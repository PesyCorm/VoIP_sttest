import heapq
import logging
import subprocess
import sys
import threading
import time
from enum import Enum
from json import loads
from os import path
from queue import Queue
from random import randint
from select import select
from socket import socket
from tempfile import mkstemp
from typing import Union

from fuzzywuzzy import fuzz as ft_search
from rtp import RTP
from rtp import PayloadType as _RTPLibPayloadType
from vosk import KaldiRecognizer, Model


logger = logging.getLogger(__name__)
sys.setswitchinterval(0.0001)


class DynamicPayloadType(Exception):
    # legacy
    pass


class NoMatchesRecognize(Exception):
    pass


class RTPProtocol(Enum):
    # legacy
    UDP = "udp"
    AVP = "RTP/AVP"
    SAVP = "RTP/SAVP"


class TransmitType(Enum):
    # legacy
    RECVONLY = "recvonly"
    SENDRECV = "sendrecv"
    SENDONLY = "sendonly"
    INACTIVE = "inactive"

    def __str__(self):
        return self.value


class PayloadType(Enum):
    def __new__(
        cls,
        value: Union[int, str],
        clock: int = 0,
        channel: int = 0,
        description: str = "",
    ):  # TODO rename args and properties
        obj = object.__new__(cls)
        obj._value_ = value
        obj.rate = clock
        obj.channel = channel
        obj.description = description
        return obj

    @property
    def rate(self) -> int:
        return self._rate

    @rate.setter
    def rate(self, value: int) -> None:
        self._rate = value

    @property
    def channel(self) -> int:
        return self._channel

    @channel.setter
    def channel(self, value: int) -> None:
        self._channel = value

    @property
    def description(self) -> str:
        return self._description

    @description.setter
    def description(self, value: str) -> None:
        self._description = value

    def __int__(self) -> int:
        try:
            return int(self.value)
        except ValueError:
            pass
        raise DynamicPayloadType(self.description + " is a dynamically assigned payload")

    def __str__(self) -> str:
        if isinstance(self.value, int):
            return self.description
        return str(self.value)

    # Audio/partial Video
    PCMU = 0, 8000, 1, "PCMU"
    GSM = 3, 8000, 1, "GSM"
    G723 = 4, 8000, 1, "G723"
    DVI4_8000 = 5, 8000, 1, "DVI4"
    DVI4_16000 = 6, 16000, 1, "DVI4"
    LPC = 7, 8000, 1, "LPC"
    PCMA = 8, 8000, 1, "PCMA"
    G722 = 9, 8000, 1, "G722"
    L16_2 = 10, 44100, 2, "L16"
    L16 = 11, 44100, 1, "L16"
    QCELP = 12, 8000, 1, "QCELP"
    CN = 13, 8000, 1, "CN"
    # MPA channel varries, should be defined in the RTP packet.
    MPA = 14, 90000, 0, "MPA"
    G728 = 15, 8000, 1, "G728"
    DVI4_11025 = 16, 11025, 1, "DVI4"
    DVI4_22050 = 17, 22050, 1, "DVI4"
    G729 = 18, 8000, 1, "G729"

    # Video
    CELB = 25, 90000, 0, "CelB"
    JPEG = 26, 90000, 0, "JPEG"
    NV = 28, 90000, 0, "nv"
    H261 = 31, 90000, 0, "H261"
    MPV = 32, 90000, 0, "MPV"
    # MP2T is both audio and video per RFC 3551 July 2003 5.7
    MP2T = 33, 90000, 1, "MP2T"
    H263 = 34, 90000, 0, "H263"

    # Non-codec
    TELEPHONE_EVENT = "telephone-event", 8000, 0, "telephone-event"
    UNKNOWN = "UNKNOWN", 0, 0, "UNKNOWN CODEC"


