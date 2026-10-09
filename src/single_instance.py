import socket

DEFAULT_PORT = 47862  # arbitrary local port that acts as the "an instance is running" lock


class InstanceLock:
    def __init__(self, sock):
        self.__sock = sock

    def release(self):
        self.__sock.close()


def acquire(port=DEFAULT_PORT):
    """Return an InstanceLock, or None if another instance already holds the port.

    A bound local socket vanishes with the process, so a crashed instance never leaves a stale lock.
    """
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):  # Windows: make a second bind fail instead of sharing the port
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
    try:
        sock.bind(("127.0.0.1", port))
    except OSError:
        sock.close()
        return None
    return InstanceLock(sock)
