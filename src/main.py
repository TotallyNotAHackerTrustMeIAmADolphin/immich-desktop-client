import logging
import mimetypes
import os
import sys
import threading
from contextlib import contextmanager
from time import sleep
from pathlib import Path

from PIL import Image
from pystray import Icon as icon, Menu as menu, MenuItem as item
from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

import applog
import autostart
from fatal import announce, die
from gui_runner import GuiRunner
from notifier import Notifier
from status import Status
from single_instance import acquire
from config import (default_config_dir, existing_directories, is_placeholder_config, load_config,
                    write_template_config)
from immich import (Immich, InvalidServerResponseError, ServerUnreachableError, UnsupportedServerError,
                    is_media_file)

log = logging.getLogger(__name__)


def on_clicked(icon, item):
    global state
    state = not item.checked
    status.set_paused(not state)
    if state is True:
        log.info("starting synchronisation")
    else:
        log.info("ending synchronisation")


def get_extensions_for_type():
    mimetypes.init()
    temp = []
    for ext in mimetypes.types_map:
        if mimetypes.types_map[ext].split('/')[0] == "video" or mimetypes.types_map[ext].split('/')[0] == "image":
            temp.append(ext)
    for ext in mimetypes.common_types:
        if mimetypes.common_types[ext].split('/')[0] == "video" or mimetypes.common_types[ext].split('/')[0] == "image":
            temp.append(ext)

    return tuple(temp)


class MyHandler(FileSystemEventHandler):
    def on_created(self, event):
        global state
        if state and not event.is_directory and is_media_file(event.src_path, media_file_extensions):
            log.info(f"File {event.src_path} has been created!")
            try:
                api.created(event.src_path)
            except Exception as e:  # an escaping exception would silently end the watcher thread
                log.error(f"error handling creation of {event.src_path}: {e!r}")

    def on_deleted(self, event):
        global state
        if state and not event.is_directory and is_media_file(event.src_path, media_file_extensions):
            log.info(f"File {event.src_path} has been deleted!")
            try:
                api.delete(event.src_path)
            except Exception as e:
                log.error(f"error handling deletion of {event.src_path}: {e!r}")

    def on_moved(self, event):
        global state
        if (state and not event.is_directory and is_media_file(event.src_path, media_file_extensions)
                and is_media_file(event.dest_path, media_file_extensions)):
            log.info(f"File {event.src_path} has been moved to {event.dest_path}!")
            try:
                api.move(event.src_path, event.dest_path)
            except Exception as e:
                log.error(f"error handling move of {event.src_path}: {e!r}")

    def on_modified(self, event):
        global state
        if state and not event.is_directory and is_media_file(event.src_path, media_file_extensions):
            sleep(1)  # let the writer finish before hashing
            log.info(f"File {event.src_path} has been modified!")
            try:
                api.modify(event.src_path)
            except Exception as e:
                log.error(f"error handling modification of {event.src_path}: {e!r}")


instance_lock = acquire()
if instance_lock is None:
    die("Immich Desktop Client is already running.")

# Everything from here on goes to the log file: the windowed exe has no console to print to.
# Only the instance holding the lock logs, so two processes never rotate the same file.
log_path = applog.setup_logging(default_config_dir())

# Load Config
config = load_config(default_config_dir())
if config is None or is_placeholder_config(config):
    # first run (or the untouched example config): ask for the settings in a window
    config = None
    try:
        from settings_dialog import open_settings
        if open_settings():
            config = load_config(default_config_dir())
    except Exception as e:  # no tkinter, or no display (headless session)
        log.warning(f"could not show the settings window: {e!r}")
    if config is None or is_placeholder_config(config):
        die(f"No usable configuration found. Edit {write_template_config(default_config_dir())} "
                 f"or start the app again to open the settings window.")

media_file_extensions = get_extensions_for_type()

immich_host = config["api"]["url"]
album_name = config["api"].get("album")
if album_name is not None and str(album_name).startswith("<"):
    album_name = None  # still the template placeholder
api_key = config["api"]["key"]
applog.register_secret(api_key)
directories_to_watch = config["watchdog"]["directories"]
delete_options = config.get("delete") or {}
notifications_enabled = bool(config.get("notifications", True))  # changes apply after a restart

state = True

recursive = config["watchdog"].get("recursive", True)

status = Status()
api = None  # connected by startup() once the tray is up, so progress is visible from the first second
observer = Observer()
event_handler = MyHandler()
exit_code = 0

def load_icon():
    try:
        return Image.open(default_config_dir() / 'icon.ico')
    except OSError:
        return Image.new('RGB', (64, 64), (66, 80, 175))  # plain fallback when the icon file is missing


# Tk windows only ever run on the main thread (see GuiRunner); tray callbacks just submit tasks.
runner = GuiRunner(inline=sys.platform == "darwin")  # macOS: the tray owns the main thread


@contextmanager
def hidden_root():
    import tkinter
    root = tkinter.Tk()
    root.withdraw()
    root.attributes('-topmost', True)
    try:
        yield root
    finally:
        root.destroy()


def open_config(tray_icon, tray_item):
    path = write_template_config(default_config_dir())
    if hasattr(os, "startfile"):
        os.startfile(path)
    else:
        log.info(f"config file: {path}")


def show_progress_window(tray_icon, tray_item):
    def show():
        from progress_window import open_progress
        open_progress(status, should_close=lambda: not runner.running)

    runner.submit_once("progress", show)


def open_log(tray_icon, tray_item):
    applog.open_log(log_path)


