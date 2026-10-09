"""Automated Windows smoke test for the built exe against a DISPOSABLE Immich server.

Covers the checkable parts of docs/releasing.md step 3: version refusal, upload of existing files, single instance,
add / edit / rename / delete with live delete, and the upgrade from a legacy shelve (migrated entries are never
trashed). It does NOT click the tray menu or the Tk dialogs; do that part by hand.

    python tests/smoke/run_smoke.py                 # builds the exe, starts a throw-away Immich 3.1 in Docker
    python tests/smoke/run_smoke.py --exe PATH      # use an existing exe
    python tests/smoke/run_smoke.py --url http://localhost:2283/api --key KEY   # reuse a disposable server

Never point --url at a real library. Quit the installed app first: the single-instance lock port is machine-wide.
The exe runs with USERPROFILE pointing at a temp dir, so your real profile and autostart entry stay untouched.
"""
import argparse
import hashlib
import http.server
import json
import os
import shelve
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
import uuid
from pathlib import Path

import requests
from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
COMPOSE_URL = "https://github.com/immich-app/immich/releases/download/v3.1.0/{}"
LOCK_PORT = 47862  # single_instance.DEFAULT_PORT

results = []


def check(name, ok, detail=""):
    results.append((name, bool(ok), detail))
    print(f"[{'PASS' if ok else 'FAIL'}] {name}{(' - ' + detail) if detail and not ok else ''}", flush=True)
    return ok


def wait_for(predicate, timeout=90, interval=2):
    end = time.time() + timeout
    while time.time() < end:
        value = predicate()
        if value:
            return value
        time.sleep(interval)
    return None


