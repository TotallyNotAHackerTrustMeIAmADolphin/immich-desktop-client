from datetime import datetime


def test_upload_dates_are_iso8601_with_utc_offset(client, api, tmp_path):
    photo = tmp_path / "photo.jpg"
    photo.write_bytes(b"jpeg-bytes")

    client.created(str(photo))

    assert len(api.uploads) == 1
    for field in ("fileCreatedAt", "fileModifiedAt"):
        parsed = datetime.fromisoformat(api.uploads[0][field])
        assert parsed.utcoffset() is not None, f"{field} must carry a UTC offset"


def test_upload_omits_dropped_device_fields(client, api, tmp_path):
    photo = tmp_path / "photo.jpg"
    photo.write_bytes(b"jpeg-bytes")

    client.created(str(photo))

    assert "deviceId" not in api.uploads[0]
    assert "deviceAssetId" not in api.uploads[0]


def test_failed_upload_is_survived_and_not_recorded(client, api, tmp_path):
    api.upload_error = (500, {"message": "boom"})
    photo = tmp_path / "photo.jpg"
    photo.write_bytes(b"jpeg-bytes")

    client.created(str(photo))  # must not raise: an exception would kill the watcher thread

    assert api.album_adds == []
    assert not (tmp_path / "shelve").exists() and not list(tmp_path.glob("shelve*"))
