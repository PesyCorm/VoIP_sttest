"""implemented from https://github.com/tayler6000/pyVoIP/blob/v1.6.8/pyVoIP/SIP.py"""
import re
import hashlib
from enum import Enum, IntEnum
from typing import Optional, Any, Callable

from qa_voip_py.media.media import RTPProtocol, TransmitType, PayloadType


SIPCompatibleMethods = ["INVITE", "ACK", "BYE", "CANCEL", "OPTIONS", "REGISTER"]
SIPCompatibleVersions = ["SIP/2.0"]


class InvalidAccountInfoError(Exception):
    pass


class SIPParseError(Exception):
    pass


class SIPStatus(Enum):
    def __new__(cls, value: int, phrase: str = "", description: str = ""):
        obj = object.__new__(cls)
        obj._value_ = value

        obj.phrase = phrase
        obj.description = description
        return obj

    def __int__(self) -> int:
        return self._value_

    def __str__(self) -> str:
        return f"{self._value_} {self.phrase}"

    @property
    def phrase(self) -> str:
        return self._phrase

    @phrase.setter
    def phrase(self, value: str) -> None:
        self._phrase = value

    @property
    def description(self) -> str:
        return self._description

    @description.setter
    def description(self, value: str) -> None:
        self._description = value

    # Informational
    TRYING = (
        100,
        "Trying",
        "Extended search being performed, may take a significant time",
    )
    RINGING = (
        180,
        "Ringing",
        "Destination user agent received INVITE, "
        + "and is alerting user of call",
    )
    FORWARDED = 181, "Call is Being Forwarded"
    QUEUED = 182, "Queued"
    SESSION_PROGRESS = 183, "Session Progress"
    TERMINATED = 199, "Early Dialog Terminated"

    # Success
    OK = 200, "OK", "Request successful"
    ACCEPTED = (
        202,
        "Accepted",
        "Request accepted, processing continues (Deprecated.)",
    )
    NO_NOTIFICATION = (
        204,
        "No Notification",
        "Request fulfilled, nothing follows",
    )

    # Redirection
    MULTIPLE_CHOICES = (
        300,
        "Multiple Choices",
        "Object has several resources -- see URI list",
    )
    MOVED_PERMANENTLY = (
        301,
        "Moved Permanently",
        "Object moved permanently -- see URI list",
    )
    MOVED_TEMPORARILY = (
        302,
        "Moved Temporarily",
        "Object moved temporarily -- see URI list",
    )
    USE_PROXY = (
        305,
        "Use Proxy",
        "You must use proxy specified in Location to "
        + "access this resource",
    )
    ALTERNATE_SERVICE = (
        380,
        "Alternate Service",
        "The call failed, but alternatives are available -- see URI list",
    )

    # Client Error
    BAD_REQUEST = (
        400,
        "Bad Request",
        "Bad request syntax or unsupported method",
    )
    UNAUTHORIZED = (
        401,
        "Unauthorized",
        "No permission -- see authorization schemes",
    )
    PAYMENT_REQUIRED = (
        402,
        "Payment Required",
        "No payment -- see charging schemes",
    )
    FORBIDDEN = (
        403,
        "Forbidden",
        "Request forbidden -- authorization will not help",
    )
    NOT_FOUND = (404, "Not Found", "Nothing matches the given URI")
    METHOD_NOT_ALLOWED = (
        405,
        "Method Not Allowed",
        "Specified method is invalid for this resource",
    )
    NOT_ACCEPTABLE = (
        406,
        "Not Acceptable",
        "URI not available in preferred format",
    )
    PROXY_AUTHENTICATION_REQUIRED = (
        407,
        "Proxy Authentication Required",
        "You must authenticate with this proxy before proceeding",
    )
    REQUEST_TIMEOUT = (
        408,
        "Request Timeout",
        "Request timed out; try again later",
    )
    CONFLICT = 409, "Conflict", "Request conflict"
    GONE = (
        410,
        "Gone",
        "URI no longer exists and has been permanently removed",
    )
    LENGTH_REQUIRED = (
        411,
        "Length Required",
        "Client must specify Content-Length",
    )
    CONDITIONAL_REQUEST_FAILED = 412, "Conditional Request Failed"
    REQUEST_ENTITY_TOO_LARGE = (
        413,
        "Request Entity Too Large",
        "Entity is too large",
    )
    REQUEST_URI_TOO_LONG = 414, "Request-URI Too Long", "URI is too long"
    UNSUPPORTED_MEDIA_TYPE = (
        415,
        "Unsupported Media Type",
        "Entity body in unsupported format",
    )
    UNSUPPORTED_URI_SCHEME = (
        416,
        "Unsupported URI Scheme",
        "Cannot satisfy request",
    )
    UNKOWN_RESOURCE_PRIORITY = (
        417,
        "Unkown Resource-Priority",
        "There was a resource-priority option tag, "
        + "but no Resource-Priority header",
    )
    BAD_EXTENSION = (
        420,
        "Bad Extension",
        "Bad SIP Protocol Extension used, not understood by the server.",
    )
    EXTENSION_REQUIRED = (
        421,
        "Extension Required",
        "Server requeires a specific extension to be "
        + "listed in the Supported header.",
    )
    SESSION_INTERVAL_TOO_SMALL = 422, "Session Interval Too Small"
    SESSION_INTERVAL_TOO_BRIEF = 423, "Session Interval Too Breif"
    BAD_LOCATION_INFORMATION = 424, "Bad Location Information"
    USE_IDENTITY_HEADER = (
        428,
        "Use Identity Header",
        "The server requires an Identity header, "
        + "and one has not been provided.",
    )
    PROVIDE_REFERRER_IDENTITY = 429, "Provide Referrer Identity"
    """
    This response is intended for use between proxy devices,
    and should not be seen by an endpoint. If it is seen by one,
    it should be treated as a 400 Bad Request response.
    """
    FLOW_FAILED = (
        430,
        "Flow Failed",
        "A specific flow to a user agent has failed, "
        + "although other flows may succeed.",
    )
    ANONYMITY_DISALLOWED = 433, "Anonymity Disallowed"
    BAD_IDENTITY_INFO = 436, "Bad Identity-Info"
    UNSUPPORTED_CERTIFICATE = 437, "Unsupported Certificate"
    INVALID_IDENTITY_HEADER = 438, "Invalid Identity Header"
    FIRST_HOP_LACKS_OUTBOUND_SUPPORT = 439, "First Hop Lacks Outbound Support"
    MAX_BREADTH_EXCEEDED = 440, "Max-Breadth Exceeded"
    BAD_INFO_PACKAGE = 469, "Bad Info Package"
    CONSENT_NEEDED = 470, "Consent Needed"
    TEMPORARILY_UNAVAILABLE = 480, "Temporarily Unavailable"
    CALL_OR_TRANSACTION_DOESNT_EXIST = 481, "Call/Transaction Does Not Exist"
    LOOP_DETECTED = 482, "Loop Detected"
    TOO_MANY_HOPS = 483, "Too Many Hops"
    ADDRESS_INCOMPLETE = 484, "Address Incomplete"
    AMBIGUOUS = 485, "Ambiguous"
    BUSY_HERE = 486, "Busy Here", "Callee is busy"
    REQUEST_TERMINATED = 487, "Request Terminated"
    NOT_ACCEPTABLE_HERE = 488, "Not Acceptable Here"
    BAD_EVENT = 489, "Bad Event"
    REQUEST_PENDING = 491, "Request Pending"
    UNDECIPHERABLE = 493, "Undecipherable"
    SECURITY_AGREEMENT_REQUIRED = 494, "Security Agreement Required"

    # Server Errors
    INTERNAL_SERVER_ERROR = (
        500,
        "Internal Server Error",
        "Server got itself in trouble",
    )
    NOT_IMPLEMENTED = (
        501,
        "Not Implemented",
        "Server does not support this operation",
    )
    BAD_GATEWAY = (
        502,
        "Bad Gateway",
        "Invalid responses from another server/proxy",
    )
    SERVICE_UNAVAILABLE = (
        503,
        "Service Unavailable",
        "The server cannot process the request due to a high load",
    )
    GATEWAY_TIMEOUT = (
        504,
        "Server Timeout",
        "The server did not receive a timely response",
    )
    SIP_VERSION_NOT_SUPPORTED = (
        505,
        "SIP Version Not Supported",
        "Cannot fulfill request",
    )
    MESSAGE_TOO_LONG = 513, "Message Too Long"
    PUSH_NOTIFICATION_SERVICE_NOT_SUPPORTED = (
        555,
        "Push Notification Service Not Supported",
    )
    PRECONDITION_FAILURE = 580, "Precondition Failure"

    # Global Failure Responses
    BUSY_EVERYWHERE = 600, "Busy Everywhere"
    DECLINE = 603, "Decline"
    DOES_NOT_EXIST_ANYWHERE = 604, "Does Not Exist Anywhere"
    GLOBAL_NOT_ACCEPTABLE = 606, "Not Acceptable"
    UNWANTED = 607, "Unwanted"
    REJECTED = 608, "Rejected"