class DTMF:
    EVENT_NUMBERS = {
        # {Digit info: RFC2833 event}
        "0": 0,
        "1": 1,
        "2": 2,
        "3": 3,
        "4": 4,
        "5": 5,
        "6": 6,
        "7": 7,
        "8": 8,
        "9": 9,
        "*": 10,
        "#": 11,
        "A": 12,
        "B": 13,
        "C": 14,
        "D": 15,
        "Flash": 16,
    }

    def make_numbers_packets(self, numbers: str) -> list[bytes]:
        res_packets = []
        timestamp = 1
        sequence = None
        ssrc = None
        for number in numbers:
            packets = []

            number = self.EVENT_NUMBERS[number].to_bytes(length=1, byteorder="big")

            for p in range(1, 10):
                # 9 пакетов - произвольное значение.
                # Насчет рекомендаций не вдавался в подробности стандарта, подозреваю что там ничего КОНКРЕТНОГО нет.
                # В любом случае должен быть первый маркированный пакет, и 1-3 завершающих пакета с end-bit
                event_duration = p * 160
                if p > 7:  # end event
                    # number + End bit/R-bit/Volume + duration bytes
                    dtmf_payload = (
                        number
                        + (0b10001010).to_bytes(length=1, byteorder="big")
                        + event_duration.to_bytes(length=2, byteorder="big")
                    )
                else:
                    dtmf_payload = (
                        number
                        + (0b00001010).to_bytes(length=1, byteorder="big")
                        + event_duration.to_bytes(length=2, byteorder="big")
                    )

                if p == 1:
                    pack = RTP(
                        marker=True,
                        payloadType=_RTPLibPayloadType.DYNAMIC_101,
                        # в payload types медиа аудио/видео dtmf аналогично обозначен как 101
                        timestamp=timestamp,
                        payload=bytearray(dtmf_payload),
                    )
                    sequence = pack.sequenceNumber if not sequence else sequence + 1
                    ssrc = pack.ssrc if not ssrc else ssrc
                    pack.sequenceNumber = sequence
                    pack.ssrc = ssrc
                else:
                    sequence += 1
                    pack = RTP(
                        marker=False,
                        payloadType=_RTPLibPayloadType.DYNAMIC_101,
                        # в payload types медиа аудио/видео dtmf аналогично обозначен как 101
                        timestamp=timestamp,
                        payload=bytearray(dtmf_payload),
                        sequenceNumber=sequence,
                        ssrc=ssrc,
                    )
                packets.append(pack.toBytes())
            timestamp += 160
            res_packets.extend(packets)
        return res_packets


