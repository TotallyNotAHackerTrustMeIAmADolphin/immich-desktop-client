import pytest

import immich
from test_upload import make_photo


def test_upload_survives_transient_network_errors(client, api, tmp_path):
    api.fail_next = ["raise", 503]
    photo = make_photo(tmp_path)

    client.created(str(photo))

    assert client.record.get(str(photo)).asset_id == "asset-1"


def test_upload_gives_up_after_bounded_attempts_without_raising(client, api, tmp_path):
    api.calls = 0
    api.fail_next = ["raise"] * 20
    photo = make_photo(tmp_path)

    client.created(str(photo))

    assert client.record.get(str(photo)) is None
    assert api.calls == immich.RETRY_ATTEMPTS


def test_client_errors_are_not_retried(client, api, tmp_path):
    api.calls = 0
    api.upload_error = (400, {"message": "bad"})
    client.created(str(make_photo(tmp_path)))
    assert api.calls == 1


def test_backoff_delays_double(client, api, tmp_path, monkeypatch):
    delays = []
    monkeypatch.setattr(immich, "sleep", delays.append)
    api.fail_next = ["raise", "raise", "raise"]

    client.created(str(make_photo(tmp_path)))

    assert delays == [1, 2, 4]


def test_version_check_retries_before_declaring_server_unreachable(api, tmp_path):
    api.fail_next = ["raise"] * 20
    with pytest.raises(immich.ServerUnreachableError):
        immich.Immich("http://immich.test/api", "key", album_name="a", album_id="1",
                      record_path=str(tmp_path / "r.sqlite"))
    assert api.calls == immich.RETRY_ATTEMPTS
