import immich
from status import State
from test_upload import make_photo


def test_catch_up_reports_n_of_m_and_ends_idle(client, api, tmp_path):
    root = tmp_path / "pics"
    root.mkdir()
    for name in ("a.jpg", "b.jpg", "c.jpg"):
        make_photo(root, name)
    seen = []
    client.status.subscribe(lambda snap: seen.append((snap.state, snap.text)))

    client.upload_all_images([str(root)], (".jpg",))

    texts = [text for state, text in seen if state is State.UPLOADING]
    assert texts == ["Uploading 1 of 3", "Uploading 2 of 3", "Uploading 3 of 3"]
    final = client.status.snapshot()
    assert final.state is State.IDLE and final.uploaded == 3


def test_a_failed_upload_is_listed_with_path_and_reason(client, api, tmp_path):
    api.upload_error = (500, {"message": "boom"})
    photo = make_photo(tmp_path)

    client.created(str(photo))

    snap = client.status.snapshot()
    assert snap.failed == 1
    path, reason = snap.failures[0]
    assert path == str(photo) and "500" in reason


def test_a_retried_file_that_now_uploads_leaves_the_failure_list(client, api, tmp_path):
    root = tmp_path / "pics"
    root.mkdir()
    photo = make_photo(root)
    api.upload_error = (500, {"message": "boom"})
    client.upload_all_images([str(root)], (".jpg",))
    assert client.status.snapshot().failed == 1

    api.upload_error = None
    client.upload_all_images([str(root)], (".jpg",))

    assert client.status.snapshot().failed == 0
    assert client.record.get(str(photo)) is not None


def test_retry_exhaustion_reports_unreachable_and_recovery_clears_it(client, api, tmp_path):
    api.fail_next = ["raise"] * immich.RETRY_ATTEMPTS
    client.created(str(make_photo(tmp_path, "a.jpg")))
    assert client.status.snapshot().state is State.UNREACHABLE

    client.created(str(make_photo(tmp_path, "b.jpg")))
    assert client.status.snapshot().state is not State.UNREACHABLE


def test_an_unreachable_root_is_counted_as_skipped(client, api, tmp_path):
    client.upload_all_images([str(tmp_path / "unmounted")], (".jpg",))

    snap = client.status.snapshot()
    assert snap.roots_skipped == 1
    assert snap.text == "Idle · 1 root skipped"
