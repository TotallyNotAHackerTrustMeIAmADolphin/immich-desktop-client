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


class UnsupportedServerError(Exception):
    """The server is older than MINIMUM_SERVER_VERSION or reports no parseable version."""


class ServerUnreachableError(Exception):
    """The server could not be reached; a transient condition, not a refusal."""


def is_media_file(path, media_file_extensions):
    return str(path).lower().endswith(media_file_extensions)


class Immich:
    def __init__(self, immich_host, api_key, album_name=None, album_id=None, record_path=None, live_delete=False, catch_up_delete=False):
        self.__immichHost = immich_host
        self.__apiKey = api_key
        self.__roots = []
        self.__live_delete = live_delete
        self.__catch_up_delete = catch_up_delete

        if record_path is None:
            data_dir = Path.home() / ".Immich-desktop-client"
            self.record = UploadRecord(data_dir / "record.sqlite")
            migrate_legacy_shelve(data_dir / "shelve", self.record)
        else:
            self.record = UploadRecord(record_path)

        self.check_server_supported()

        if album_name is None:
            self.album_name = socket.gethostname()
        else:
            self.album_name = album_name

        if album_id is None:
            self.__album_id = self.__get_album_id()
        else:
            self.__album_id = album_id

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
            for filename in os.listdir(root):
                file = os.path.join(root, filename)
                if is_media_file(filename, media_file_extensions) and self.record.get(file) is None:
                    self.created(file)

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
        self.__copy_asset_metadata(entry.asset_id, new_id)
        self.__trash([entry.asset_id])

    def __upload(self, file):
        """Upload a file and record it. Returns (asset_id, status), or None if the upload failed."""
        try:
            stats = self.__get_file_stats(file)
        except FileNotFoundError:
            print("could not create file")
            return None

        checksum = self.__get_sha1(file)
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

        files = {
            'assetData': open(file, 'rb')
        }
        try:
            response = requests.post(self.__immichHost + "/assets", headers=headers, data=data, files=files)
        except Exception as e:
            print(e)
            return None
        else:
            if not response.ok:
                print(f"upload of {file} failed: {response.status_code} {response.text}")
                return None
            image_id = json.loads(response.text)
            print("status: " + image_id['status'])
            previous = self.record.get(file)
            own_upload = image_id['status'] == 'created' or (
                previous is not None and previous.own_upload and previous.asset_id == image_id['id'])
            self.record.upsert(file, image_id['id'], checksum, own_upload=own_upload,
                               root=self.__root_for(file))
            self.__add_asset_to_album(image_id['id'])
            print("saved image successfully: " + str(response.text))
            return image_id['id'], image_id['status']

    def __forget_missing(self, entry):
        """Catch-up delete: the record lists a file that is gone although its watched root is reachable."""
        if entry.own_upload and not self.__trash([entry.asset_id]):
            return  # keep the entry so the next startup retries
        self.record.remove(entry.path)

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

    def __copy_asset_metadata(self, source_id, target_id):
        headers = {'Content-Type': 'application/json', 'x-api-key': self.__apiKey}
        payload = json.dumps({"sourceId": source_id, "targetId": target_id})
        try:
            response = requests.request("PUT", self.__immichHost + "/assets/copy", headers=headers, data=payload)
            if not response.ok:
                print(f"could not carry albums/favorite over to the new asset: {response.status_code}")
        except requests.exceptions.RequestException as e:
            print(f"could not carry albums/favorite over to the new asset: {e}")

    def __trash(self, asset_ids):
        """Move assets to the server's trash; True on success. Deliberately never sends force (see ADR 0001)."""
        headers = {'Content-Type': 'application/json', 'x-api-key': self.__apiKey}
        payload = json.dumps({"ids": list(asset_ids)})
        try:
            response = requests.request("DELETE", self.__immichHost + "/assets", headers=headers, data=payload)
            if not response.ok:
                print(f"could not trash {asset_ids}: {response.status_code}")
            return response.ok
        except requests.exceptions.RequestException as e:
            print(f"could not trash {asset_ids}: {e}")
            return False

    def __root_for(self, path):
        """The watched root that contains path (the deepest one if roots are nested), or None."""
        path = os.path.normpath(path)
        candidates = [root for root in self.__roots if path.startswith(root + os.sep)]
        return max(candidates, key=len) if candidates else None

    def __create_album(self):
        payload = json.dumps({
            "albumName": self.album_name,
            "description": "The Immich Desktop Client puts all images from " + self.album_name + " in this folder",
        })
        headers = {
            'Content-Type': 'application/json',
            'Accept': 'application/json',
            'x-api-key': self.__apiKey
        }
        response = requests.request("POST", self.__immichHost + "/albums", headers=headers, data=payload)
        print("Successfully created album " + str(response.json()))
        return json.loads(response.text)['id']

    def __get_album_id(self):
        headers = {
            'Accept': 'application/json',
            'x-api-key': self.__apiKey
        }

        response = requests.request("GET", self.__immichHost + "/albums", headers=headers)
        response = json.loads(response.text)

        album_id = None
        for album in response:
            if album['albumName'] == self.album_name and album.get('isOwned'):
                album_id = album['id']
        if album_id is None:
            print("no album found ... creating new one")
            album_id = self.__create_album()

        return album_id

    def __add_asset_to_album(self, asset_id):
        payload = json.dumps({
            "ids": [
                str(asset_id)
            ]
        })
        headers = {
            'Content-Type': 'application/json',
            'Accept': 'application/json',
            'x-api-key': self.__apiKey
        }

        response = requests.request("PUT", self.__immichHost + "/albums/" + self.__album_id + "/assets",
                                    headers=headers, data=payload)
        print(response.json())
        print("successfully added asset to album")

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

    def check_server_supported(self):
        headers = {'Accept': 'application/json', 'x-api-key': self.__apiKey}
        try:
            response = requests.request("GET", self.__immichHost + "/server/version", headers=headers)
        except requests.exceptions.RequestException as e:
            raise ServerUnreachableError(str(e)) from e

        try:
            payload = response.json()
            version = (payload['major'], payload['minor'], payload['patch'])
            if not all(isinstance(part, int) for part in version):
                raise ValueError
        except (ValueError, KeyError, TypeError):
            raise UnsupportedServerError("server did not report a parseable version")
        if version < MINIMUM_SERVER_VERSION:
            raise UnsupportedServerError(
                "server version %d.%d.%d is older than the required %d.%d.%d" % (version + MINIMUM_SERVER_VERSION))

    def test_connection(self):
        headers = {
            'Accept': 'application/json',
            'x-api-key': self.__apiKey
        }

        try:
            response = requests.request("POST", self.__immichHost + "/auth/validateToken", headers=headers)
            print(response.json())
            return response.status_code
        except requests.exceptions.RequestException as e:
            print(e)
