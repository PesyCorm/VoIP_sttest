import socket
from typing import Optional


def get_available_socket(connected: bool = False, host: Optional[str] = None, port: Optional[int] = None) -> socket.socket:
    """Get available socket.
    :return: tuple[port, socket instance]
    """
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(('', 0))
    if connected:
        assert host, 'If "connected" is True, you must pass the host'
        assert port, 'if "connected" is True, you must pass the port'
        sock.connect((host, port))
    return sock
