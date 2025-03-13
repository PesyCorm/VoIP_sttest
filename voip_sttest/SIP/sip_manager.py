"""Partially implemented from https://github.com/tayler6000/pyVoIP/blob/v1.6.8/pyVoIP/SIP.py"""

import socket
import uuid
import time
import random
import hashlib
from select import select
from threading import Timer, Lock
from typing import Callable, Optional

from voip_sttest.helpers.waiter import try_wait
from voip_sttest.media.media import PayloadType
from voip_sttest.SIP.sip_factory import SIPMessage, SIPMessageType, SIPStatus, SipFactory


class _Counter:
    def __init__(self):
        self.value = 0
        self.locker = Lock()

    def next(self):
        self.locker.acquire()
        self.value += 1
        self.locker.release()
        return self.value


class SIPImpl:
    def __init__(
            self,
            pbx_host: str,
            pbx_port: int,
            username: str,
            password: str,
            connected_socket: socket.socket
    ):
        self.pbx_host = pbx_host
        self.pbx_port = pbx_port
        self.username = username
        self.password = password

        self.socket = connected_socket
        self.local_addr = self.socket.getsockname()[0]
        self.local_port = self.socket.getsockname()[1]

        self.default_expires = 300
        self.response_timeout = 10

        self.invite_cseq = _Counter()
        self.register_cseq = _Counter()
        self.bye_cseq = _Counter()
        self.call_id_counter = _Counter()
        self.sess_id_counter = _Counter()

        self.urn_uuid = self._gen_urn_uuid()

        self.recv_locker = Lock()
        self.send_locker = Lock()

        self.NSD = False

        self.used_tags = []

        self.sip_factory = SipFactory(
            pbx_host,
            pbx_port,
            self.local_addr,
            self.local_port,
            username,
            password,
            self.urn_uuid
        )

    def _gen_urn_uuid(self) -> str:
        """
        Generate client instance specific urn:uuid
        """
        return str(uuid.uuid4()).upper()

    def _gen_branch(self, length=32) -> str:
        """
        Generate unique branch id according to
        https://datatracker.ietf.org/doc/html/rfc3261#section-8.1.1.7
        """
        branchid = uuid.uuid4().hex[: length - 7]
        return f"z9hG4bK{branchid}"

    def _gen_tag(self) -> str:
        # Keep as True instead of NSD so it can generate a tag on deregister.
        while True:
            rand = str(random.randint(1, 4294967296)).encode("utf8")
            tag = hashlib.md5(rand).hexdigest()[0:8]
            if tag not in self.used_tags:
                self.used_tags.append(tag)
                return tag

    def _gen_call_id(self) -> str:
        hash = hashlib.sha256(str(self.call_id_counter.next()).encode("utf8"))
        hhash = hash.hexdigest()
        return f"{hhash[0:32]}@{self.local_addr}:{self.local_port}"

    def _recv(self, timeout: float = 0.1) -> bytes | None:
        data = None
        self.recv_locker.acquire()
        r, _, _ = select([self.socket,], [], [], timeout)
        if r:
            data = self.socket.recv(8192)
        self.recv_locker.release()
        return data

    def recv_message(self, timeout: float = 0.1) -> SIPMessage | None:
        raw = self._recv(timeout)
        if raw and raw != b"\x00\x00\x00\x00":
            message = SIPMessage(raw)
            return message

    def _send_message(self, message: str) -> SIPMessage:
        message_bytes = message.encode('utf8')
        self.send_locker.acquire()
        self.socket.send(message_bytes)
        self.send_locker.release()
        return SIPMessage(message_bytes)

    def send_register(self, request: Optional[SIPMessage] = None, start_session: bool = True) -> SIPMessage:
        reg_expiration = self.default_expires if start_session else 0
        if request:
            if request.status == SIPStatus.UNAUTHORIZED:
                authorization = {
                    'realm': request.authentication['realm'],
                    'nonce': request.authentication['nonce']
                }
            else:
                authorization = None

            message = self.sip_factory.gen_register(
                expires=reg_expiration,
                branch=request.headers['Via'][0]['branch'],  # list values - legacy, multiple Via header
                tag=self._gen_tag(),
                call_id=request.headers['Call-ID'],
                cseq=self.register_cseq.next(),
                authorization=authorization
            )
        else:
            message = self.sip_factory.gen_register(
                expires=reg_expiration,
                branch=self._gen_branch(),
                tag=self._gen_tag(),
                call_id=self._gen_call_id(),
                cseq=self.register_cseq.next(),
            )
        return self._send_message(message)

    def send_invite(
            self,
            number: str,
            media_port: int,
            sendtype: str,
            available_payload: dict[int, PayloadType],
            sess_id: Optional[int] = None,
            request: Optional[SIPMessage] = None
    ) -> SIPMessage:
        call_id = request.headers['Call-ID'] if request else self._gen_call_id()
        if request:
            if request.status in (SIPStatus.UNAUTHORIZED, SIPStatus.PROXY_AUTHENTICATION_REQUIRED):
                authorization = {
                    'realm': request.authentication['realm'],
                    'nonce': request.authentication['nonce']
                }
            else:
                authorization = None
            sdp = self.sip_factory.gen_sdp(
                sess_id=sess_id,
                media_port=media_port,
                available_payload=available_payload,
                sendtype=sendtype
            )
            message = self.sip_factory.gen_invite(
                number=number,
                branch=request.headers['Via'][0]['branch'],
                cseq=self.invite_cseq.next(),
                tag=self._gen_tag(),
                call_id=call_id,
                sdp=sdp,
                authorization=authorization
            )
        else:
            sdp = self.sip_factory.gen_sdp(
                sess_id=self.sess_id_counter.next(),
                media_port=media_port,
                available_payload=available_payload,
                sendtype=sendtype
            )
            message = self.sip_factory.gen_invite(
                number=number,
                branch=self._gen_branch(),
                cseq=self.invite_cseq.next(),
                tag=self._gen_tag(),
                call_id=call_id,
                sdp=sdp,
            )

        res = self._send_message(message)
        return res

    def send_ack(self, request: SIPMessage) -> SIPMessage:
        return self._send_message(
            self.sip_factory.gen_ack(request)
        )

    def send_ok(self, request: SIPMessage) -> SIPMessage:
        return self._send_message(
            self.sip_factory.gen_ok(request)
        )

    def send_bye(self, request: SIPMessage) -> SIPMessage:
        return self._send_message(
            self.sip_factory.gen_bye(self._gen_tag(), request)
        )


