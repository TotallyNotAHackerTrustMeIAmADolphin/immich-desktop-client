"""A minimal in-memory stand-in for the Immich REST API, patched over `requests`."""
import json

import requests


class FakeResponse:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code
        self.ok = status_code < 400
        self.text = payload if isinstance(payload, str) else json.dumps(payload)

    def json(self):
        if isinstance(self._payload, str) and getattr(self, "html", False):
            raise ValueError("not json")
        return self._payload


class FakeImmichApi:
    def __init__(self):
        self.uploads = []  # form data of every POST /assets
        self.album_targets = []  # album id of every add-to-album call
        self.album_adds = []  # asset ids added to albums
        self.next_status = "created"
        self.fail_next = []  # queue of 'raise' / 503 outcomes consumed by upcoming calls
        self.calls = 0
        self.fixed_id = None  # force every upload to resolve to this asset id
        self.upload_error = None  # (status_code, body) to simulate a failed upload
        self.version = {"major": 3, "minor": 1, "patch": 0}  # served by GET /server/version
        self.unreachable = False
        self.version_response = None  # replace the whole /server/version reply (e.g. a 404 page)
        self.copies = []  # PUT /assets/copy payloads
        self.copy_status = 204
        self.delete_status = 204
        self.deletes = []  # DELETE /assets payloads
        self.albums = []  # served by GET /albums
        self.created_albums = []
        self._counter = 0

    def __injected_failure(self):
        self.calls += 1
        if self.fail_next:
            outcome = self.fail_next.pop(0)
            if outcome == "raise":
                raise requests.exceptions.ConnectionError("flaky network")
            return FakeResponse({"message": "unavailable"}, outcome)
        return None

    def post(self, url, headers=None, data=None, files=None, **kwargs):
        assert url.endswith("/assets")
        failure = self.__injected_failure()
        if failure is not None:
            return failure
        if self.upload_error:
            return FakeResponse(self.upload_error[1], self.upload_error[0])
        self.uploads.append(dict(data))
        self._counter += 1
        asset_id = self.fixed_id or f"asset-{self._counter}"
        return FakeResponse({"id": asset_id, "status": self.next_status}, 201)

    def request(self, method, url, headers=None, data=None, **kwargs):
        failure = self.__injected_failure()
        if failure is not None:
            return failure
        if method == "PUT" and "/albums/" in url and url.endswith("/assets"):
            self.album_targets.append(url.split("/albums/")[1].split("/")[0])
            self.album_adds.extend(json.loads(data)["ids"])
            return FakeResponse([{"success": True}])
        if self.unreachable:
            raise requests.exceptions.ConnectionError("server down")
        if method == "PUT" and url.endswith("/assets/copy"):
            self.copies.append(json.loads(data))
            return FakeResponse({}, self.copy_status)
        if method == "DELETE" and url.endswith("/assets"):
            self.deletes.append(json.loads(data))
            return FakeResponse({}, self.delete_status)
        if method == "GET" and url.endswith("/server/version"):
            if self.version_response is not None:
                return self.version_response
            return FakeResponse(self.version)
        if method == "GET" and url.endswith("/albums"):
            return FakeResponse(self.albums)
        if method == "POST" and url.endswith("/albums"):
            self.created_albums.append(json.loads(data))
            return FakeResponse({"id": "new-album", **json.loads(data)}, 201)
        raise AssertionError(f"unexpected call to fake Immich API: {method} {url}")
