import mimetypes
import sys
from pathlib import Path

import yaml
from PIL import Image
from pystray import Icon as icon, Menu as menu, MenuItem as item
from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

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

    # TODO: make these event handlers work
    #   def on_moved(self, event):
    #       if not event.is_directory and event.src_path.endswith(".png") or event.src_path.endswith(".jpg") or event.src_path.endswith(".jpeg"):
    #           print(f"File {event.src_path} has been moved!")
    #           api.move(event.src_path,event.dest_path)
    #  def on_modified(self, event):
    #      if not event.is_directory and event.src_path.endswith(".png") or event.src_path.endswith(".jpg") or event.src_path.endswith(".jpeg"):
    #          print(f"File {event.src_path} has been modified!")
    #          api.modify(event.src_path)


# Load Config
with open(str(Path.home()) + '/.Immich-desktop-client/config.yaml', 'rt') as file:
    config = yaml.safe_load(file)

media_file_extensions = get_extensions_for_type()

immich_host = config["api"]["url"]
album_name = config["api"]["album"]
api_key = config["api"]["key"]
directories_to_watch = config["watchdog"]["directories"]

state = True

try:
    api = Immich(immich_host, api_key, album_name)
except UnsupportedServerError as e:
    sys.exit(f"Refusing to start: {e}. Immich 3.0.0 or newer is required.")
except ServerUnreachableError as e:
    sys.exit(f"Could not reach the Immich server: {e}")
api.test_connection()
api.print_shelve()
api.upload_all_images(directories_to_watch, media_file_extensions)

# Create observer and event handler
observer = Observer()
event_handler = MyHandler()
for directory in directories_to_watch:
    observer.schedule(event_handler, directory, recursive=True)
    print("watching directory: " + directory)
observer.start()

# Update the state in `on_clicked` and return the new state in
# a `checked` callable
icon('test', Image.open(str(Path.home()) + '/.Immich-desktop-client/icon.ico'), menu=menu(
    item(
        'Sync directories to Immich',
        on_clicked,
        checked=lambda item: state)
)
     ).run()
