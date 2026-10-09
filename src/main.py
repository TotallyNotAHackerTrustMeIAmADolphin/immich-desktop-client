import mimetypes
import os
import sys
from time import sleep
from pathlib import Path

from PIL import Image
from pystray import Icon as icon, Menu as menu, MenuItem as item
from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

import autostart
from single_instance import acquire
from config import default_config_dir, load_config, write_template_config
from immich import Immich, ServerUnreachableError, UnsupportedServerError, is_media_file


def on_clicked(icon, item):
    global state
    state = not item.checked
    if state is True:
        print("starting synchronisation")
    else:
        print("ending synchronisation")


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
            print(f"File {event.src_path} has been created!")
            try:
                api.created(event.src_path)
            except Exception as e:  # an escaping exception would silently end the watcher thread
                print(f"error handling creation of {event.src_path}: {e!r}")

    def on_deleted(self, event):
        global state
        if state and not event.is_directory and is_media_file(event.src_path, media_file_extensions):
            print(f"File {event.src_path} has been deleted!")
            try:
                api.delete(event.src_path)
            except Exception as e:
                print(f"error handling deletion of {event.src_path}: {e!r}")

    def on_moved(self, event):
        global state
        if (state and not event.is_directory and is_media_file(event.src_path, media_file_extensions)
                and is_media_file(event.dest_path, media_file_extensions)):
            print(f"File {event.src_path} has been moved to {event.dest_path}!")
            try:
                api.move(event.src_path, event.dest_path)
            except Exception as e:
                print(f"error handling move of {event.src_path}: {e!r}")

    def on_modified(self, event):
        global state
        if state and not event.is_directory and is_media_file(event.src_path, media_file_extensions):
            sleep(1)  # let the writer finish before hashing
            print(f"File {event.src_path} has been modified!")
            try:
                api.modify(event.src_path)
            except Exception as e:
                print(f"error handling modification of {event.src_path}: {e!r}")


instance_lock = acquire()
if instance_lock is None:
    sys.exit("Immich Desktop Client is already running.")

# Load Config
config = load_config(default_config_dir())
if config is None:
    sys.exit(f"No usable configuration found. Edit {write_template_config(default_config_dir())} and start again.")

media_file_extensions = get_extensions_for_type()

immich_host = config["api"]["url"]
album_name = config["api"].get("album")
if album_name is not None and str(album_name).startswith("<"):
    album_name = None  # still the template placeholder
api_key = config["api"]["key"]
directories_to_watch = config["watchdog"]["directories"]
delete_options = config.get("delete") or {}

state = True

recursive = config["watchdog"].get("recursive", True)

# at login the network is often not up yet, so keep trying for a while before giving up
STARTUP_ATTEMPTS = 20
for attempt in range(1, STARTUP_ATTEMPTS + 1):
    try:
        api = Immich(immich_host, api_key, album_name,
                     live_delete=delete_options.get("live", False),
                     catch_up_delete=delete_options.get("catch_up", False),
                     recursive=recursive,
                     album_by_year=config["api"].get("album_by_year", False))
        break
    except UnsupportedServerError as e:
        sys.exit(f"Refusing to start: {e}. Immich 3.0.0 or newer is required.")
    except ServerUnreachableError as e:
        if attempt == STARTUP_ATTEMPTS:
            sys.exit(f"Could not reach the Immich server: {e}")
        print(f"Immich server not reachable yet ({e}); retrying in 30 seconds")
        sleep(30)
api.test_connection()
api.upload_all_images(directories_to_watch, media_file_extensions)

# Create observer and event handler
observer = Observer()
event_handler = MyHandler()
for directory in directories_to_watch:
    observer.schedule(event_handler, directory, recursive=recursive)
    print("watching directory: " + directory)
observer.start()

def load_icon():
    try:
        return Image.open(default_config_dir() / 'icon.ico')
    except OSError:
        return Image.new('RGB', (64, 64), (66, 80, 175))  # plain fallback when the icon file is missing


def open_config(tray_icon, tray_item):
    path = write_template_config(default_config_dir())
    if hasattr(os, "startfile"):
        os.startfile(path)
    else:
        print(f"config file: {path}")


def delete_all_uploads(tray_icon, tray_item):
    import tkinter
    from tkinter import messagebox
    root = tkinter.Tk()
    root.withdraw()
    root.attributes('-topmost', True)
    confirmed = messagebox.askyesno(
        "Immich Desktop Client",
        "Move every file this app uploaded to the Immich trash?\n\n"
        "Files that already existed on the server are not touched. "
        "Trashed items can be restored in Immich until its trash is emptied.",
        parent=root)
    if confirmed:
        trashed = api.delete_all_own_uploads()
        messagebox.showinfo("Immich Desktop Client", f"Moved {trashed} uploads to the Immich trash.", parent=root)
    root.destroy()


def toggle_autostart(tray_icon, tray_item):
    if autostart.is_enabled():
        autostart.disable()
    else:
        autostart.enable(sys.executable)


def quit_app(tray_icon, tray_item):
    observer.stop()
    tray_icon.stop()


# Update the state in `on_clicked` and return the new state in
# a `checked` callable
icon('Immich Desktop Client', load_icon(), menu=menu(
    item(
        'Sync directories to Immich',
        on_clicked,
        checked=lambda item: state),
    item('Start with Windows', toggle_autostart, checked=lambda item: autostart.is_enabled(),
         visible=sys.platform == 'win32' and getattr(sys, 'frozen', False)),
    item('Open config file', open_config),
    item('Move all uploads to Immich trash...', delete_all_uploads),
    item('Quit', quit_app),
)).run()
instance_lock.release()
