import sys

VALUE_NAME = "ImmichDesktopClient"
_RUN_KEY_PATH = r"Software\Microsoft\Windows\CurrentVersion\Run"


class _WindowsRunKey:
    """The per-user Run registry key; the only part of this module that needs Windows."""

    def get(self, name):
        import winreg
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY_PATH) as key:
                return winreg.QueryValueEx(key, name)[0]
        except FileNotFoundError:
            return None

    def set(self, name, value):
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY_PATH, 0, winreg.KEY_SET_VALUE) as key:
            winreg.SetValueEx(key, name, 0, winreg.REG_SZ, value)

    def delete(self, name):
        import winreg
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY_PATH, 0, winreg.KEY_SET_VALUE) as key:
                winreg.DeleteValue(key, name)
        except FileNotFoundError:
            pass


def default_run_key():
    """The registry key on Windows, None elsewhere (autostart is Windows-only in this release)."""
    return _WindowsRunKey() if sys.platform == "win32" else None


def is_enabled(run_key=...):
    run_key = default_run_key() if run_key is ... else run_key
    return run_key is not None and run_key.get(VALUE_NAME) is not None


def enable(command, run_key=...):
    run_key = default_run_key() if run_key is ... else run_key
    if run_key is None:
        return False
    run_key.set(VALUE_NAME, f'"{command}"')
    return True


def disable(run_key=...):
    run_key = default_run_key() if run_key is ... else run_key
    if run_key is None:
        return False
    run_key.delete(VALUE_NAME)
    return True
