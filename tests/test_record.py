from record import UploadRecord


def test_unknown_path_has_no_entry(tmp_path):
    assert UploadRecord(tmp_path / "r.sqlite").get("/a.jpg") is None


def test_upsert_then_get_round_trips_and_persists(tmp_path):
    db = tmp_path / "r.sqlite"
    UploadRecord(db).upsert("/a.jpg", "asset-1", "sha", own_upload=True)

    entry = UploadRecord(db).get("/a.jpg")  # fresh instance: proves persistence

    assert (entry.path, entry.asset_id, entry.checksum, entry.own_upload) == ("/a.jpg", "asset-1", "sha", True)


def test_upsert_replaces_existing_entry(tmp_path):
    record = UploadRecord(tmp_path / "r.sqlite")
    record.upsert("/a.jpg", "asset-1", "sha1", own_upload=True)
    record.upsert("/a.jpg", "asset-2", "sha2", own_upload=False)

    entry = record.get("/a.jpg")
    assert (entry.asset_id, entry.checksum, entry.own_upload) == ("asset-2", "sha2", False)
    assert len(record.entries()) == 1


def test_remove_deletes_entry_and_ignores_unknown(tmp_path):
    record = UploadRecord(tmp_path / "r.sqlite")
    record.upsert("/a.jpg", "asset-1", "sha", own_upload=True)
    record.remove("/a.jpg")
    record.remove("/never-there.jpg")
    assert record.get("/a.jpg") is None


def test_root_is_stored_and_can_be_adopted_later(tmp_path):
    record = UploadRecord(tmp_path / "r.sqlite")
    record.upsert("/a.jpg", "asset-1", "sha", own_upload=False)
    assert record.get("/a.jpg").root is None

    record.set_root("/a.jpg", "/")
    assert record.get("/a.jpg").root == "/"