def photo(directory, name, color):
    path = Path(directory) / name
    image = Image.new("RGB", (16, 16), color)
    salt = uuid.uuid4().bytes  # unique bytes: a duplicate on the server would (correctly) not count as an own upload
    for i in range(0, 12, 3):
        image.putpixel((i // 3, 0), tuple(salt[i:i + 3]))
    image.save(path)
    return path


# ---- server ----------------------------------------------------------------------------------------------------

class Server:
    def __init__(self, url, key):
        self.url, self.key = url, key
        self.headers = {"x-api-key": key, "Accept": "application/json"}

    def get(self, path, **kw):
        return requests.get(self.url + path, headers=self.headers, timeout=30, **kw)

    def albums(self, album):
        return [a for a in self.get("/albums", params={"name": album}).json() if a["albumName"] == album]

    def album_assets(self, album):
        """Every asset (also trashed ones) in the albums with this name; 3.x no longer lists them in GET /albums/{id}."""
        assets = []
        for found in self.albums(album):
            body = {"albumIds": [found["id"]], "withDeleted": True, "size": 200}
            r = requests.post(self.url + "/search/metadata", headers=self.headers, json=body, timeout=30)
            for a in r.json()["assets"]["items"]:
                a["trashed"] = bool(a.get("isTrashed"))
                assets.append(a)
        return assets

    def live(self, album, name=None):
        return [a for a in self.album_assets(album)
                if not a["trashed"] and (name is None or a["originalFileName"] == name)]

    def upload(self, path):
        stamp = time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime(os.path.getmtime(path)))
        with open(path, "rb") as f:
            r = requests.post(self.url + "/assets", headers=self.headers, timeout=60,
                              data={"deviceAssetId": uuid.uuid4().hex, "deviceId": "smoke", "fileCreatedAt": stamp,
                                    "fileModifiedAt": stamp}, files={"assetData": f})
        r.raise_for_status()
        return r.json()["id"]

    def is_trashed(self, asset_id):
        return bool(self.get(f"/assets/{asset_id}").json().get("isTrashed"))


def start_docker_server(workdir):
    docker = r"C:\Program Files\Docker\Docker\resources\bin"
    env = {**os.environ, "PATH": os.environ["PATH"] + os.pathsep + docker}
    for name, target in (("docker-compose.yml", "docker-compose.yml"), ("example.env", ".env")):
        (workdir / target).write_bytes(requests.get(COMPOSE_URL.format(name), timeout=60).content)
    env_file = workdir / ".env"
    env_file.write_text("\n".join("IMMICH_VERSION=v3.1.0" if l.startswith("IMMICH_VERSION=") else l
                                  for l in env_file.read_text().splitlines()))
    subprocess.run(["docker", "compose", "up", "-d"], cwd=workdir, env=env, check=True)
    url = "http://localhost:2283/api"
    if not wait_for(lambda: _ok(url + "/server/version"), timeout=240, interval=3):
        raise RuntimeError("Immich did not come up")
    creds = {"email": "admin@example.test", "password": "smoke-test-password"}
    requests.post(f"{url}/auth/admin-sign-up", json={**creds, "name": "Admin"})
    token = requests.post(f"{url}/auth/login", json=creds).json()["accessToken"]
    key = requests.post(f"{url}/api-keys", json={"name": "smoke", "permissions": ["all"]},
                        headers={"Authorization": f"Bearer {token}"}).json()["secret"]
    return url, key, env


def _ok(url):
    try:
        return requests.get(url, timeout=5).ok
    except requests.RequestException:
        return False


# ---- app -------------------------------------------------------------------------------------------------------

class App:
    """One exe process running with its own USERPROFILE."""

    def __init__(self, exe, profile):
        self.exe, self.profile = exe, Path(profile)
        self.config_dir = self.profile / ".Immich-desktop-client"
        self.proc = None

    def write_config(self, url, key, album, directory, live=True):
        self.config_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy(ROOT / "resources" / "icon.ico", self.config_dir / "icon.ico")
        (self.config_dir / "config.yaml").write_text(
            f"api:\n  url: {url}\n  key: {key}\n  album: {album}\nwatchdog:\n  recursive: true\n"
            f"  directories:\n  - {Path(directory).as_posix()}\ndelete:\n  live: {str(live).lower()}\n  catch_up: false\n")

    def start(self):
        env = {**os.environ, "USERPROFILE": str(self.profile), "HOME": str(self.profile)}
        self.proc = subprocess.Popen([str(self.exe)], env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return self.proc

    def stop(self):
        if self.proc and self.proc.poll() is None:
            subprocess.run(["taskkill", "/F", "/T", "/PID", str(self.proc.pid)], capture_output=True)
            self.proc.wait(timeout=30)


def lock_port_free():
    s = socket.socket()
    try:
        s.bind(("127.0.0.1", LOCK_PORT))
        return True
    except OSError:
        return False
    finally:
        s.close()


# ---- scenarios -------------------------------------------------------------------------------------------------

def scenario_version_refusal(exe, tmp):
    class Old(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            body = json.dumps({"major": 2, "minor": 7, "patch": 0}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *a):
            pass

    httpd = http.server.HTTPServer(("127.0.0.1", 0), Old)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    watch = tmp / "old-watch"
    watch.mkdir()
    app = App(exe, tmp / "profile-old")
    app.write_config(f"http://127.0.0.1:{httpd.server_port}/api", "key", "smoke-old", watch)
    proc = app.start()
    try:
        code = wait_for(lambda: proc.poll() is not None, timeout=60)
        check("server older than 3.0.0 is refused (app exits)", code and proc.returncode not in (0, None),
              f"returncode={proc.returncode}")
    finally:
        app.stop()
        httpd.shutdown()


def scenario_main(server, exe, tmp):
    album = f"smoke-{uuid.uuid4().hex[:6]}"
    watch = tmp / "watch"
    watch.mkdir()
    a = photo(watch, "a.jpg", "red")
    b = photo(watch, "b.jpg", "green")
    app = App(exe, tmp / "profile-main")
    app.write_config(server.url, server.key, album, watch)
    app.start()
    try:
        ok = wait_for(lambda: len(server.live(album)) == 2, timeout=120)
        check("existing files are uploaded into the album", ok, f"{len(server.live(album))} assets")
        if not ok:
            return
        b_id = server.live(album, "b.jpg")[0]["id"]
        a_old = server.live(album, "a.jpg")[0]["id"]

        second = App(exe, tmp / "profile-main")
        proc2 = second.start()
        exited = wait_for(lambda: proc2.poll() is not None, timeout=30)
        check("second launch exits without doing anything", exited and app.proc.poll() is None)
        second.stop()

        c = photo(watch, "c.jpg", "blue")
        c_assets = wait_for(lambda: server.live(album, "c.jpg"), timeout=60)
        check("new file is uploaded", c_assets)
        if not c_assets:
            return

        photo(watch, "a.jpg", "yellow")  # edit: different pixels
        replaced = wait_for(lambda: server.is_trashed(a_old) and server.live(album, "a.jpg"), timeout=90)
        check("edited file replaces the server copy (old trashed, new in album)", replaced)

        before = len(server.album_assets(album))
        b.rename(watch / "b2.jpg")
        time.sleep(10)
        check("rename causes no new upload and no trash",
              len(server.album_assets(album)) == before and not server.is_trashed(b_id))

        c_id = c_assets[0]["id"]
        c.unlink()
        check("deleting a file trashes its asset (restorable, not removed)",
              wait_for(lambda: server.is_trashed(c_id), timeout=60) and
              server.get(f"/assets/{c_id}").status_code == 200)

        app.stop()
        app.start()
        time.sleep(20)
        check("restarting the app reuses its album instead of creating another", len(server.albums(album)) == 1,
              f"{len(server.albums(album))} albums named {album}")
    finally:
        app.stop()


def scenario_upgrade(server, exe, tmp):
    album = f"smoke-up-{uuid.uuid4().hex[:6]}"
    watch = tmp / "watch-up"
    watch.mkdir()
    legacy = photo(watch, "legacy.jpg", "purple")
    legacy_id = server.upload(legacy)
    app = App(exe, tmp / "profile-up")
    app.write_config(server.url, server.key, album, watch)
    checksum = hashlib.sha1(legacy.read_bytes()).hexdigest()
    with shelve.open(str(app.config_dir / "shelve")) as db:  # old key format: str(path) -> [asset_id, checksum]
        db[os.path.normpath(str(legacy))] = [legacy_id, checksum]
    fresh = photo(watch, "fresh.jpg", "orange")
    app.start()
    try:
        uploaded = wait_for(lambda: server.live(album, "fresh.jpg"), timeout=120)
        check("upgrade: a new file is uploaded after migrating the shelve", uploaded)
        if not uploaded:
            return
        fresh_id = uploaded[0]["id"]
        legacy.unlink()
        fresh.unlink()
        trashed = wait_for(lambda: server.is_trashed(fresh_id), timeout=60)
        time.sleep(5)
        check("upgrade: own upload is trashed on delete (control)", trashed)
        check("upgrade: migrated (non-own) entry is never trashed", not server.is_trashed(legacy_id))
    finally:
        app.stop()


def build_exe(tmp):
    out = tmp / "dist"
    subprocess.run([sys.executable, "-m", "PyInstaller", str(ROOT / "immich-desktop-client.spec"), "--noconfirm",
                    "--distpath", str(out), "--workpath", str(tmp / "build")], cwd=ROOT, check=True,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return out / "immich-desktop-client.exe"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--exe")
    parser.add_argument("--url")
    parser.add_argument("--key")
    args = parser.parse_args()

    if not lock_port_free():
        sys.exit(f"Port {LOCK_PORT} is in use: quit the installed Immich Desktop Client first.")

    tmp = Path(tempfile.mkdtemp(prefix="immich-smoke-"))
    docker_env = None
    try:
        exe = Path(args.exe) if args.exe else build_exe(tmp)
        if args.url:
            server = Server(args.url, args.key)
        else:
            url, key, docker_env = start_docker_server(tmp)
            server = Server(url, key)
        scenario_version_refusal(exe, tmp)
        scenario_main(server, exe, tmp)
        scenario_upgrade(server, exe, tmp)
    finally:
        if docker_env:
            subprocess.run(["docker", "compose", "down", "-v"], cwd=tmp, env=docker_env)
        shutil.rmtree(tmp, ignore_errors=True)

    failed = [r for r in results if not r[1]]
    print(f"\n{len(results) - len(failed)}/{len(results)} checks passed")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
