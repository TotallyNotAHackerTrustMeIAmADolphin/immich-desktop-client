import hashlib
import json
import os.path
import socket
from datetime import datetime
from pathlib import Path
from time import sleep

import requests

from record import UploadRecord, migrate_legacy_shelve

MINIMUM_SERVER_VERSION = (3, 0, 0)
OWNERSHIP_HINT_KEY = "immich-desktop-client"
RETRY_ATTEMPTS = 4
RETRY_BASE_DELAY_SECONDS = 1
TRASH_BATCH_SIZE = 100


class UnsupportedServerError(Exception):
    """The server is older than MINIMUM_SERVER_VERSION or reports no parseable version."""


class InvalidServerResponseError(Exception):
    """The address answered, but not like an Immich API (wrong URL, proxy error page, ...)."""


class ServerUnreachableError(Exception):
    """The server could not be reached; a transient condition, not a refusal."""


def with_retries(call):
    """Retry on network errors and 5xx responses with exponential backoff."""
    delay = RETRY_BASE_DELAY_SECONDS
    for attempt in range(1, RETRY_ATTEMPTS + 1):
        last_attempt = attempt == RETRY_ATTEMPTS
        try:
            response = call()
        except requests.exceptions.RequestException:
            if last_attempt:
                raise
        else:
            if response.status_code < 500 or last_attempt:
                return response
        sleep(delay)
        delay *= 2


def check_server_supported(immich_host, api_key):
    """Raise UnsupportedServerError / ServerUnreachableError unless the server meets the version floor."""
    headers = {'Accept': 'application/json', 'x-api-key': api_key}
    try:
        response = with_retries(lambda: requests.request("GET", immich_host + "/server/version", headers=headers))
    except requests.exceptions.RequestException as e:
        raise ServerUnreachableError(str(e)) from e
    if response.status_code >= 500:
        raise ServerUnreachableError(f"server answered {response.status_code}")
    if not response.ok:
        raise InvalidServerResponseError(
            f"{immich_host} answered HTTP {response.status_code}; check that the URL ends in /api")
    try:
        payload = response.json()
    except ValueError:
        raise InvalidServerResponseError(f"{immich_host} did not answer like an Immich API; check the URL")
    try:
        version = (payload['major'], payload['minor'], payload['patch'])
        if not all(isinstance(part, int) for part in version):
            raise ValueError
    except (ValueError, KeyError, TypeError):
        raise UnsupportedServerError("server did not report a parseable version")
    if version < MINIMUM_SERVER_VERSION:
        raise UnsupportedServerError(
            "server version %d.%d.%d is older than the required %d.%d.%d" % (version + MINIMUM_SERVER_VERSION))


def is_media_file(path, media_file_extensions):
    return str(path).lower().endswith(media_file_extensions)


