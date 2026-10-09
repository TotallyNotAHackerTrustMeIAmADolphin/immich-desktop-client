import socket

from single_instance import acquire


def free_port():
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


def test_first_instance_gets_the_lock_and_a_second_one_does_not():
    port = free_port()
    first = acquire(port)
    try:
        assert first is not None
        assert acquire(port) is None
    finally:
        first.release()


def test_lock_can_be_taken_again_after_release():
    port = free_port()
    acquire(port).release()
    again = acquire(port)
    assert again is not None
    again.release()
