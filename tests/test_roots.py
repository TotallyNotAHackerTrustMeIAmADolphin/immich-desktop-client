import shutil

from test_upload import make_photo


def test_created_file_is_recorded_under_its_watched_root(client, api, tmp_path):
    root = tmp_path / "pics"
    root.mkdir()
    client.upload_all_images([str(root)], (".jpg",))  # registers the watched roots
    photo = make_photo(root, "a.jpg")

    client.created(str(photo))

    assert client.record.get(str(photo)).root == str(root)


def test_unreachable_root_is_skipped_entirely_and_does_not_crash(client, api, tmp_path):
    root = tmp_path / "usb"
    root.mkdir()
    client.upload_all_images([str(root)], (".jpg",))
    photo = make_photo(root, "a.jpg")
    client.created(str(photo))
    shutil.rmtree(root)  # drive unplugged
    api.uploads.clear()

    client.upload_all_images([str(root)], (".jpg",))

    assert api.uploads == []
    assert client.record.get(str(photo)) is not None


def test_entries_of_roots_removed_from_config_stay_untouched(client, api, tmp_path):
    old_root, new_root = tmp_path / "old", tmp_path / "new"
    old_root.mkdir(), new_root.mkdir()
    client.upload_all_images([str(old_root)], (".jpg",))
    photo = make_photo(old_root, "a.jpg", b"v1")
    client.created(str(photo))
    photo.write_bytes(b"v2")  # changed, but its root is no longer watched
    api.uploads.clear()

    client.upload_all_images([str(new_root)], (".jpg",))

    assert api.uploads == []
    assert client.record.get(str(photo)).asset_id == "asset-1"


def test_legacy_entry_without_root_adopts_the_matching_watched_root(client, api, tmp_path):
    root = tmp_path / "pics"
    root.mkdir()
    photo = make_photo(root, "a.jpg")
    client.record.upsert(str(photo), "asset-9", "stale-sha", own_upload=False)  # as migrated: no root

    client.upload_all_images([str(root)], (".jpg",))

    entry = client.record.get(str(photo))
    assert entry.root == str(root)
    assert len(api.uploads) == 1  # checksum differed, so it was caught up


def test_move_updates_the_record_path_in_place_without_server_calls(client, api, tmp_path):
    root = tmp_path / "pics"
    root.mkdir()
    client.upload_all_images([str(root)], (".jpg",))
    photo = make_photo(root, "a.jpg")
    client.created(str(photo))
    api.uploads.clear()
    api.album_adds.clear()

    client.move(str(photo), str(root / "renamed.jpg"))

    assert client.record.get(str(photo)) is None
    moved = client.record.get(str(root / "renamed.jpg"))
    assert (moved.asset_id, moved.own_upload, moved.root) == ("asset-1", True, str(root))
    assert api.uploads == [] and api.album_adds == []