class SIPMessageType(IntEnum):
    def __new__(cls, value: int):
        obj = int.__new__(cls, value)
        obj._value_ = value
        return obj

    MESSAGE = 1
    RESPONSE = 0


class SIPMessage:
    def __init__(self, data: bytes):
        self.SIPCompatibleVersions = SIPCompatibleVersions
        self.SIPCompatibleMethods = SIPCompatibleMethods
        self.heading = b""
        self.type: Optional[SIPMessageType] = None
        self.status = None
        self.headers: dict[str, Any] = {"Via": []}
        self.body: dict[str, Any] = {}
        self.authentication: dict[str, str] = {}
        self.raw = data
        self.auth_match = re.compile(r'(\w+)=("[^",]+"|[^ \t,]+)')
        self.parse(data)

    def summary(self) -> str:
        data = ""
        if self.type == SIPMessageType.RESPONSE:
            data += f"Status: {int(self.status)} {self.status.phrase}\n\n"
        else:
            data += f"Method: {self.method}\n\n"
        data += "Headers:\n"
        for x in self.headers:
            data += f"{x}: {self.headers[x]}\n"
        data += "\n"
        data += "Body:\n"
        for x in self.body:
            data += f"{x}: {self.body[x]}\n"
        data += "\n"
        data += "Raw:\n"
        data += str(self.raw)

        return data

    def parse(self, data: bytes) -> None:
        try:
            headers, body = data.split(b"\r\n\r\n")
        except ValueError as ve:
            print(f"Error unpacking data, only using header: {ve}")
            headers = data.split(b"\r\n\r\n")[0]

        headers_raw = headers.split(b"\r\n")
        heading = headers_raw.pop(0)
        check = str(heading.split(b" ")[0], "utf8")

        if check in self.SIPCompatibleVersions:
            self.type = SIPMessageType.RESPONSE
            self.parse_sip_response(data)
        elif check in self.SIPCompatibleMethods:
            self.type = SIPMessageType.MESSAGE
            self.parse_sip_message(data)
        else:
            raise SIPParseError(
                "Unable to decipher SIP request: " + str(heading, "utf8")
            )

    def parse_header(self, header: str, data: str) -> None:
        if header == "Via":
            for d in data:
                info = re.split(" |;", d)
                _type = info[0]  # SIP Method
                _address = info[1].split(":")  # Tuple: address, port
                _ip = _address[0]

                """
                If no port is provided in via header assume default port.
                Needs to be str. Check response build for better str creation
                """
                _port = info[1].split(":")[1] if len(_address) > 1 else "5060"
                _via = {"type": _type, "address": (_ip, _port)}

                """
                Sets branch, maddr, ttl, received, and rport if defined
                as per RFC 3261 20.7
                """
                for x in info[2:]:
                    if "=" in x:
                        _via[x.split("=")[0]] = x.split("=")[1]
                    else:
                        _via[x] = None
                self.headers["Via"].append(_via)
        elif header == "From" or header == "To":
            info = data.split(";tag=")
            tag = ""
            if len(info) >= 2:
                tag = info[1]
            raw = info[0]
            # fix issue 41 part 1
            contact = re.split(r"<?sip:", raw)
            contact[0] = contact[0].strip('"').strip("'")
            address = contact[1].strip(">")
            if len(address.split("@")) == 2:
                number = address.split("@")[0]
                host = address.split("@")[1]
            else:
                number = None
                host = address

            self.headers[header] = {
                "raw": raw,
                "tag": tag,
                "address": address,
                "number": number,
                "caller": contact[0],
                "host": host,
            }
        elif header == "CSeq":
            self.headers[header] = {
                "check": data.split(" ")[0],
                "method": data.split(" ")[1],
            }
        elif header == "Allow" or header == "Supported":
            self.headers[header] = data.split(", ")
        elif header == "Content-Length":
            self.headers[header] = int(data)
        elif header in ("WWW-Authenticate", "Authorization", "Proxy-Authenticate"):
            print(f'parse header: {header}')
            data = data.replace("Digest ", "")
            row_data = self.auth_match.findall(data)
            header_data = {}
            for var, data in row_data:
                header_data[var] = data.strip('"')
            self.headers[header] = header_data
            self.authentication = header_data
            print(f'auth data: {self.authentication}')
        else:
            self.headers[header] = data

    def parse_body(self, header: str, data: str) -> None:
        if "Content-Encoding" in self.headers:
            raise SIPParseError("Unable to parse encoded content.")
        if self.headers["Content-Type"] == "application/sdp":
            # Referenced RFC 4566 July 2006
            if header == "v":
                # SDP 5.1 Version
                self.body[header] = int(data)
            elif header == "o":
                # SDP 5.2 Origin
                # o=<username> <sess-id> <sess-version> <nettype> <addrtype> <unicast-address> # noqa: E501
                d = data.split(" ")
                self.body[header] = {
                    "username": d[0],
                    "id": d[1],
                    "version": d[2],
                    "network_type": d[3],
                    "address_type": d[4],
                    "address": d[5],
                }
            elif header == "s":
                # SDP 5.3 Session Name
                # s=<session name>
                self.body[header] = data
            elif header == "i":
                # SDP 5.4 Session Information
                # i=<session-description>
                self.body[header] = data
            elif header == "u":
                # SDP 5.5 URI
                # u=<uri>
                self.body[header] = data
            elif header == "e" or header == "p":
                # SDP 5.6 Email Address and Phone Number of person
                # responsible for the conference
                # e=<email-address>
                # p=<phone-number>
                self.body[header] = data
            elif header == "c":
                # SDP 5.7 Connection Data
                # c=<nettype> <addrtype> <connection-address>
                if "c" not in self.body:
                    self.body["c"] = []
                d = data.split(" ")
                # TTL Data and Multicast addresses may be specified.
                # For IPv4 its listed as addr/ttl/number of addresses.
                # c=IN IP4 224.2.1.1/127/3 means:
                # c=IN IP4 224.2.1.1/127
                # c=IN IP4 224.2.1.2/127
                # c=IN IP4 224.2.1.3/127
                # With the TTL being 127.
                # IPv6 does not support time to live so you will only see a '/'
                # for multicast addresses.
                if "/" in d[2]:
                    if d[1] == "IP6":
                        self.body[header].append(
                            {
                                "network_type": d[0],
                                "address_type": d[1],
                                "address": d[2].split("/")[0],
                                "ttl": None,
                                "address_count": int(d[2].split("/")[1]),
                            }
                        )
                    else:
                        address_data = d[2].split("/")
                        if len(address_data) == 2:
                            self.body[header].append(
                                {
                                    "network_type": d[0],
                                    "address_type": d[1],
                                    "address": address_data[0],
                                    "ttl": int(address_data[1]),
                                    "address_count": 1,
                                }
                            )
                        else:
                            self.body[header].append(
                                {
                                    "network_type": d[0],
                                    "address_type": d[1],
                                    "address": address_data[0],
                                    "ttl": int(address_data[1]),
                                    "address_count": int(address_data[2]),
                                }
                            )
                else:
                    self.body[header].append(
                        {
                            "network_type": d[0],
                            "address_type": d[1],
                            "address": d[2],
                            "ttl": None,
                            "address_count": 1,
                        }
                    )
            elif header == "b":
                # SDP 5.8 Bandwidth
                # b=<bwtype>:<bandwidth>
                # A bwtype of CT means Conference Total between all medias
                # and all devices in the conference.
                # A bwtype of AS means Applicaton Specific total for this
                # media and this device.
                # The bandwidth is given in kilobits per second.
                # As this was written in 2006, this could be Kibibits.
                # TODO: Implement Bandwidth restrictions
                d = data.split(":")
                self.body[header] = {"type": d[0], "bandwidth": d[1]}
            elif header == "t":
                # SDP 5.9 Timing
                # t=<start-time> <stop-time>
                d = data.split(" ")
                self.body[header] = {"start": d[0], "stop": d[1]}
            elif header == "r":
                # SDP 5.10 Repeat Times
                # r=<repeat interval> <active duration> <offsets from start-time> # noqa: E501
                d = data.split(" ")
                self.body[header] = {
                    "repeat": d[0],
                    "duration": d[1],
                    "offset1": d[2],
                    "offset2": d[3],
                }
            elif header == "z":
                # SDP 5.11 Time Zones
                # z=<adjustment time> <offset> <adjustment time> <offset> ....
                # Used for change in timezones such as day light savings time.
                d = data.split()
                amount = len(d) / 2
                self.body[header] = {}
                for x in range(int(amount)):
                    self.body[header]["adjustment-time" + str(x)] = d[x * 2]
                    self.body[header]["offset" + str(x)] = d[x * 2 + 1]
            elif header == "k":
                # SDP 5.12 Encryption Keys
                # k=<method>
                # k=<method>:<encryption key>
                if ":" in data:
                    d = data.split(":")
                    self.body[header] = {"method": d[0], "key": d[1]}
                else:
                    self.body[header] = {"method": d}  # TODO ?
            elif header == "m":
                # SDP 5.14 Media Descriptions
                # m=<media> <port>/<number of ports> <proto> <fmt> ...
                # <port> should be even, and <port>+1 should be the RTCP port.
                # <number of ports> should coinside with number of
                # addresses in SDP 5.7 c=
                if "m" not in self.body:
                    self.body["m"] = []
                d = data.split(" ")

                if "/" in d[1]:
                    ports_raw = d[1].split("/")
                    port = ports_raw[0]
                    count = int(ports_raw[1])
                else:
                    port = d[1]
                    count = 1
                methods = d[3:]

                self.body["m"].append(
                    {
                        "type": d[0],
                        "port": int(port),
                        "port_count": count,
                        "protocol": RTPProtocol(d[2]),
                        "methods": methods,
                        "attributes": {},
                    }
                )
                for x in self.body["m"][-1]["methods"]:
                    self.body["m"][-1]["attributes"][x] = {}
            elif header == "a":
                # SDP 5.13 Attributes & 6.0 SDP Attributes
                # a=<attribute>
                # a=<attribute>:<value>

                if "a" not in self.body:
                    self.body["a"] = {}

                if ":" in data:
                    d = data.split(":")
                    attribute = d[0]
                    value = d[1]
                else:
                    attribute = data
                    value = None

                if value is not None:
                    if attribute == "rtpmap":
                        # a=rtpmap:<payload type> <encoding name>/<clock rate> [/<encoding parameters>] # noqa: E501
                        v = re.split(" |/", value)
                        for t in self.body["m"]:
                            if v[0] in t["methods"]:
                                index = int(self.body["m"].index(t))
                                break
                        else:
                            raise RuntimeError('unexpected error')
                        if len(v) == 4:
                            encoding = v[3]
                        else:
                            encoding = None

                        self.body["m"][index]["attributes"][v[0]]["rtpmap"] = {
                            "id": v[0],
                            "name": v[1],
                            "frequency": v[2],
                            "encoding": encoding,
                        }

                    elif attribute == "fmtp":
                        # a=fmtp:<format> <format specific parameters>
                        d = value.split(" ")
                        for t in self.body["m"]:
                            if d[0] in t["methods"]:
                                index = int(self.body["m"].index(t))
                                break
                        else:
                            raise RuntimeError('unexpected error')

                        self.body["m"][index]["attributes"][d[0]]["fmtp"] = {
                            "id": d[0],
                            "settings": d[1:],
                        }
                    else:
                        self.body["a"][attribute] = value
                else:
                    if (
                        attribute == "recvonly"
                        or attribute == "sendrecv"
                        or attribute == "sendonly"
                        or attribute == "inactive"
                    ):
                        self.body["a"][
                            "transmit_type"
                        ] = TransmitType(
                            attribute
                        )  # noqa: E501
            else:
                self.body[header] = data

        else:
            self.body[header] = data

    @staticmethod
    def parse_raw_header(
        headers_raw: list[bytes], handle: Callable[[str, str], None]
    ) -> None:
        headers: dict[str, Any] = {"Via": []}
        # Only use first occurance of VIA header field;
        # got second VIA from Kamailio running in DOCKER
        # According to RFC 3261 these messages should be
        # discarded in a response
        for x in headers_raw:
            i = str(x, "utf8").split(": ")
            if i[0] == "Via":
                headers["Via"].append(i[1])
            if i[0] not in headers.keys():
                headers[i[0]] = i[1]

        for key, val in headers.items():
            handle(key, val)

    @staticmethod
    def parse_raw_body(
        body: bytes, handle: Callable[[str, str], None]
    ) -> None:
        if len(body) > 0:
            body_raw = body.split(b"\r\n")
            for x in body_raw:
                i = str(x, "utf8").split("=")
                if i != [""]:
                    handle(i[0], i[1])

    def parse_sip_response(self, data: bytes) -> None:
        headers, body = data.split(b"\r\n\r\n")
        headers_raw = headers.split(b"\r\n")
        self.heading = headers_raw.pop(0)
        self.version = str(self.heading.split(b" ")[0], "utf8")
        if self.version not in self.SIPCompatibleVersions:
            raise SIPParseError(f"SIP Version {self.version} not compatible.")

        self.status = SIPStatus(int(self.heading.split(b" ")[1]))

        self.parse_raw_header(headers_raw, self.parse_header)
        self.parse_raw_body(body, self.parse_body)

    def parse_sip_message(self, data: bytes) -> None:
        headers, body = data.split(b"\r\n\r\n")
        headers_raw = headers.split(b"\r\n")
        self.heading = headers_raw.pop(0)
        self.version = str(self.heading.split(b" ")[2], "utf8")
        if self.version not in self.SIPCompatibleVersions:
            raise SIPParseError(f"SIP Version {self.version} not compatible.")

        self.method = str(self.heading.split(b" ")[0], "utf8")

        self.parse_raw_header(headers_raw, self.parse_header)
        self.parse_raw_body(body, self.parse_body)