class SipFlow(SIPImpl):
    def __init__(
            self,
            pbx_host: str,
            pbx_port: int,
            username: str,
            password: str,
            connected_socket: socket.socket,
            callback_rules: Callable
    ):
        super().__init__(pbx_host, pbx_port, username, password, connected_socket)
        self.callback = callback_rules

        self.register_thread = None  # TODO unfilled
        self.recv_thread = None

        self.first_reg_success = False  # The flag that the first registration was successful, you can start the call
        self.reg_ended = False  # Flag that the session is over (authorized REGISTER with expires==0)
        self.trying_end_session = False  # Flag of attempt to terminate session
        # Used to determine Expires when handling 401 Unauthorized (REGISTER)
        self.trying_reg_count = 0
        self.max_trying_reg = 2

    def _check_registered(self, wait: int = 20):
        st = time.time()
        while st + wait >= time.time():
            if self.first_reg_success:
                return
        raise TimeoutError('Failed to register on the PBX.')

    def _manage_recv(self):
        while self.NSD:
            message = self.recv_message()
            if message:
                self._handle_message(message)

    def _handle_message(self, message: SIPMessage) -> None:
        if self.callback is None:
            raise RuntimeError(
                'Error initializing SIP manager, missing instructions for processing received messages.'
            )
        if message.type != SIPMessageType.MESSAGE:
            if message.headers['CSeq']['method'] == 'REGISTER':
                if message.status in (SIPStatus.UNAUTHORIZED, SIPStatus.PROXY_AUTHENTICATION_REQUIRED):
                    if self.trying_reg_count > self.max_trying_reg:
                        raise RuntimeError('Failed to register on the PBX.')
                    self.trying_reg_count += 1
                    if self.trying_end_session:
                        self.send_register(message, start_session=False)
                    else:
                        self.send_register(message)
                elif message.status == SIPStatus.OK:
                    self.trying_reg_count = 0
                    if not self.first_reg_success:
                        self.first_reg_success = True
                    if self.trying_end_session:
                        self.reg_ended = True
                else:
                    raise RuntimeError('unexpected error')
            elif message.status in (
                # Callback calls are not always about a response to the PBX.
                # For some statuses, this is simply a change in the state of the call instance.
                SIPStatus.OK,
                SIPStatus.NOT_FOUND,
                SIPStatus.SERVICE_UNAVAILABLE,
                SIPStatus.TRYING,
                SIPStatus.RINGING,
                SIPStatus.UNAUTHORIZED,
                SIPStatus.PROXY_AUTHENTICATION_REQUIRED # 401/407 for invite is processed by call callback,
                    # since tracking of attempts occurs for each call separately
            ):
                self.callback(message)
            else:
                raise RuntimeError(f'Received an unknown SIP message type: {message.summary()}')
        elif message.method == "BYE":
            self.callback(message)
        elif message.method == 'OPTIONS':
            self.send_ok(message)
        elif message.method == 'ACK':
            # just ignore it, no need to process it
            return
        else:
            raise RuntimeError(f'Received an unknown SIP message type: {message.summary()}')

    def start(self) -> None:
        if self.NSD:
            raise RuntimeError("Attempted to start already started SIPClient")
        self.NSD = True
        self.trying_reg_count += 1
        self.send_register()
        self.recv_thread = Timer(1, self._manage_recv)
        self.recv_thread.start()

    def stop(self):
        self.trying_end_session = True
        self.send_register(start_session=False)
        try_wait(
            lambda: self.reg_ended,
            check_result_eq_true=True,
            wait_time=5,
            raise_after_time=True,
            message_on_error='The 200 OK (REGISTER) response was not received from the PBX when the session ended.'
        )
        self.NSD = False

    def send_invite(
            self,
            number: str,
            media_port: int,
            sendtype: str,
            available_payload: dict[int, PayloadType],
            sess_id: Optional[int] = None,
            request: Optional[SIPMessage] = None
    ) -> SIPMessage:
        self._check_registered()
        return super().send_invite(number, media_port, sendtype, available_payload, sess_id, request)

    def send_bye(self, request: SIPMessage) -> SIPMessage:
        self._check_registered()
        return super().send_bye(request)
