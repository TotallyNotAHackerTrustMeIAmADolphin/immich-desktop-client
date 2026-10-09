import os
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


def test_drive_style_root_ending_in_a_separator_still_matches(client, api, tmp_path):
    drive_root = tmp_path.anchor  # "/" on POSIX, "C:\\" on Windows
    client.upload_all_images([drive_root], (".jpg",))
    photo = make_photo(tmp_path, "a.jpg")
    client.created(str(photo))
    assert client.record.get(str(photo)).root == os.path.normpath(drive_root)


def test_root_matching_ignores_case_where_the_filesystem_does(client, api, tmp_path, monkeypatch):
    import os
    monkeypatch.setattr(os.path, "normcase", lambda p: p.lower())  # as on Windows
    root = tmp_path / "Pics"
    root.mkdir()
    client.upload_all_images([str(root)], (".jpg",))
    photo = make_photo(root, "a.jpg")
    client.created(str(photo))
    api.uploads.clear()

    lowercase_destination = str(root / "b.jpg").replace("Pics", "pics")  # event paths may differ in case
    client.move(str(photo), lowercase_destination)

    assert client.record.get(lowercase_destination).root == str(root)


def test_moving_a_folder_rewrites_every_path_under_it(client, api, tmp_path):
    root = tmp_path / "pics"
    (root / "old").mkdir(parents=True)
    client.upload_all_images([str(root)], (".jpg",))
    a = make_photo(root / "old", "a.jpg", b"a")
    b = make_photo(root, "b.jpg", b"b")
    client.created(str(a))
    client.created(str(b))
    api.uploads.clear()

    client.move_folder(str(root / "old"), str(root / "new"))

    assert client.record.get(str(a)) is None
    moved = client.record.get(str(root / "new" / "a.jpg"))
    assert (moved.asset_id, moved.own_upload, moved.root) == ("asset-1", True, str(root))
    assert client.record.get(str(b)) is not None  # sibling untouched
    assert api.uploads == [] and api.deletes == []


def test_folder_name_prefix_does_not_catch_siblings(client, api, tmp_path):
    root = tmp_path / "pics"
    (root / "trip").mkdir(parents=True)
    (root / "trip2").mkdir()
    client.upload_all_images([str(root)], (".jpg",))
    sibling = make_photo(root / "trip2", "x.jpg")
    client.created(str(sibling))

    client.move_folder(str(root / "trip"), str(root / "moved"))

    assert client.record.get(str(sibling)) is not None
