"""Integration tests against a DISPOSABLE Immich 3.1 server. Never point these at your real library.

Not part of CI. To run (see docs/releasing.md):

    IMMICH_TEST_URL=http://localhost:2283/api python -m pytest tests/integration

On a brand-new server the first run signs up an admin and creates an API key by itself. To reuse an
existing disposable server set IMMICH_TEST_API_KEY as well.

NOTE: written without access to a live server; the first run may need small request-shape fixes.
"""
import os
import uuid

import pytest
import requests

import immich

URL = os.environ.get("IMMICH_TEST_URL")
pytestmark = pytest.mark.skipif(not URL, reason="set IMMICH_TEST_URL to a disposable Immich server")


def api_key():
    if os.environ.get("IMMICH_TEST_API_KEY"):
        return os.environ["IMMICH_TEST_API_KEY"]
    credentials = {"email": "admin@example.test", "password": "integration-test-password"}
    requests.post(f"{URL}/auth/admin-sign-up", json={**credentials, "name": "Admin"})  # fails harmlessly if done
    token = requests.post(f"{URL}/auth/login", json=credentials).json()["accessToken"]
    created = requests.post(f"{URL}/api-keys", json={"name": f"it-{uuid.uuid4().hex[:6]}", "permissions": ["all"]},
                            headers={"Authorization": f"Bearer {token}"})
    return created.json()["secret"]


@pytest.fixture(scope="module")
def key():
    return api_key()


@pytest.fixture
def client(key, tmp_path):
    album = f"it-{uuid.uuid4().hex[:8]}"
    return immich.Immich(URL, key, album_name=album, record_path=str(tmp_path / "r.sqlite"), live_delete=True)


def asset(key, asset_id):
    return requests.get(f"{URL}/assets/{asset_id}", headers={"x-api-key": key}).json()


def image(tmp_path, name, payload):
    from PIL import Image
    path = tmp_path / name
    Image.new("RGB", (8, 8), payload).save(path)
    return path


def test_supported_server_is_accepted(key):
    immich.check_server_supported(URL, key)


def test_upload_creates_an_own_upload_in_the_owned_album(client, key, tmp_path):
    photo = image(tmp_path, "a.png", (255, 0, 0))
    client.created(str(photo))

    entry = client.record.get(str(photo))
    assert entry.own_upload is True
    albums = requests.get(f"{URL}/albums", params={"isOwned": "true", "name": client.album_name},
                          headers={"x-api-key": key}).json()
    assert len(albums) == 1 and albums[0]["assetCount"] == 1


def test_replace_trashes_the_old_asset_and_keeps_the_new_one(client, key, tmp_path):
    photo = image(tmp_path, "b.png", (0, 255, 0))
    client.created(str(photo))
    old_id = client.record.get(str(photo)).asset_id
    image(tmp_path, "b.png", (0, 0, 255))

    client.modify(str(photo))

    new_id = client.record.get(str(photo)).asset_id
    assert new_id != old_id
    assert asset(key, old_id)["isTrashed"] is True
    assert asset(key, new_id)["isTrashed"] is False


def test_live_delete_moves_the_asset_to_trash_restorably(client, key, tmp_path):
    photo = image(tmp_path, "c.png", (9, 9, 9))
    client.created(str(photo))
    asset_id = client.record.get(str(photo)).asset_id

    client.delete(str(photo))

    assert asset(key, asset_id)["isTrashed"] is True  # still exists server-side, i.e. not force-deleted
    restored = requests.post(f"{URL}/trash/restore/assets", json={"ids": [asset_id]}, headers={"x-api-key": key})
    assert restored.status_code in (200, 204)
    assert asset(key, asset_id)["isTrashed"] is False
