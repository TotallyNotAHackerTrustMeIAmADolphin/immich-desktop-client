import pytest

import immich
from fake_immich import FakeImmichApi


@pytest.fixture
def api(monkeypatch):
    fake = FakeImmichApi()
    monkeypatch.setattr(immich.requests, "post", fake.post)
    monkeypatch.setattr(immich.requests, "request", fake.request)
    return fake


@pytest.fixture
def client(api, tmp_path):
    # device_id and album_id given explicitly so construction makes no network or wmic calls
    return immich.Immich("http://immich.test/api", "key", album_name="test", album_id="album-1",
                         device_id="device-1", shelve_path=str(tmp_path / "shelve"))
