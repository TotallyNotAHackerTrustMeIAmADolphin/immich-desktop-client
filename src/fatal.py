import logging
import os

log = logging.getLogger(__name__)

TITLE = "Immich Desktop Client"
NO_DIALOGS_ENV = "IMMICH_DESKTOP_CLIENT_NO_DIALOGS"  # set by the automated smoke test, which must not block


def _show_dialog(message):
    import tkinter
    from tkinter import messagebox

    root = tkinter.Tk()
    root.withdraw()
    root.attributes('-topmost', True)
    try:
        messagebox.showerror(TITLE, message, parent=root)
    finally:
        root.destroy()


def die(message, show=_show_dialog):
    """Stop the app with a reason the user can actually see.

    The windowed exe has no console, so a bare sys.exit(message) would make it vanish without a word.
    """
    log.error(message)
    try:
        if not os.environ.get(NO_DIALOGS_ENV):
            show(message)
    except Exception as e:  # no tkinter or no display (headless session): the log still has the reason
        log.warning(f"could not show the error window: {e!r}")
    raise SystemExit(1)
