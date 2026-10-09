from pathlib import Path

import yaml

CONFIG_FILENAME = "config.yaml"

TEMPLATE = """\
api:
  key: <API-KEY>
  url: https://<IMMICH_SERVER_DOMAIN>/api
  album: <OPTIONAL; OVERRIDE THE DEFAULT ALBUM NAME>
  album_by_year: false  # file uploads into "<album> <year>" albums instead of one album
watchdog:
  recursive: true  # also watch sub-folders
  directories:
    - C:\\Users\\test\\Images\\
    - C:\\Users\\test\\Screenshots\\
# Optional. Deletions only ever move this client's own uploads to the server's trash.
delete:
  live: false      # trash the upload when the local file is deleted while the app runs
  catch_up: false  # at startup, trash uploads whose local file is gone (reachable folders only)
"""


def default_config_dir():
    return Path.home() / ".Immich-desktop-client"


def load_config(config_dir):
    """Return the parsed config, or None when first-run setup is needed.

    Older installers created config.yaml as a *directory*; such a directory is renamed aside
    rather than treated as fatal.
    """
    path = Path(config_dir) / CONFIG_FILENAME
    if path.is_dir():
        aside = _unused_name(path)
        path.rename(aside)
        print(f"{path} was a directory; moved it to {aside}")
        return None
    if not path.exists():
        return None
    with open(path, 'rt') as file:
        return yaml.safe_load(file)


def is_placeholder_config(config):
    """True for a config that is empty or still holds the example's <PLACEHOLDER> values."""
    api = (config or {}).get("api") or {}
    url, key = str(api.get("url") or ""), str(api.get("key") or "")
    return not url or not key or "<" in url or "<" in key


def existing_directories(directories):
    """The directories that are reachable right now (an unplugged drive is skipped, not fatal)."""
    reachable = []
    for directory in directories:
        if Path(directory).is_dir():
            reachable.append(directory)
        else:
            print(f"watched folder not reachable, not watching it this session: {directory}")
    return reachable


def write_template_config(config_dir):
    """Create the example config unless one already exists; return its path."""
    config_dir = Path(config_dir)
    config_dir.mkdir(parents=True, exist_ok=True)
    path = config_dir / CONFIG_FILENAME
    if not path.exists():
        path.write_text(TEMPLATE)
    return path


def _unused_name(path):
    candidate = path.with_name(path.name + ".dir-bak")
    counter = 1
    while candidate.exists():
        counter += 1
        candidate = path.with_name(f"{path.name}.dir-bak{counter}")
    return candidate
