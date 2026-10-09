import shutil

import immich
from test_upload import make_photo


def build(api, tmp_path, catch_up_delete):
    return immich.Immich("http://immich.test/api", "key", album_name="t", album_id="a",
                         record_path=str(tmp_path / "r.sqlite"), catch_up_delete=catch_up_delete)


def setup_uploaded(client, tmp_path):
    root = tmp_path / "pics"
    root.mkdir()
    client.upload_all_images([str(root)], (".jpg",))
    photo = make_photo(root, "a.jpg")
    client.created(str(photo))
    return root, photo


def test_catch_up_delete_trashes_own_upload_missing_from_an_accessible_root(api, tmp_path):
    client = build(api, tmp_path, True)
    root, photo = setup_uploaded(client, tmp_path)
    photo.unlink()

    client.upload_all_images([str(root)], (".jpg",))

    assert api.deletes == [{"ids": ["asset-1"]}]
    assert client.record.get(str(photo)) is None


def test_catch_up_delete_is_off_by_default(api, tmp_path):
    client = build(api, tmp_path, False)
    root, photo = setup_uploaded(client, tmp_path)
    photo.unlink()

    client.upload_all_images([str(root)], (".jpg",))

    assert api.deletes == []
    assert client.record.get(str(photo)) is not None


def test_catch_up_delete_never_acts_on_an_unreachable_root(api, tmp_path):
    client = build(api, tmp_path, True)
    root, photo = setup_uploaded(client, tmp_path)
    shutil.rmtree(root)  # unmounted drive

    client.upload_all_images([str(root)], (".jpg",))

    assert api.deletes == []
    assert client.record.get(str(photo)) is not None


def test_catch_up_delete_never_trashes_duplicates_but_forgets_them(api, tmp_path):
    api.next_status = "duplicate"
    client = build(api, tmp_path, True)
    root, photo = setup_uploaded(client, tmp_path)
    photo.unlink()

    client.upload_all_images([str(root)], (".jpg",))

    assert api.deletes == []
    assert client.record.get(str(photo)) is None


def test_failed_trash_keeps_the_entry_for_the_next_startup(api, tmp_path):
    client = build(api, tmp_path, True)
    root, photo = setup_uploaded(client, tmp_path)
    photo.unlink()
    api.delete_status = 500

    client.upload_all_images([str(root)], (".jpg",))

    assert client.record.get(str(photo)) is not None