class _STT:
    # Можно конечно в отдельный модуль вынести, но тут используются атрибуты этого модуля.
    # А в этом модуле, соответственно, используется сам инстанс СТТ.
    # Пока не хочется мучиться с расхлебыванием цикличных импортов.
    MINIMAL_MATCH_SCORE = 80
    REC_CODEC = "s16le"
    CODEC_TABLE = {
        "s16le": {"ffname": "s16le", "rate": 16_000},
        PayloadType.PCMU.description: {"ffname": "mulaw", "rate": PayloadType.PCMU.rate},
        PayloadType.PCMA.description: {"ffname": "alaw", "rate": PayloadType.PCMA.rate},
    }

    def __init__(self):
        model_path: str = path.join(path.dirname(__file__), "..", "data", "small_model")
        self.rec = KaldiRecognizer(Model(model_path), self.CODEC_TABLE[self.REC_CODEC]["rate"])
        self.locker = threading.Lock()

    def recognize(self, payload_file_path: str, payload_codec_name: str, ivr_index) -> dict:
        self.locker.acquire(timeout=10)
        with subprocess.Popen(
            [
                "ffmpeg", "-loglevel", "quiet", "-f", f'{self.CODEC_TABLE[payload_codec_name]["ffname"]}',
                "-ar", f'{self.CODEC_TABLE[payload_codec_name]["rate"]}', "-ac", "1", "-i", f"{payload_file_path}",
                "-f", f'{self.CODEC_TABLE[self.REC_CODEC]["ffname"]}',
                "-ar", f'{self.CODEC_TABLE[self.REC_CODEC]["rate"]}', "-ac", "1", "-",
            ],
            stdout=subprocess.PIPE,
        ) as proc:
            while True:
                data = proc.stdout.read(4000)
                if len(data) == 0:
                    break
                self.rec.AcceptWaveform(data)
        res = self._normalize_by_index(loads(self.rec.FinalResult())["text"], ivr_index)
        self.locker.release()
        return res

    def _normalize_by_index(self, ivr_str: str, ivr_index) -> dict:
        def clear_text(text: str) -> str:
            patterns = (".", ",", ":", "!", "?")
            text = text.lower()
            for p in patterns:
                text = text.replace(p, " ").replace("  ", " ")
            return text.strip()

        _ivr_str = clear_text(ivr_str)

        if hasattr(ivr_index, "local"):
            # ну это конечно оверинжиниринг виктимблейминг смолл дик энерджи и вообще у автора беды с башкой
            # но в целом пока работает, не горит делать нормально так что TODO

            index_value = ivr_index.local
            result_value = ""
            free_part = False
            last_ivr_index = 0
            ivr_list = _ivr_str.split()

            for word in clear_text(index_value).split():
                if free_part and word == "%":
                    free_part = False
                elif word == "%":
                    free_part = True
                elif free_part:
                    result_value += word
                elif word == "{d}":
                    for i, v in enumerate(ivr_list[last_ivr_index:]):
                        try:
                            result_value += str(text_to_number(v))
                            last_ivr_index += i + 1
                            break
                        except KeyError:
                            continue
                    else:
                        raise NoMatchesRecognize(
                            "Ошибка при заполнении данными шаблона.\n"
                            f"Запись которую распознавали: {_ivr_str}\n"
                            f"Шаблон: {index_value}\n"
                        )
                else:
                    raise NoMatchesRecognize(
                        "Ошибка в шаблоне для local записи.\n"
                        f"Не смогли подобрать паттерн нормализации для шаблона {index_value}"
                    )
                result_value += " "
            return {"local": result_value.strip()}

        elif isinstance(ivr_index, Enum):
            # тут пришлось немного нагнуться и написать свой цикл,
            # потому что при использовании fuzzywuzzy.process.extract
            # мы будем получать то что передали - а именно "очищенный" текст,
            # который потом не сможем сравнить с эталоном.
            ilm = ivr_index.index_list_messages()  # noqa
            values = [
                (k, ft_search.ratio(_ivr_str, clear_text(v)))
                for k, v in ilm.items()
            ]
            values = heapq.nlargest(2, values, key=lambda i: i[1])
            assert values[0][1] >= 80, (
                f"Процент совпадения для ближайшей распознанной записи < {80}\n"
                f"Распознанная запись: {_ivr_str}\n"
                f"Записи в индексе: {ivr_index.index_list_messages()}\n"  # noqa
            )

            if len(values) > 1 and ((values[0][1] - 10) <= values[1][1]):
                logger.warning(
                    f"Для распознанной записи расстояние между двумя ближайшими соседними записями <10\n"
                    f"Распознанная запись: {ivr_str}\n"
                    f"Ближайшая нормализованная (match score {values[0][1]}): {values[0][0]}\n"
                    f"Следующая нормализованная (match score {values[1][1]}): {values[1][0]}\n"
                )
            index_value = {values[0][0]: ilm[values[0][0]]}

        else:
            raise RuntimeError(f"Не смогли определить способ нормализации для индекса {ivr_index}")

        return index_value


class _Media:
    data = dict()
    stt_workers = Queue()
    locker = threading.Lock()

    @classmethod
    def init_stt_workers(cls, workers: int = 1):
        for _ in range(workers):
            cls.stt_workers.put(_STT())

    @classmethod
    def get_stt_worker(cls) -> _STT:
        """Simple thread-safe roundrobin."""
        cls.locker.acquire()
        # по сути, queue гарантирует консистентность извлечения/добавления данных в очередь,
        # но вот между двумя этими действиями все-таки нужно самому не давать потокам нарушить это дзен.
        worker = cls.stt_workers.get()
        cls.stt_workers.put(worker)
        cls.locker.release()
        return worker

    def __init__(self, issued_socket: socket):
        self.socket = issued_socket
        self.dtmf_generator = DTMF()
        self.socket_ready = False
        self.data["port"] = self.socket.getsockname()[1]

    def _set_socket_connection(self, connection_data: tuple) -> None:
        self.socket.connect(connection_data)
        self.socket_ready = True

    def _check_socket_ready(self, timeout: int = 5) -> None:
        st = time.time()
        while True:
            if st + timeout < time.time():
                raise RuntimeError("Media socket is not ready!")
            if self.socket_ready:
                return

    def recv(self) -> bytes:
        self._check_socket_ready()
        r, _, _ = select([self.socket], [], [], 0.1)
        if r:
            return self.socket.recv(4096)

    def send(self, data: bytes) -> None:
        self._check_socket_ready()
        self.socket.send(data)

    def stop(self) -> None:
        self.socket.close()


