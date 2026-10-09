import immich
from test_upload import make_photo


def make(api, tmp_path):
    return immich.Immich("http://immich.test/api", "key", album_name="laptop", record_path=str(tmp_path / "r.sqlite"))


def test_uploads_go_into_own_album_ignoring_shared_namesakes(api, tmp_path):
    api.albums = [
        {"id": "shared-one", "albumName": "laptop", "isOwned": False},
        {"id": "mine", "albumName": "laptop", "isOwned": True},
    ]
    client = make(api, tmp_path)
    client.created(str(make_photo(tmp_path)))

    assert api.created_albums == []
    assert api.album_targets == ["mine"]


def test_creates_album_when_none_owned_and_uses_its_id(api, tmp_path):
    api.albums = [{"id": "shared-one", "albumName": "laptop", "isOwned": False}]
    client = make(api, tmp_path)
    client.created(str(make_photo(tmp_path)))

    assert len(api.created_albums) == 1
    assert api.album_targets == ["new-album"]
