from progress_window import view_model
from status import Status


def uploading_snapshot(done, total, current="a.jpg"):
    status = Status()
    status.scan_started()
    status.queue(total)
    for i in range(done):
        status.upload_started(f"done{i}.jpg")
        status.upload_finished(f"done{i}.jpg")
    status.upload_started(current)
    return status.snapshot()


def test_uploading_shows_a_determinate_bar_with_the_current_file():
    view = view_model(uploading_snapshot(done=12, total=340, current="/pics/x.jpg"))

    assert view.headline == "Uploading 13 of 340"
    assert view.mode == "determinate"
    assert abs(view.fraction - 12 / 340) < 1e-9
    assert view.current_file == "/pics/x.jpg"


def test_scanning_without_a_known_total_is_an_indeterminate_bar():
    status = Status()
    status.scan_started()

    view = view_model(status.snapshot())

    assert view.headline == "Catching up"
    assert view.mode == "indeterminate"
    assert view.current_file == ""


def test_idle_and_paused_show_an_empty_bar_and_no_file():
    status = Status()
    status.scan_started()
    status.scan_finished()

    view = view_model(status.snapshot())

    assert (view.headline, view.mode, view.fraction) == ("Idle", "idle", 0.0)


def test_failures_become_one_readable_row_each():
    status = Status()
    status.upload_failed("/pics/bad.jpg", "server answered HTTP 400")

    view = view_model(status.snapshot())

    assert view.failures == ["/pics/bad.jpg  -  server answered HTTP 400"]
    assert "1 failed" in view.headline
