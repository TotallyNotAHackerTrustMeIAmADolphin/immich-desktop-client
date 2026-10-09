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
    def __init__(self, immich_host, api_key, album_name=None, album_id=None, record_path=None):
        self.__immichHost = immich_host
        self.__apiKey = api_key
        self.__roots = []

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
            # files missing from disk are deliberately left alone here (catch-up delete is a separate feature)
            if os.path.isfile(entry.path) and self.__get_sha1(entry.path) != entry.checksum:
                self.created(entry.path)

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
        try:
            stats = self.__get_file_stats(file)
        except FileNotFoundError:
            print("could not create file")
            return

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
        else:
            if not response.ok:
                print(f"upload of {file} failed: {response.status_code} {response.text}")
                return
            image_id = json.loads(response.text)
            print("status: " + image_id['status'])
            self.record.upsert(file, image_id['id'], checksum, own_upload=image_id['status'] == 'created',
                               root=self.__root_for(file))
            self.__add_asset_to_album(image_id['id'])
            print("saved image successfully: " + str(response.text))

    # TODO: Create option to replace assets instead of adding the new version
    #    def modify(self, file):
    #                try:
    #                    stats = self.__get_file_stats(file)
    #                except FileNotFoundError:
    #                    print("could not create file")
    #                    return
    #        try:
    #            asset_id = self.__get_image_id(file)
    #        except KeyError:
    #            print("trying to modify non-uploaded file ... uploading file")
    #            self.created(file)
    #        else:
    #            print(file)
    #            data = {
    #                'deviceAssetId': f"{file}-{stats.st_mtime}",
    #                'deviceId': self.__uuid,
    #                'fileCreatedAt': datetime.fromtimestamp(stats.st_mtime),
    #                'fileModifiedAt': datetime.fromtimestamp(stats.st_mtime)
    #            }
    #            files=[
    #                ('assetData',('IMAGE',open(file,'rb'),'application/octet-stream'))
    #            ]
    #            headers = {
    #                'Accept': 'application/json',
    #                'x-api-key': self.__apiKey
    #            }
    #            try:
    #                print(f"{self.__immichHost}/assets/{asset_id}/original")
    #                response = requests.request(method="PUT", url=f"{self.__immichHost}/assets/{asset_id}/original", headers=headers,
    #                                            files=files, data=data)
    #            except Exception as e:
    #                print("error when replacing file" + e.__str__())
    #            else:
    #                if response.status_code == 200:
    #                    self.__save_image_to_shelve(asset_id, file)
    #                else:
    #                    print("error when replacing file")
    #                print(response.text)

    def delete(self, file):
        self.record.remove(file)

    # TODO create Option for deleting images on server too
    #    try:
    #        assetId = self.__getImageId(file)
    #    except KeyError:
    #        print("deleting non-uploaded file")
    #    else:
    #        payload = json.dumps({
    #            "force": True,
    #            "ids": [
    #                assetId
    #            ]
    #        })
    #        headers = {
    #            'Content-Type': 'application/json',
    #            'x-api-key': self.__apiKey
    #        }
    #        try:
    #            response = requests.request("DELETE", self.__immichHost + "/assets", headers=headers, data=payload)
    #        except Exception as e:
    #            print("error when deleting file: "+ e.__str__())
    #            return
    #        else:
    #            print(response.text)
    #            self.__delete_image_from_shelve(file)
    def move(self, source, destination):
        entry = self.record.get(source)
        if entry is None:
            return
        self.record.remove(source)
        self.record.upsert(destination, entry.asset_id, entry.checksum, entry.own_upload,
                           root=self.__root_for(destination) or entry.root)

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
