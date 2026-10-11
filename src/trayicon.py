from pathlib import Path

ICON_NAME = "icon.ico"


def resolve_icon_path(config_dir, meipass=None, source_dir=None):
    """First existing tray icon: the profile copy (installer), the PyInstaller bundle, the source checkout.

    Pure on purpose: directories are passed in so it needs neither a display nor a real profile.
    """
    candidates = [Path(config_dir) / ICON_NAME]
    if meipass:
        candidates.append(Path(meipass) / "resources" / ICON_NAME)
    if source_dir:
        candidates.append(Path(source_dir).parent / "resources" / ICON_NAME)
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return None