def open_settings_window(tray_icon, tray_item):
    def show():
        from settings_dialog import open_settings
        open_settings()

    runner.submit_once("settings", show)


def retry_failed_items(tray_icon, tray_item):
    if api is None:
        return

    def work():  # a whole catch-up scan: off the GUI thread so windows and the tray stay responsive
        try:
            api.retry_failed(media_file_extensions)
        except Exception as e:
            log.error(f"retry of the failed items did not finish: {e!r}")

    threading.Thread(target=work, daemon=True, name="retry-failed").start()


def can_retry(tray_item):
    snapshot = status.snapshot()
    return api is not None and snapshot.failed > 0 and not snapshot.scanning


def delete_all_uploads(tray_icon, tray_item):
    def show_result(trashed):
        from tkinter import messagebox
        with hidden_root() as root:
            messagebox.showinfo("Immich Desktop Client", f"Moved {trashed} uploads to the Immich trash.", parent=root)

    def work():  # network loop: off the GUI thread so windows and the tray stay responsive
        trashed = api.delete_all_own_uploads()
        runner.submit(lambda: show_result(trashed))

    def confirm():
        if api is None:
            log.info("delete all uploads ignored: still connecting to the server")
            return
        from tkinter import messagebox
        with hidden_root() as root:
            confirmed = messagebox.askyesno(
                "Immich Desktop Client",
                "Move every file this app uploaded to the Immich trash?\n\n"
                "Files that already existed on the server are not touched. "
                "Trashed items can be restored in Immich until its trash is emptied.",
                parent=root)
        if confirmed:
            threading.Thread(target=work, daemon=True).start()

    runner.submit_once("delete-all", confirm)


def toggle_autostart(tray_icon, tray_item):
    if autostart.is_enabled():
        autostart.disable()
    else:
        autostart.enable(sys.executable)


def quit_app(tray_icon, tray_item):
    observer.stop()
    tray_icon.stop()
    runner.stop()


# Update the state in `on_clicked` and return the new state in
# a `checked` callable
tray = icon('Immich Desktop Client', load_icon(), menu=menu(
    item(lambda item: status.snapshot().text, lambda tray_icon, tray_item: None, enabled=False),  # status line
    item('Show progress...', show_progress_window),
    menu.SEPARATOR,
    item(
        'Sync directories to Immich',
        on_clicked,
        checked=lambda item: state),
    item('Start with Windows', toggle_autostart, checked=lambda item: autostart.is_enabled(),
         visible=sys.platform == 'win32' and getattr(sys, 'frozen', False)),
    item('Settings...', open_settings_window),
    item('Open config file', open_config),
    item('Open log', open_log),
    item('Retry failed items', retry_failed_items, enabled=can_retry),
    item('Move all uploads to Immich trash...', delete_all_uploads),
    item('Quit', quit_app),
))


def show_status(snapshot):
    """Tray tooltip and status line follow the status (best effort: Status logs a failing listener)."""
    tray.title = f"Immich Desktop Client: {snapshot.text}"[:127]  # the Windows tooltip limit
    tray.update_menu()


status.subscribe(show_status)
status.subscribe(Notifier(lambda title, message: tray.notify(message, title),
                          enabled=lambda: notifications_enabled))


def fail_startup(message):
    """A fatal error on the startup thread: show it on the GUI thread, then quit with exit code 1."""
    global exit_code
    exit_code = 1
    status.refused(message)

    def show_and_quit():
        try:
            announce(message)
        finally:
            quit_app(tray, None)

    runner.submit(show_and_quit)


def startup():
    """Connect to the server, catch up, then watch. Runs off the main thread so the tray is up meanwhile."""
    global api
    try:
        # at login the network is often not up yet, so keep trying for a while before giving up
        STARTUP_ATTEMPTS = 20
        for attempt in range(1, STARTUP_ATTEMPTS + 1):
            try:
                api = Immich(immich_host, api_key, album_name,
                             live_delete=delete_options.get("live", False),
                             catch_up_delete=delete_options.get("catch_up", False),
                             recursive=recursive,
                             album_by_year=config["api"].get("album_by_year", False),
                             status=status)
                break
            except UnsupportedServerError as e:
                return fail_startup(f"Refusing to start: {e}. Immich 3.0.0 or newer is required.")
            except InvalidServerResponseError as e:
                return fail_startup(f"Refusing to start: {e}")
            except ServerUnreachableError as e:
                if attempt == STARTUP_ATTEMPTS:
                    return fail_startup(f"Could not reach the Immich server: {e}")
                status.server_unreachable()
                log.warning(f"Immich server not reachable yet ({e}); retrying in 30 seconds")
                sleep(30)
        status.server_reachable()
        if api.test_connection() in (401, 403):
            return fail_startup("The Immich server rejected the API key. Open the settings and check it.")
        api.upload_all_images(directories_to_watch, media_file_extensions)

        for directory in existing_directories(directories_to_watch):
            try:
                observer.schedule(event_handler, directory, recursive=recursive)
                log.info("watching directory: " + directory)
            except OSError as e:
                log.warning(f"could not watch {directory}: {e!r}")
        observer.start()
    except Exception as e:
        log.exception("startup failed")
        fail_startup(f"The app could not start: {e!r}")


def begin(tray_icon):
    tray_icon.visible = True
    threading.Thread(target=startup, daemon=True, name="startup").start()


if sys.platform == "darwin":
    tray.run(setup=begin)
else:
    tray.run_detached(setup=begin)
    runner.run()  # blocks the main thread, executing GUI tasks, until Quit
instance_lock.release()
sys.exit(exit_code)
