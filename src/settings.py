import os
from pathlib import Path

import yaml

from config import CONFIG_FILENAME, is_placeholder_config
from immich import (InvalidServerResponseError, ServerUnreachableError, UnsupportedServerError,
                    check_server_supported)


def config_from_form(form):
    api = {"url": form["url"].strip().rstrip("/"), "key": form["key"].strip()}
    if form.get("album", "").strip():
        api["album"] = form["album"].strip()
    api["album_by_year"] = bool(form.get("album_by_year"))
    return {
        "api": api,
        "watchdog": {"recursive": bool(form.get("recursive", True)), "directories": list(form["directories"])},
        "delete": {"live": bool(form.get("live_delete")), "catch_up": bool(form.get("catch_up_delete"))},
    }


def form_from_config(config):
    if is_placeholder_config(config) and "<" in str(config):
        config = {}  # the untouched example config: start from a blank form instead
    api = config.get("api") or {}
    watchdog = config.get("watchdog") or {}
    delete = config.get("delete") or {}
    album = api.get("album") or ""
    return {
        "url": api.get("url", ""),
        "key": api.get("key", ""),
        "album": "" if str(album).startswith("<") else album,
        "album_by_year": bool(api.get("album_by_year", False)),
        "recursive": bool(watchdog.get("recursive", True)),
        "directories": list(watchdog.get("directories") or []),
        "live_delete": bool(delete.get("live", False)),
        "catch_up_delete": bool(delete.get("catch_up", False)),
    }


def validate_form(form, check_server=check_server_supported):
    """Return (errors, warnings). Errors block saving; warnings do not."""
    errors, warnings = [], []
    if not form.get("url", "").strip():
        errors.append("Enter the Immich server URL (ending in /api).")
    if not form.get("key", "").strip():
        errors.append("Enter an API key.")
    if not form.get("directories"):
        errors.append("Add at least one folder to watch.")
    if errors:
        return errors, warnings

    try:
        check_server(form["url"].strip().rstrip("/"), form["key"].strip())
    except UnsupportedServerError as e:
        errors.append(f"This server is not supported: {e}. Immich 3.0.0 or newer is required.")
    except InvalidServerResponseError as e:
        errors.append(str(e))
    except ServerUnreachableError as e:
        warnings.append(f"The server could not be reached right now ({e}); its version was not checked.")
    return errors, warnings


def save_config(config_dir, config):
    config_dir = Path(config_dir)
    config_dir.mkdir(parents=True, exist_ok=True)
    target = config_dir / CONFIG_FILENAME
    if target.is_dir():
        from config import load_config
        load_config(config_dir)  # renames a directory that squats on the file name
    temporary = config_dir / (CONFIG_FILENAME + ".tmp")
    with open(temporary, "wt") as file:
        yaml.safe_dump(config, file, sort_keys=False)
    os.replace(temporary, target)
