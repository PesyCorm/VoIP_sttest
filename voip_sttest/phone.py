import logging
from enum import Enum
from typing import Optional

from ._implement_call import _Call
from .media.media import _MediaWrapper
from .SIP.sip_factory import SIPMessage, SIPStatus, SIPMessageType
from .SIP.sip_manager import SipFlow
from .helpers.waiter import try_wait
from .helpers.network import get_available_socket


logger = logging.getLogger(__name__)


class PhoneStatus(Enum):
    INACTIVE = "INACTIVE"
    REGISTERING = "REGISTERING"
    REGISTERED = "REGISTERED"
    DEREGISTER = "DEREGISTER"
    FAILED = "FAILED"


class Phone:
    stt_workers_num = 1

    def __init__(
        self,
        stand: str,
        pbx_host: str,
        pbx_port: int,
        username: str,
        password: str,
        dial_prefix: str = '',
        call_wrapper: type[_Call] = _Call,
        media_wrapper: type[_MediaWrapper] = _MediaWrapper
    ):
        self.stand = stand
        self.pbx_host = pbx_host
        self.pbx_port = pbx_port
        self.username = username
        self.password = password
        self.dial_prefix = dial_prefix
        self._status: Optional[PhoneStatus] = None

        self.calls: dict[str, _Call] = dict()  # Не гарантируется что звонки в списке живые/остановленные
        self._sip = SipFlow(
            self.pbx_host,
            self.pbx_port,
            username,
            password,
            get_available_socket(connected=True, host=self.pbx_host, port=self.pbx_port),
            self._callback,
        )
        self._call_wrapper = call_wrapper
        self._media_wrapper = media_wrapper
        self._media_wrapper.init_stt_workers(self.stt_workers_num)

    def __del__(self):
        self.stop()

    def _del_call(self, call_id: str) -> None:
        self.calls.pop(call_id)

    def _callback(self, request: SIPMessage) -> None:
        requested_call = try_wait(
            lambda: self.calls[request.headers['Call-ID']],
            wait_time=2,
            raise_after_time=True,
            message_on_error=f'Не смогли получить инстанс звонка для Call-ID {request.headers["Call-ID"]}'
        )
        if request.type == SIPMessageType.MESSAGE:
            if request.method == "BYE":
                requested_call._handle_bye(request)
            else:
                raise RuntimeError(f'Unknown SIP message: {request.method}')
        else:
            if request.status == SIPStatus.TRYING:
                requested_call._handle_trying(request)
            elif request.status == SIPStatus.OK:
                requested_call._handle_OK(request)
            elif request.status == SIPStatus.NOT_FOUND:
                requested_call._handle_not_found(request)
            elif request.status == SIPStatus.SERVICE_UNAVAILABLE:
                requested_call._handle_unavailable(request)
            elif request.status == SIPStatus.UNAUTHORIZED:
                requested_call._handle_unauthorized(request)
            elif request.status == SIPStatus.PROXY_AUTHENTICATION_REQUIRED:
                print('handle 407')
                requested_call._handle_unauthorized(request)
            else:
                raise RuntimeError(f'Unknown sip status: {request.status}')

    @property
    def status(self) -> PhoneStatus:
        return self._status

    def start(self) -> "Phone":
        logger.info('Проходим регистрацию на АТС')
        self._status = PhoneStatus.REGISTERING
        self._sip.start()
        self._status = PhoneStatus.REGISTERED
        return self

    def hangup(self, call: _Call) -> None:
        self._stop_call(call.call_data['call_id'])

    def call(self, number: Optional[str] = '') -> _Call:
        logger.info(f'Начинаем новый звонок. Номер набора: {number}')
        new_call = self._call_wrapper(
            pbx_info={'host': self.pbx_host, 'port': self.pbx_port},
            sip_manager=self._sip,
            media_wrapper=self._media_wrapper(get_available_socket()),
        )
        new_call._new_call(f'{self.dial_prefix}{number}')
        self.calls[new_call.call_data['call_id']] = new_call
        return new_call

    def stop(self) -> None:
        logger.info('Завершаем работу телефона')
        if self.calls:
            for call_id in list(self.calls.keys()):
                self._stop_call(call_id)
        self._status = PhoneStatus.DEREGISTER
        self._sip.stop()
        self._status = PhoneStatus.INACTIVE

    def _stop_call(self, call_id):
        logger.info(f'Завершаем звонок {call_id}')
        if call := self.calls.get(call_id):
            call._hangup()
            self._del_call(call_id)
