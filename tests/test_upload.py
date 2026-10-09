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
    assert client.record.get(str(photo)) is None


def make_photo(tmp_path, name="photo.jpg", content=b"jpeg-bytes"):
    photo = tmp_path / name
    photo.write_bytes(content)
    return photo


def test_created_upload_is_recorded_as_own_upload(client, api, tmp_path):
    photo = make_photo(tmp_path)
    client.created(str(photo))

    entry = client.record.get(str(photo))
    assert entry.asset_id == "asset-1" and entry.own_upload is True


def test_duplicate_upload_is_recorded_but_never_as_own_upload(client, api, tmp_path):
    api.next_status = "duplicate"
    photo = make_photo(tmp_path)
    client.created(str(photo))

    entry = client.record.get(str(photo))
    assert entry.asset_id == "asset-1" and entry.own_upload is False
    assert api.album_adds == ["asset-1"]  # still filed into the album


def test_upload_carries_ownership_hint_metadata(client, api, tmp_path):
    import json
    client.created(str(make_photo(tmp_path)))

    metadata = json.loads(api.uploads[0]["metadata"])
    assert [item["key"] for item in metadata] == ["immich-desktop-client"]


def test_catch_up_uploads_new_and_changed_files_but_not_unchanged(client, api, tmp_path):
    unchanged = make_photo(tmp_path, "same.jpg", b"same")
    changed = make_photo(tmp_path, "edited.jpg", b"v1")
    client.created(str(unchanged))
    client.created(str(changed))
    changed.write_bytes(b"v2")
    new = make_photo(tmp_path, "new.JPG", b"new")
    api.uploads.clear()

    client.upload_all_images([str(tmp_path)], (".jpg",))

    assert len(api.uploads) == 2  # edited + new, not the unchanged one


def test_catch_up_never_touches_record_of_files_missing_from_disk(client, api, tmp_path):
    gone = make_photo(tmp_path)
    client.created(str(gone))
    gone.unlink()

    client.upload_all_images([str(tmp_path)], (".jpg",))

    assert client.record.get(str(gone)) is not None
