from status import State
from test_upload import make_photo


def failing_catch_up(client, api, tmp_path):
    root = tmp_path / "pics"
    root.mkdir()
    photo = make_photo(root)
    api.upload_error = (400, {"message": "bad file"})
    client.upload_all_images([str(root)], (".jpg",))
    return root, photo


def test_retry_uploads_what_failed_and_empties_the_failure_list(client, api, tmp_path):
    root, photo = failing_catch_up(client, api, tmp_path)
    assert client.status.snapshot().failed == 1
    api.upload_error = None

    started = client.retry_failed((".jpg",))

    assert started is True
    assert client.status.snapshot().failed == 0
    assert client.record.get(str(photo)) is not None


def test_retry_that_fails_again_lists_the_file_again(client, api, tmp_path):
    root, photo = failing_catch_up(client, api, tmp_path)

    client.retry_failed((".jpg",))

    snap = client.status.snapshot()
    assert snap.failed == 1 and snap.failures[0][0] == str(photo)


def test_a_failed_file_that_is_gone_by_retry_time_just_disappears_from_the_list(client, api, tmp_path):
    root, photo = failing_catch_up(client, api, tmp_path)
    photo.unlink()

    client.retry_failed((".jpg",))

    assert client.status.snapshot().failed == 0


def test_retry_does_nothing_while_a_scan_is_running(client, api, tmp_path):
    root, photo = failing_catch_up(client, api, tmp_path)
    client.status.scan_started()

    assert client.retry_failed((".jpg",)) is False
    assert client.status.snapshot().failed == 1
    assert client.status.snapshot().state is State.CATCHING_UP


def test_retry_before_any_catch_up_has_nothing_to_scan(client):
    assert client.retry_failed((".jpg",)) is False