class SipFactory:
    def __init__(
            self,
            pbx_host: str,
            pbx_port: int,
            local_addr: str,
            local_port: int,
            username: str,
            password: str,
            urn_uuid: str,
            user_agent: str = 'qa auto'
    ):
        self.pbx_host = pbx_host
        self.pbx_port = pbx_port
        self.local_addr = local_addr
        self.local_port = local_port
        self.username = username
        self.password = password
        self.urn_uuid = urn_uuid
        self.user_agent = user_agent
        self.sip_compatible_methods_str = ", ".join(SIPCompatibleMethods)

    def _gen_response_via_header(self, request: SIPMessage) -> str:
        via = ""
        for i, h_via in enumerate(request.headers["Via"], 1):
            # if len(request.headers["Via"]) ==
            v_line = (
                "Via: SIP/2.0/UDP "
                + f'{h_via["address"][0]}:{h_via["address"][1]}'
            )
            if "branch" in h_via.keys():
                v_line += f';branch={h_via["branch"]}'
            if "rport" in h_via.keys():
                if h_via["rport"] is not None:
                    v_line += f';rport={h_via["rport"]}'
                else:
                    v_line += ";rport"
            if "received" in h_via.keys():
                v_line += f';received={h_via["received"]}'
            v_line += "\r\n"
            via += v_line
        return via

    def gen_authorization(self, realm, method, nonce, invite: bool = False) -> str:
        if not invite:
            HA1 = self.username + ":" + realm + ":" + self.password
            HA1 = hashlib.md5(HA1.encode("utf8")).hexdigest()
            HA2 = f"{method}:sip:{self.pbx_host};transport=UDP"
            HA2 = hashlib.md5(HA2.encode("utf8")).hexdigest()
            authhash = (HA1 + ":" + nonce + ":" + HA2).encode("utf8")
            authhash = hashlib.md5(authhash).hexdigest().encode("utf8")
            return (
                    f'Authorization: Digest username="{self.username}",realm='
                    + f'"{realm}",nonce="{nonce}",uri="sip:{self.pbx_host};'
                    + f'transport=UDP",response="{str(authhash, "utf8")}",'
                    + "algorithm=MD5\r\n"
            )
        else:
            HA1 = self.username + ":" + realm + ":" + self.password
            HA1 = hashlib.md5(HA1.encode("utf8")).hexdigest()
            HA2 = f"{method}:sip:79966973573##4859776863@{self.pbx_host}"
            HA2 = hashlib.md5(HA2.encode("utf8")).hexdigest()
            authhash = (HA1 + ":" + nonce + ":" + HA2).encode("utf8")
            authhash = hashlib.md5(authhash).hexdigest().encode("utf8")
            return (
                    f'Authorization: Digest username="{self.username}",realm='
                    + f'"{realm}",nonce="{nonce}",uri="sip:79966973573##4859776863@{self.pbx_host}",response="{str(authhash, "utf8")}",'
                    + "algorithm=MD5\r\n"
            )

    def gen_register(
            self,
            expires: int,
            branch: str,
            tag: str,
            call_id: str,
            cseq: int,
            authorization: Optional[dict[str, str]] = None
    ) -> str:
        if authorization:
            authorization_data = self.gen_authorization(
                authorization['realm'],
                'REGISTER',
                authorization['nonce']
            )

        regRequest = f"REGISTER sip:{self.pbx_host} SIP/2.0\r\n"
        regRequest += (
            f"Via: SIP/2.0/UDP {self.local_addr}:{self.local_port};"
            + f"branch={branch};rport\r\n"
        )
        regRequest += (
            f'From: "{self.username}" '
            + f"<sip:{self.username}@{self.pbx_host}>;tag="
            + f'{tag}\r\n'
        )
        regRequest += (
            f'To: "{self.username}" '
            + f"<sip:{self.username}@{self.pbx_host}>\r\n"
        )
        regRequest += f"Call-ID: {call_id}\r\n"
        regRequest += f"CSeq: {cseq} REGISTER\r\n"
        regRequest += (
            "Contact: "
            + f"<sip:{self.username}@{self.local_addr}:{self.local_port};"
            + "transport=UDP>;+sip.instance="
            + f'"<urn:uuid:{self.urn_uuid}>"\r\n'
        )
        regRequest += f'Allow: {self.sip_compatible_methods_str}\r\n'
        regRequest += "Max-Forwards: 70\r\n"
        regRequest += "Allow-Events: org.3gpp.nwinitdereg\r\n"
        regRequest += f"User-Agent: {self.user_agent}\r\n"
        regRequest += f"Expires: {expires}\r\n"
        if authorization:
            regRequest += authorization_data  # noqa
        regRequest += "Content-Length: 0"
        regRequest += "\r\n\r\n"

        return regRequest

    def gen_sdp(
            self,
            sess_id: int,
            media_port: int,
            available_payload: dict[int, PayloadType],
            sendtype: str
    ) -> str:
        body = "v=0\r\n"
        # TODO: Check IPv4/IPv6
        body += f"o=qa {sess_id} {sess_id} IN IP4 {self.local_addr}\r\n"
        body += f"s=qa\r\n"
        body += f"c=IN IP4 {self.local_addr}\r\n"  # TODO: Check IPv4/IPv6
        body += "t=0 0\r\n"
        body += f"m=audio {media_port} RTP/AVP"
        for payload_type in available_payload:
            body += f" {payload_type}"
        body += "\r\n"  # m=audio <port> RTP/AVP <codecs>\r\n
        for payload_type, payload_value in available_payload.items():
            body += f"a=rtpmap:{payload_type} {payload_value.description}/{payload_value.rate}\r\n"
            if str(payload_value.description) == "telephone-event":
                body += f"a=fmtp:{payload_type} 0-15\r\n"
        body += "a=ptime:20\r\n"
        body += "a=maxptime:150\r\n"
        body += f"a={sendtype}\r\n"

        return body

    def gen_invite(
            self,
            number: str,
            branch: str,
            cseq: int,
            tag: str,
            call_id: str,
            sdp: str,
            authorization: Optional[dict[str, str]] = None
    ) -> str:
        if authorization:
            authorization_data = self.gen_authorization(
                authorization['realm'],
                'INVITE',
                authorization['nonce'],
                invite=True
            )

        invRequest = f"INVITE sip:{number}@{self.pbx_host} SIP/2.0\r\n"
        invRequest += (
                f"Via: SIP/2.0/UDP {self.local_addr}:{self.local_port};branch="
                + f"{branch}\r\n"
        )
        invRequest += "Max-Forwards: 70\r\n"
        invRequest += (
                "Contact: "
                + f"<sip:{self.username}@{self.local_addr}:{self.local_port}>\r\n"
        )
        invRequest += f"To: <sip:{number}@{self.pbx_host}>\r\n"
        invRequest += f"From: <sip:{self.username}@{self.local_addr}>;tag={tag}\r\n"
        invRequest += f"Call-ID: {call_id}\r\n"
        invRequest += f"CSeq: {cseq} INVITE\r\n"
        invRequest += f"Allow: {self.sip_compatible_methods_str}\r\n"
        invRequest += "Content-Type: application/sdp\r\n"
        invRequest += f"User-Agent: qa test\r\n"
        if authorization:
            invRequest += authorization_data  # noqa
        invRequest += f"Content-Length: {len(sdp)}\r\n\r\n"
        invRequest += sdp

        return invRequest

    def gen_ack(self, request: SIPMessage, tag: Optional[str] = None) -> str:
        tag_from = request.headers['From']['tag']
        tag_to = request.headers['To']['tag']
        if not tag_to:
            # В некоторых сообщениях, например, OPTIONS, АТС присылает сообщение без тега в поле TO
            tag_to = tag
        t = re.split(r'[<>]', request.headers["To"]["raw"])[-2]

        ackMessage = f"ACK {t} SIP/2.0\r\n"
        ackMessage += self._gen_response_via_header(request)
        ackMessage += "Max-Forwards: 70\r\n"
        ackMessage += f"From: {request.headers['From']['raw']};tag={tag_from}\r\n"
        ackMessage += f"To: {request.headers['To']['raw']};tag={tag_to}\r\n"
        ackMessage += f"Call-ID: {request.headers['Call-ID']}\r\n"
        ackMessage += f"CSeq: {request.headers['CSeq']['check']} ACK\r\n"
        ackMessage += f"User-Agent: qa auto\r\n"
        ackMessage += "Content-Length: 0\r\n\r\n"

        return ackMessage

    def gen_ok(self, request: SIPMessage) -> str:
        tag_from = request.headers['From']['tag']
        tag_to = request.headers['To']['tag']

        okResponse = "SIP/2.0 200 OK\r\n"
        okResponse += self._gen_response_via_header(request)
        okResponse += f"From: {request.headers['From']['raw']};tag={tag_from}\r\n"
        okResponse += f"To: {request.headers['To']['raw']};tag={tag_to}\r\n"
        okResponse += f"Call-ID: {request.headers['Call-ID']}\r\n"
        okResponse += (
            f"CSeq: {request.headers['CSeq']['check']} "
            + f"{request.headers['CSeq']['method']}\r\n"
        )
        okResponse += f"User-Agent: qa auto\r\n"
        okResponse += f"Allow: {self.sip_compatible_methods_str}\r\n"
        okResponse += "Content-Length: 0\r\n\r\n"

        return okResponse

    def gen_bye(
            self,
            tag: str,
            invite_request: SIPMessage,
    ) -> str:
        c = invite_request.headers["Contact"].strip("<").strip(">")
        byeRequest = f"BYE {c} SIP/2.0\r\n"
        byeRequest += self._gen_response_via_header(invite_request)
        fromH = invite_request.headers["From"]["raw"]
        toH = invite_request.headers["To"]["raw"]
        if invite_request.headers["From"]["tag"] == tag:
            byeRequest += f"From: {fromH};tag={tag}\r\n"
            if invite_request.headers["To"]["tag"] != "":
                to = toH + ";tag=" + invite_request.headers["To"]["tag"]
            else:
                to = toH
            byeRequest += f"To: {to}\r\n"
        else:
            byeRequest += (
                f"To: {fromH};tag=" + f"{invite_request.headers['From']['tag']}\r\n"
            )
            byeRequest += f"From: {toH};tag={tag}\r\n"
        byeRequest += f"Call-ID: {invite_request.headers['Call-ID']}\r\n"
        cseq = int(invite_request.headers["CSeq"]["check"]) + 1
        byeRequest += f"CSeq: {cseq} BYE\r\n"
        byeRequest += (
            "Contact: "
            + f"<sip:{self.username}@{self.pbx_host}:{self.pbx_port}>\r\n"
        )
        byeRequest += f"User-Agent: qa auto\r\n"
        byeRequest += f"Allow: {self.sip_compatible_methods_str}\r\n"
        byeRequest += "Content-Length: 0\r\n\r\n"

        return byeRequest
