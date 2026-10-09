"""A minimal in-memory stand-in for the Immich REST API, patched over `requests`."""
import json

import requests


class FakeResponse:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code
        self.ok = status_code < 400
        self.text = json.dumps(payload)

    def json(self):
        return self._payload


class FakeImmichApi:
    def __init__(self):
        self.uploads = []  # form data of every POST /assets
        self.album_adds = []  # asset ids added to albums
        self.next_status = "created"
        self.upload_error = None  # (status_code, body) to simulate a failed upload
        self.version = {"major": 3, "minor": 1, "patch": 0}  # served by GET /server/version
        self.unreachable = False
        self.albums = []  # served by GET /albums
        self.created_albums = []
        self._counter = 0

    def post(self, url, headers=None, data=None, files=None, **kwargs):
        assert url.endswith("/assets")
        if self.upload_error:
            return FakeResponse(self.upload_error[1], self.upload_error[0])
        self.uploads.append(dict(data))
        self._counter += 1
        return FakeResponse({"id": f"asset-{self._counter}", "status": self.next_status}, 201)

    def request(self, method, url, headers=None, data=None, **kwargs):
        if method == "PUT" and "/albums/" in url and url.endswith("/assets"):
            self.album_adds.extend(json.loads(data)["ids"])
            return FakeResponse([{"success": True}])
        if self.unreachable:
            raise requests.exceptions.ConnectionError("server down")
        if method == "GET" and url.endswith("/server/version"):
            return FakeResponse(self.version)
        if method == "GET" and url.endswith("/albums"):
            return FakeResponse(self.albums)
        if method == "POST" and url.endswith("/albums"):
            self.created_albums.append(json.loads(data))
            return FakeResponse({"id": "new-album", **json.loads(data)}, 201)
        raise AssertionError(f"unexpected call to fake Immich API: {method} {url}")
