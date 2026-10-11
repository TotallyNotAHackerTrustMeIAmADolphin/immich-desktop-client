from notifier import Notifier
from status import Status


def make(enabled=True):
    sent = []
    status = Status()
    status.subscribe(Notifier(lambda title, message: sent.append((title, message)), enabled=lambda: enabled))
    return status, sent


def finish_a_scan(status, failing=0, uploading=0):
    status.scan_started()
    status.queue(failing + uploading)
    for i in range(uploading):
        status.upload_started(f"ok{i}.jpg")
        status.upload_finished(f"ok{i}.jpg")
    for i in range(failing):
        status.upload_started(f"bad{i}.jpg")
        status.upload_failed(f"bad{i}.jpg", "HTTP 500")
    status.scan_finished()


def test_a_catch_up_with_failures_notifies_once_with_the_counts():
    status, sent = make()

    finish_a_scan(status, failing=2, uploading=3)

    assert len(sent) == 1
    title, message = sent[0]
    assert "3 uploaded" in message and "2 failed" in message


def test_a_clean_catch_up_stays_quiet():
    status, sent = make()

    finish_a_scan(status, uploading=5)

    assert sent == []


def test_becoming_unreachable_notifies_once_not_on_every_retry():
    status, sent = make()

    status.server_unreachable()
    status.server_unreachable()
    status.server_unreachable()
    assert len(sent) == 1

    status.server_reachable()
    status.server_unreachable()
    assert len(sent) == 2


def test_single_failed_files_and_skipped_roots_do_not_notify():
    status, sent = make()
    status.scan_started()
    status.scan_finished()

    status.upload_started("live.jpg")
    status.upload_failed("live.jpg", "HTTP 500")
    status.root_skipped("E:\photos")

    assert sent == []


def test_nothing_is_sent_when_notifications_are_switched_off():
    status, sent = make(enabled=False)

    status.server_unreachable()
    finish_a_scan(status, failing=1)

    assert sent == []


def test_a_failing_notification_backend_is_harmless():
    status = Status()

    def broken(title, message):
        raise RuntimeError("no toast support")

    status.subscribe(Notifier(broken))
    status.server_unreachable()  # must not raise