class _MediaWrapper(_Media):
    available_codecs = {
        PayloadType.PCMU.value: PayloadType.PCMU,
        PayloadType.PCMA.value: PayloadType.PCMA,
        PayloadType.G722.value: PayloadType.G722,
        101: PayloadType.TELEPHONE_EVENT,  # TODO fix this
    }

    def send_dtmf(self, numbers: str) -> None:
        for pack in self.dtmf_generator.make_numbers_packets(numbers):
            time.sleep(0.0160)
            self.send(pack)

    def send_audio(self, file_path: str):
        """Отправка аудио в сторону АТС (кодек G.711u)
        :param file_path: путь до аудио файла (только формат wav)
        :return:
        """
        with subprocess.Popen(
            [
                "ffmpeg", "-loglevel", "quiet", "-i", f"{file_path}",
                "-f", "mulaw", "-ar", "8000", "-ac", "1", "-",
            ],
            stdout=subprocess.PIPE,
        ) as proc:
            ssrc = randint(0, (2**32) - 1)
            while True:
                # Насколько мне известно, в RTP нет указания по поводу максимального размера payload части.
                # 160 байт является просто наиболее оптимальным размером.
                data = proc.stdout.read(160)
                if len(data) == 0:
                    break
                packet = RTP(
                    version=2,
                    padding=False,
                    marker=False,
                    payloadType=_RTPLibPayloadType.PCMU,
                    sequenceNumber=randint(1, 9999),
                    timestamp=randint(1, 9999),
                    ssrc=ssrc,
                    extension=None,
                    csrcList=None,
                    payload=bytearray(data),
                ).toBytes()
                self.send(packet)

    def _recv_media_fragment(self, timeout: int = 10) -> tuple[int, bytes]:
        """
        :param timeout:
        :return: tuple[payload type (codec), payload bytes]
        """
        timer = time.time()
        data = []
        codec = None
        while True:
            if timer <= (time.time() - timeout):
                raise TimeoutError
            if data and timer <= (time.time() - 0.5):
                # если в течение 500мс не смогли прочитать новый пакет, считаем аудио фрагмент завершенным.
                return codec, b"".join(data)

            frame_4096 = self.recv()
            if frame_4096:
                if not codec:
                    codec = RTP().fromBytearray(bytearray(frame_4096)).payloadType

                data.append(RTP().fromBytearray(bytearray(frame_4096)).payload)
                timer = time.time()

    def _recognize(self, codec_name: int, payload_file_path: str, ivr_index) -> dict:
        worker = self.get_stt_worker()
        return worker.recognize(
            payload_file_path,
            codec_name,  # noqa
            ivr_index,
        )

    def _compare_ivr(self, recognized: dict, standard: str | Enum) -> None:
        recognized_index, recognized_data = tuple(recognized.items())[0]
        if isinstance(standard, Enum):
            standard = standard.value  # noqa
        assert recognized_data == standard, f"\nОжидали услышать: {standard}\nУслышали: {recognized_data}"

    def _get_cached_ivr(self) -> None | dict:
        if hasattr(self, "last_cached_ivr"):
            res = self.last_cached_ivr
            delattr(self, "last_cached_ivr")
            return res

    def listen(self, ivr_index) -> dict:
        if cached_ivr := self._get_cached_ivr():
            self._compare_ivr(cached_ivr, ivr_index)
            return cached_ivr
        codec, payload = self._recv_media_fragment()
        tmp_file_path = mkstemp()[1]  # mkstemp(): -> tuple[fileno, filepath]
        with open(tmp_file_path, "wb") as f:
            f.write(payload)
        rd = self._recognize(
            self.available_codecs[codec].description,  # noqa
            tmp_file_path,
            ivr_index,
        )
        if rd.get("local"):
            return rd  # такие записи возвращаются в необработанном виде. используется для ивров вроде редиала.
        # дальше ффууууу
        rd = tuple(*rd.items())
        if "__" in rd[0]:
            _rd_indexes = rd[0].split("__")
            self.last_cached_ivr = {_rd_indexes[1]: getattr(ivr_index, _rd_indexes[1]).value}
            rd = (_rd_indexes[0], getattr(ivr_index, _rd_indexes[0]).value)
        rd = {rd[0]: rd[1]}
        self._compare_ivr(rd, ivr_index)
        return rd
