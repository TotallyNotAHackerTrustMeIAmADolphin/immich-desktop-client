from test_upload import make_photo


def uploaded(client, tmp_path, content=b"v1"):
    photo = make_photo(tmp_path, "a.jpg", content)
    client.created(str(photo))
    return photo


def test_modified_own_upload_is_replaced_copy_then_trash(client, api, tmp_path):
    photo = uploaded(client, tmp_path)
    photo.write_bytes(b"v2")

    client.modify(str(photo))

    assert len(api.uploads) == 2
    assert api.copies == [{"sourceId": "asset-1", "targetId": "asset-2"}]
    assert api.deletes == [{"ids": ["asset-1"]}]  # trash only: no force flag at all
    entry = client.record.get(str(photo))
    assert (entry.asset_id, entry.own_upload) == ("asset-2", True)


def test_unchanged_checksum_does_nothing(client, api, tmp_path):
    photo = uploaded(client, tmp_path)
    photo.write_bytes(b"v1")  # touched, same content
    api.uploads.clear()

    client.modify(str(photo))

    assert api.uploads == [] and api.copies == [] and api.deletes == []


def test_modified_duplicate_upload_is_never_copied_over_or_trashed(client, api, tmp_path):
    api.next_status = "duplicate"
    photo = uploaded(client, tmp_path)  # recorded as NOT an own upload
    photo.write_bytes(b"v2")
    api.next_status = "created"

    client.modify(str(photo))

    assert len(api.uploads) == 2
    assert api.copies == [] and api.deletes == []
    assert client.record.get(str(photo)).asset_id == "asset-2"


def test_replace_resolving_to_the_same_asset_is_not_trashed(client, api, tmp_path):
    photo = uploaded(client, tmp_path)
    photo.write_bytes(b"v2")
    api.next_status = "duplicate"
    api.fixed_id = "asset-1"  # server says the new content already is asset-1

    client.modify(str(photo))

    assert api.deletes == [] and api.copies == []


def test_replace_whose_upload_fails_leaves_everything_alone(client, api, tmp_path):
    photo = uploaded(client, tmp_path)
    photo.write_bytes(b"v2")
    api.upload_error = (500, {"message": "boom"})

    client.modify(str(photo))

    assert api.copies == [] and api.deletes == []
    assert client.record.get(str(photo)).asset_id == "asset-1"


def test_catch_up_replaces_changed_own_uploads(client, api, tmp_path):
    root = tmp_path / "pics"
    root.mkdir()
    client.upload_all_images([str(root)], (".jpg",))
    photo = uploaded(client, root)
    photo.write_bytes(b"v2")

    client.upload_all_images([str(root)], (".jpg",))

    assert api.deletes == [{"ids": ["asset-1"]}]


def test_modify_of_unrecorded_file_is_a_plain_upload(client, api, tmp_path):
    photo = make_photo(tmp_path)
    client.modify(str(photo))
    assert len(api.uploads) == 1 and api.deletes == []
