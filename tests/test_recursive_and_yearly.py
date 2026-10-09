import os

import immich
from test_upload import make_photo


def build(tmp_path, **options):
    return immich.Immich("http://immich.test/api", "key", album_name="laptop", album_id="main",
                         record_path=str(tmp_path / "r.sqlite"), **options)


def test_recursive_scan_uploads_nested_files(api, tmp_path):
    root = tmp_path / "pics"
    (root / "2020" / "trip").mkdir(parents=True)
    make_photo(root, "top.jpg")
    make_photo(root / "2020" / "trip", "deep.jpg", b"deep")

    build(tmp_path, recursive=True).upload_all_images([str(root)], (".jpg",))

    assert len(api.uploads) == 2


def test_non_recursive_scan_stays_in_the_top_folder(api, tmp_path):
    root = tmp_path / "pics"
    (root / "sub").mkdir(parents=True)
    make_photo(root, "top.jpg")
    make_photo(root / "sub", "deep.jpg", b"deep")

    build(tmp_path, recursive=False).upload_all_images([str(root)], (".jpg",))

    assert len(api.uploads) == 1


def set_year(photo, year):
    stamp = __import__("datetime").datetime(year, 6, 15, 12).timestamp()
    os.utime(photo, (stamp, stamp))


def test_album_by_year_files_each_asset_into_its_year_album(api, tmp_path):
    api.albums = [{"id": "album-2020", "albumName": "laptop 2020", "isOwned": True}]
    client = build(tmp_path, album_by_year=True)
    a = make_photo(tmp_path, "a.jpg", b"a")
    b = make_photo(tmp_path, "b.jpg", b"b")
    set_year(a, 2020)
    set_year(b, 2021)

    client.created(str(a))
    client.created(str(b))

    assert [item["albumName"] for item in api.created_albums] == ["laptop 2021"]  # 2020 already existed
    assert api.album_targets == ["album-2020", "new-album"]


def test_year_albums_are_created_once_per_year(api, tmp_path):
    client = build(tmp_path, album_by_year=True)
    for name, content in (("a.jpg", b"a"), ("b.jpg", b"b")):
        photo = make_photo(tmp_path, name, content)
        set_year(photo, 2022)
        client.created(str(photo))

    assert len(api.created_albums) == 1
