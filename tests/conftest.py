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
    return immich.Immich("http://immich.test/api", "key", album_name="test", album_id="album-1",
                         record_path=str(tmp_path / "record.sqlite"))
