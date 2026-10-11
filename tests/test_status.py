from status import State, Status


def test_a_new_status_is_starting_and_empty():
    snap = Status().snapshot()

    assert snap.state is State.STARTING
    assert (snap.uploaded, snap.total, snap.failed, snap.roots_skipped) == (0, 0, 0, 0)
    assert snap.text == "Starting"


def test_catching_up_then_uploading_n_of_m_then_idle():
    status = Status()
    status.scan_started()
    assert status.snapshot().state is State.CATCHING_UP

    status.queue(3)
    status.upload_started("a.jpg")
    snap = status.snapshot()
    assert snap.state is State.UPLOADING
    assert snap.text == "Uploading 1 of 3"
    assert snap.current_file == "a.jpg"

    status.upload_finished("a.jpg")
    status.upload_started("b.jpg")
    status.upload_finished("b.jpg")
    status.upload_started("c.jpg")
    status.upload_finished("c.jpg")
    status.scan_finished()

    snap = status.snapshot()
    assert snap.state is State.IDLE
    assert snap.uploaded == 3
    assert snap.current_file is None


def test_a_live_upload_without_a_scan_counts_as_one_of_one():
    status = Status()
    status.scan_started()
    status.scan_finished()

    status.upload_started("new.jpg")
    assert status.snapshot().text == "Uploading 1 of 1"
    status.upload_finished("new.jpg")

    assert status.snapshot().state is State.IDLE


def test_failures_are_listed_counted_and_cleared_by_a_later_success():
    status = Status()
    status.scan_started()
    status.scan_finished()

    status.upload_started("bad.jpg")
    status.upload_failed("bad.jpg", "HTTP 500")
    snap = status.snapshot()
    assert snap.failed == 1
    assert snap.failures == [("bad.jpg", "HTTP 500")]
    assert snap.text == "Idle · 1 failed"

    status.upload_started("bad.jpg")
    status.upload_finished("bad.jpg")
    assert status.snapshot().failed == 0


def test_the_failure_list_is_capped_but_the_count_is_not():
    status = Status()
    for i in range(250):
        status.upload_failed(f"{i}.jpg", "boom")

    snap = status.snapshot()
    assert snap.failed == 250
    assert len(snap.failures) == 200
    assert snap.failures[-1][0] == "249.jpg"


def test_state_priority_is_refused_then_unreachable_then_busy_then_paused_then_idle():
    status = Status()
    status.scan_started()
    status.scan_finished()
    status.set_paused(True)
    assert status.snapshot().state is State.PAUSED

    status.upload_started("a.jpg")
    assert status.snapshot().state is State.UPLOADING

    status.server_unreachable()
    assert status.snapshot().state is State.UNREACHABLE

    status.refused("server is too old")
    snap = status.snapshot()
    assert snap.state is State.REFUSED
    assert snap.text == "Refused: server is too old"

    status.server_reachable()
    assert status.snapshot().state is State.REFUSED  # refusal is final for the session


def test_roots_skipped_are_counted_once_per_root_and_reset_by_a_new_scan():
    status = Status()
    status.scan_started()
    status.root_skipped("E:\photos")
    status.root_skipped("E:\photos")
    status.root_skipped("F:\more")
    status.scan_finished()

    snap = status.snapshot()
    assert snap.roots_skipped == 2
    assert snap.text == "Idle · 2 roots skipped"

    status.scan_started()
    assert status.snapshot().roots_skipped == 0


def test_listeners_get_a_snapshot_on_every_change_and_a_broken_one_is_harmless():
    status = Status()
    seen = []
    status.subscribe(lambda snap: (_ for _ in ()).throw(RuntimeError("broken listener")))
    status.subscribe(lambda snap: seen.append(snap.state))

    status.scan_started()
    status.scan_finished()

    assert seen == [State.CATCHING_UP, State.IDLE]
