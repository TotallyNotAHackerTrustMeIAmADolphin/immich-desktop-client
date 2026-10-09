"""A minimal in-memory stand-in for the Immich REST API, patched over `requests`."""
import json


class FakeResponse:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code
        self.text = json.dumps(payload)

    def json(self):
        return self._payload


class FakeImmichApi:
    def __init__(self):
        self.uploads = []  # form data of every POST /assets
        self.album_adds = []  # asset ids added to albums
        self.next_status = "created"
        self._counter = 0

    def post(self, url, headers=None, data=None, files=None, **kwargs):
        assert url.endswith("/assets")
        self.uploads.append(dict(data))
        self._counter += 1
        return FakeResponse({"id": f"asset-{self._counter}", "status": self.next_status}, 201)

    def request(self, method, url, headers=None, data=None, **kwargs):
        if method == "PUT" and "/albums/" in url and url.endswith("/assets"):
            self.album_adds.extend(json.loads(data)["ids"])
            return FakeResponse([{"success": True}])
        raise AssertionError(f"unexpected call to fake Immich API: {method} {url}")
