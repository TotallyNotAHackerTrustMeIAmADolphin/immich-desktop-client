from test_upload import make_photo


def test_live_delete_trashes_own_upload_without_force_and_forgets_it(deleting_client, api, tmp_path):
    photo = make_photo(tmp_path)
    deleting_client.created(str(photo))

    deleting_client.delete(str(photo))

    assert api.deletes == [{"ids": ["asset-1"]}]
    assert deleting_client.record.get(str(photo)) is None


def test_live_delete_never_trashes_a_duplicate(deleting_client, api, tmp_path):
    api.next_status = "duplicate"
    photo = make_photo(tmp_path)
    deleting_client.created(str(photo))

    deleting_client.delete(str(photo))

    assert api.deletes == []
    assert deleting_client.record.get(str(photo)) is None


def test_live_delete_is_off_by_default(client, api, tmp_path):
    photo = make_photo(tmp_path)
    client.created(str(photo))

    client.delete(str(photo))

    assert api.deletes == []
    assert client.record.get(str(photo)) is None


def test_failed_trash_keeps_the_record_entry(deleting_client, api, tmp_path):
    photo = make_photo(tmp_path)
    deleting_client.created(str(photo))
    api.delete_status = 500

    deleting_client.delete(str(photo))

    assert deleting_client.record.get(str(photo)) is not None


def test_delete_of_unrecorded_file_is_a_no_op(deleting_client, api, tmp_path):
    deleting_client.delete(str(tmp_path / "never-uploaded.jpg"))
    assert api.deletes == []


def test_live_delete_matches_a_startup_upload_when_watchdog_mixes_slashes(deleting_client, api, tmp_path):
    photo = make_photo(tmp_path)
    deleting_client.upload_all_images([str(tmp_path).replace("\\", "/")], (".jpg", ".png"))  # recorded via os.walk
    mixed = str(tmp_path).replace("\\", "/") + "\\" + photo.name  # what watchdog reports for a "C:/dir" watch

    deleting_client.delete(mixed)

    assert api.deletes == [{"ids": ["asset-1"]}]
    assert deleting_client.record.get(str(photo)) is None
