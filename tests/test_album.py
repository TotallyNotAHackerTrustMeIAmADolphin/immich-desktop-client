import immich


def make(api, tmp_path):
    return immich.Immich("http://immich.test/api", "key", album_name="laptop", shelve_path=str(tmp_path / "s"))


def test_finds_own_album_by_name_ignoring_shared_namesakes(api, tmp_path):
    api.albums = [
        {"id": "shared-one", "albumName": "laptop", "isOwned": False},
        {"id": "mine", "albumName": "laptop", "isOwned": True},
    ]
    client = make(api, tmp_path)
    assert api.created_albums == []
    assert client._Immich__album_id == "mine"


def test_creates_album_when_none_owned_and_uses_its_id(api, tmp_path):
    api.albums = [{"id": "shared-one", "albumName": "laptop", "isOwned": False}]
    client = make(api, tmp_path)
    assert len(api.created_albums) == 1
    assert client._Immich__album_id == "new-album"
