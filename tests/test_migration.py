import shelve

from record import UploadRecord, migrate_legacy_shelve


def make_shelve(path, mapping):
    with shelve.open(str(path), flag="c") as db:
        for key, value in mapping.items():
            db[key] = value


def test_entries_migrate_with_own_upload_forced_false(tmp_path):
    make_shelve(tmp_path / "shelve", {"/a.jpg": ["asset-1", "sha-a"], "/b.jpg": ["asset-2", "sha-b"]})
    record = UploadRecord(tmp_path / "r.sqlite")

    assert migrate_legacy_shelve(tmp_path / "shelve", record) == 2

    entry = record.get("/a.jpg")
    assert (entry.asset_id, entry.checksum, entry.own_upload) == ("asset-1", "sha-a", False)
    assert record.get("/b.jpg").own_upload is False


def test_migration_is_idempotent_and_never_overwrites_newer_entries(tmp_path):
    make_shelve(tmp_path / "shelve", {"/a.jpg": ["old-asset", "old-sha"]})
    record = UploadRecord(tmp_path / "r.sqlite")
    record.upsert("/a.jpg", "new-asset", "new-sha", own_upload=True)

    assert migrate_legacy_shelve(tmp_path / "shelve", record) == 0

    entry = record.get("/a.jpg")
    assert (entry.asset_id, entry.own_upload) == ("new-asset", True)


def test_missing_shelve_is_a_no_op(tmp_path):
    record = UploadRecord(tmp_path / "r.sqlite")
    assert migrate_legacy_shelve(tmp_path / "no-such-shelve", record) == 0
    assert record.entries() == []


def test_malformed_values_are_skipped_not_fatal(tmp_path):
    make_shelve(tmp_path / "shelve", {"/bad.jpg": "not-a-list", "/ok.jpg": ["asset-1", "sha"]})
    record = UploadRecord(tmp_path / "r.sqlite")

    assert migrate_legacy_shelve(tmp_path / "shelve", record) == 1
    assert record.get("/bad.jpg") is None
