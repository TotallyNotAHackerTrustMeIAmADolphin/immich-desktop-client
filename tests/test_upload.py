from datetime import datetime


def test_upload_dates_are_iso8601_with_utc_offset(client, api, tmp_path):
    photo = tmp_path / "photo.jpg"
    photo.write_bytes(b"jpeg-bytes")

    client.created(str(photo))

    assert len(api.uploads) == 1
    for field in ("fileCreatedAt", "fileModifiedAt"):
        parsed = datetime.fromisoformat(api.uploads[0][field])
        assert parsed.utcoffset() is not None, f"{field} must carry a UTC offset"
