import immich
from test_upload import make_photo


def test_delete_all_trashes_only_own_uploads_without_force(client, api, tmp_path):
    own = make_photo(tmp_path, "own.jpg", b"own")
    client.created(str(own))
    api.next_status = "duplicate"
    api.fixed_id = "someone-elses"
    dup = make_photo(tmp_path, "dup.jpg", b"dup")
    client.created(str(dup))

    trashed = client.delete_all_own_uploads()

    assert trashed == 1
    assert api.deletes == [{"ids": ["asset-1"]}]
    assert client.record.get(str(own)) is None
    assert client.record.get(str(dup)).asset_id == "someone-elses"  # untouched


def test_delete_all_works_in_batches(client, api, tmp_path, monkeypatch):
    monkeypatch.setattr(immich, "TRASH_BATCH_SIZE", 2)
    for i in range(5):
        client.created(str(make_photo(tmp_path, f"{i}.jpg", bytes([i]))))

    assert client.delete_all_own_uploads() == 5
    assert [len(d["ids"]) for d in api.deletes] == [2, 2, 1]
    assert client.record.entries() == []


def test_failed_batch_keeps_its_entries(client, api, tmp_path):
    photo = make_photo(tmp_path)
    client.created(str(photo))
    api.delete_status = 500

    assert client.delete_all_own_uploads() == 0
    assert client.record.get(str(photo)) is not None