class Immich:
    def __init__(self, immich_host, api_key, album_name=None, album_id=None, record_path=None,
                 live_delete=False, catch_up_delete=False, recursive=True, album_by_year=False):
        self.__immichHost = immich_host
        self.__apiKey = api_key
        self.__roots = []
        self.__live_delete = live_delete
        self.__catch_up_delete = catch_up_delete
        self.__recursive = recursive
        self.__album_by_year = album_by_year
        self.__album_ids = {}

        if record_path is None:
            data_dir = Path.home() / ".Immich-desktop-client"
            self.record = UploadRecord(data_dir / "record.sqlite")
            migrate_legacy_shelve(data_dir / "shelve", self.record)
        else:
            self.record = UploadRecord(record_path)

        self.check_server_supported()

        self.album_name = socket.gethostname() if album_name is None else album_name
        if album_id is not None:
            self.__album_ids[self.album_name] = album_id
        elif not album_by_year:
            self.__album_id_for(self.album_name)

    # ---- scanning -------------------------------------------------------------------------------------------

    def upload_all_images(self, directories, media_file_extensions):
        self.__roots = [os.path.normpath(directory) for directory in directories]

        print("catch up with files already in the upload record")
        for entry in self.record.entries():
            root = entry.root or self.__root_for(entry.path)
            if root is None or root not in self.__roots:
                continue  # root removed from the config: its entries stay untouched
            if not os.path.isdir(root):
                continue  # root currently unreachable (unmounted drive, offline share): skip, never delete
            if entry.root is None:
                self.record.set_root(entry.path, root)
            if os.path.isfile(entry.path):
                self.modify(entry.path)
            elif self.__catch_up_delete:
                self.__forget_missing(entry)

        print("uploading new files")
        for root in self.__roots:
            if not os.path.isdir(root):
                print(f"skipping unreachable watched root {root}")
                continue
            for file in self.__media_files(root, media_file_extensions):
                if self.record.get(file) is None:
                    self.created(file)

    def __media_files(self, root, media_file_extensions):
        if self.__recursive:
            for folder, _, filenames in os.walk(root):
                for filename in sorted(filenames):
                    if is_media_file(filename, media_file_extensions):
                        yield os.path.join(folder, filename)
        else:
            for filename in sorted(os.listdir(root)):
                if is_media_file(filename, media_file_extensions):
                    yield os.path.join(root, filename)

    # ---- file events ----------------------------------------------------------------------------------------

    def created(self, file):
        self.__upload(file)

    def modify(self, file):
        """Replace the server copy of a locally modified file (acts on a checksum change only)."""
        entry = self.record.get(file)
        if entry is None:
            self.created(file)
            return
        if self.__get_sha1(file) == entry.checksum:
            return

        uploaded = self.__upload(file)
        if uploaded is None:
            return  # the old asset and its record entry are untouched
        new_id, status = uploaded
        if not entry.own_upload or status != 'created' or new_id == entry.asset_id:
            return  # never copy over or trash an asset this client did not create itself
        if not self.__copy_asset_metadata(entry.asset_id, new_id):
            return  # albums/favorite could not be carried over: keep the old asset rather than lose them
        self.__trash([entry.asset_id])

    def delete(self, file):
        """Live delete: a watched file disappeared while the app was running."""
        entry = self.record.get(file)
        if entry is None:
            return
        if self.__live_delete and entry.own_upload and not self.__trash([entry.asset_id]):
            return  # trash failed: keep the entry rather than lose track of the asset
        self.record.remove(file)

    def move(self, source, destination):
        entry = self.record.get(source)
        if entry is None:
            return
        self.record.remove(source)
        self.record.upsert(destination, entry.asset_id, entry.checksum, entry.own_upload,
                           root=self.__root_for(destination) or entry.root)

    def delete_all_own_uploads(self):
        """Move every own upload to the server's trash. Returns how many were trashed."""
        own = [entry for entry in self.record.entries() if entry.own_upload]
        trashed = 0
        for start in range(0, len(own), TRASH_BATCH_SIZE):
            batch = own[start:start + TRASH_BATCH_SIZE]
            if not self.__trash([entry.asset_id for entry in batch]):
                continue  # keep these entries so nothing is forgotten that is still on the server
            for entry in batch:
                self.record.remove(entry.path)
            trashed += len(batch)
        return trashed

    def move_folder(self, source, destination):
        """A folder was moved or renamed: re-point every record entry below it, no server calls."""
        source, destination = os.path.normpath(source), os.path.normpath(destination)
        prefix = os.path.normcase(source) + os.sep
        for entry in self.record.entries():
            if os.path.normcase(entry.path).startswith(prefix):
                self.move(entry.path, destination + entry.path[len(source):])

    def __forget_missing(self, entry):
        """Catch-up delete: the record lists a file that is gone although its watched root is reachable."""
        if entry.own_upload and not self.__trash([entry.asset_id]):
            return  # keep the entry so the next startup retries
        self.record.remove(entry.path)

    # ---- server calls ---------------------------------------------------------------------------------------

    def __upload(self, file):
        """Upload a file and record it. Returns (asset_id, status), or None if the upload failed."""
        try:
            stats = self.__get_file_stats(file)
        except FileNotFoundError:
            print("could not create file")
            return None

        checksum = self.__get_sha1(file)
        if checksum is None:
            return None
        headers = {
            'Accept': 'application/json',
            'x-api-key': self.__apiKey,
            'x-Immich-checksum': checksum
        }
        data = {
            'fileCreatedAt': self.__iso_timestamp(stats.st_mtime),
            'fileModifiedAt': self.__iso_timestamp(stats.st_mtime),
            'isFavorite': 'false',
            'metadata': json.dumps([{'key': OWNERSHIP_HINT_KEY, 'value': {'checksum': checksum}}]),
        }

        def post():
            with open(file, 'rb') as asset_data:
                return requests.post(self.__immichHost + "/assets", headers=headers, data=data,
                                     files={'assetData': asset_data})

        try:
            response = with_retries(post)
        except (requests.exceptions.RequestException, OSError) as e:
            print(f"upload of {file} failed: {e}")
            return None
        if not response.ok:
            print(f"upload of {file} failed: {response.status_code} {response.text}")
            return None

        uploaded = json.loads(response.text)
        asset_id, status = uploaded['id'], uploaded['status']
        print("status: " + status)
        previous = self.record.get(file)
        own_upload = status == 'created' or (
            previous is not None and previous.own_upload and previous.asset_id == asset_id)
        self.record.upsert(file, asset_id, checksum, own_upload=own_upload, root=self.__root_for(file))
        self.__add_asset_to_album(asset_id, self.__album_name_for(stats.st_mtime))
        return asset_id, status

    def __copy_asset_metadata(self, source_id, target_id):
        payload = json.dumps({"sourceId": source_id, "targetId": target_id})
        response = self.__request("PUT", "/assets/copy", data=payload, json_body=True)
        if response is None or not response.ok:
            print("could not carry albums/favorite over to the new asset; keeping the old asset")
            return False
        return True

    def __trash(self, asset_ids):
        """Move assets to the server's trash; True on success. Deliberately never sends force (see ADR 0001)."""
        response = self.__request("DELETE", "/assets", data=json.dumps({"ids": list(asset_ids)}), json_body=True)
        if response is None or not response.ok:
            print(f"could not trash {asset_ids}")
            return False
        return True

    def __album_name_for(self, timestamp):
        if not self.__album_by_year:
            return self.album_name
        return f"{self.album_name} {datetime.fromtimestamp(timestamp).year}"

    def __album_id_for(self, album_name):
        if album_name not in self.__album_ids:
            self.__album_ids[album_name] = self.__find_album(album_name) or self.__create_album(album_name)
        return self.__album_ids[album_name]

    def __find_album(self, album_name):
        response = self.__request("GET", "/albums", params={'isOwned': 'true', 'name': album_name})
        if response is None or not response.ok:
            raise ServerUnreachableError("could not list albums")
        # the server filters too, but old servers ignore the filters, so match again here
        for album in response.json():
            if album['albumName'] == album_name and album.get('isOwned'):
                return album['id']
        return None

    def __create_album(self, album_name):
        print("no album found ... creating new one")
        payload = json.dumps({
            "albumName": album_name,
            "description": "The Immich Desktop Client puts all images from " + self.album_name + " in this folder",
        })
        response = self.__request("POST", "/albums", data=payload, json_body=True)
        if response is None or not response.ok:
            raise ServerUnreachableError("could not create album")
        print("Successfully created album " + str(response.json()))
        return response.json()['id']

    def __add_asset_to_album(self, asset_id, album_name):
        try:
            album_id = self.__album_id_for(album_name)
        except ServerUnreachableError as e:
            print(f"could not file asset into album {album_name}: {e}")
            return
        response = self.__request("PUT", f"/albums/{album_id}/assets", data=json.dumps({"ids": [str(asset_id)]}),
                                  json_body=True)
        if response is None or not response.ok:
            print(f"could not add asset to album {album_name}")

    def check_server_supported(self):
        check_server_supported(self.__immichHost, self.__apiKey)

    def test_connection(self):
        response = self.__request("POST", "/auth/validateToken")
        if response is not None:
            print(response.json())
            return response.status_code

    # ---- plumbing -------------------------------------------------------------------------------------------

    def __request(self, method, path, data=None, params=None, json_body=False):
        """A retried API call; returns the response, or None if the server could not be reached."""
        headers = {'Accept': 'application/json', 'x-api-key': self.__apiKey}
        if json_body:
            headers['Content-Type'] = 'application/json'
        try:
            return with_retries(lambda: requests.request(
                method, self.__immichHost + path, headers=headers, data=data, params=params))
        except requests.exceptions.RequestException as e:
            print(f"{method} {path} failed: {e}")
            return None

    def __root_for(self, path):
        """The watched root that contains path (the deepest one if roots are nested), or None."""
        path = os.path.normcase(os.path.normpath(path))
        candidates = []
        for root in self.__roots:
            prefix = os.path.normcase(root)
            if not prefix.endswith(os.sep):
                prefix += os.sep  # a drive root such as C:\ already ends in a separator
            if path.startswith(prefix):
                candidates.append(root)
        return max(candidates, key=len) if candidates else None

    @staticmethod
    def __get_sha1(file: str):
        for i in range(0, 3):
            try:
                with open(file, 'rb', buffering=0) as f:
                    # noinspection PyTypeChecker
                    return hashlib.file_digest(f, 'sha1').hexdigest()
            except Exception as e:
                print(e)
                sleep(0.5)

    @staticmethod
    def __get_file_stats(file: str):
        # when downloading images via the browser sometimes os.stat() fails therefore it retries for 3 times
        for i in range(0, 3):
            try:
                return os.stat(file)
            except FileNotFoundError:
                sleep(0.5)
        else:
            print("Error: could not get file stats since could not find file")
            raise FileNotFoundError

    @staticmethod
    def __iso_timestamp(timestamp: float):
        # Immich 3.x rejects dates without a UTC offset
        return datetime.fromtimestamp(timestamp).astimezone().isoformat()
