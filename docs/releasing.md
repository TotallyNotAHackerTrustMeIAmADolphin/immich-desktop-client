# Releasing

A release needs all three gates below. CI only runs the unit tests; the other two are manual.

## 1. Unit tests (automatic)

`pip install -r requirements-dev.txt && python -m pytest`

## 2. Integration tests against a disposable Immich 3.1 (manual, local)

Never use your real library: these tests upload, replace and trash assets.

1. Start a throw-away server from the official compose file of the release you target, e.g.
   `https://github.com/immich-app/immich/releases/download/v3.1.0/docker-compose.yml` (plus its example `.env`),
   with `docker compose up -d`. Wait for `http://localhost:2283/api/server/version`.
2. `IMMICH_TEST_URL=http://localhost:2283/api python -m pytest tests/integration`
   (the first run signs up an admin and creates an API key itself; set `IMMICH_TEST_API_KEY` to reuse one).
3. `docker compose down -v` to throw everything away.

They cover album lookup, replace (upload, copy, trash old) and live-delete-to-trash being restorable.

## 3. Manual smoke test on Windows 11 (manual)

On a clean profile (or after removing `%USERPROFILE%\.Immich-desktop-client`):

1. Build: `pip install pyinstaller pystray watchdog`, then `pyinstaller immich-desktop-client.spec` (windowed, with icon), then compile `resources/installer-script.iss`.
2. Install; start the app: the settings window opens. Enter the LAN server, an API key and a test folder.
   Saving against a server older than 3.0.0 must be refused.
3. Restart the app: tray icon appears, a second launch does nothing, existing files upload into the album.
4. Add a photo, edit it, rename it, delete it (with *live delete* on): check Immich after each step.
5. Tray: *Start with Windows* toggles, *Settings...* opens, *Move all uploads to Immich trash...* asks first, *Quit* exits.
6. Upgrade path: install over an old version that has a `shelve` file; its entries must appear as non-own uploads
   (never deleted or replaced), and an old `config.yaml` directory must be moved aside, not crash the app.

The checkable parts of this list are automated: `python tests/smoke/run_smoke.py` builds the exe from the spec, starts a
throw-away Immich 3.1 in Docker, runs the exe in a temp profile (`USERPROFILE` is redirected, so your real profile and
autostart entry are untouched) and checks version refusal, upload of existing files, single instance, add / edit /
rename / delete with live delete, album reuse across restarts, and the shelve upgrade. Quit the installed app first
(the single-instance port is machine-wide). Still manual: the installer, the tray menu and the Tk dialogs
(*Start with Windows*, *Settings...*, the bulk-trash confirmation, *Quit*).

## Cutting a release

1. Pass the three gates above.
2. Bump `VERSION` (one place; the installer reads it) and merge.
3. Run the *Build release (draft)* workflow from the Actions tab. It runs the unit tests, builds the exe and installer
   and attaches them to a **draft** release `v<VERSION>`; it refuses to run if that release already exists.
4. Check the draft, then publish it.

## Still undecided (see issue #1)

Code signing / SmartScreen: releases are unsigned for now and the README says how to get past the warning.
