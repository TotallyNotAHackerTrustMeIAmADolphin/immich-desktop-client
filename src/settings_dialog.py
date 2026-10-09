"""The tkinter settings window. All logic lives in settings.py; this file only draws the form."""
import tkinter
from tkinter import filedialog, messagebox, ttk

import settings
from config import default_config_dir, load_config

TITLE = "Immich Desktop Client - Settings"


def open_settings(on_saved=None, config_dir=None):
    """Show the settings window (blocking). Returns True if the settings were saved."""
    config_dir = config_dir or default_config_dir()
    form = settings.form_from_config(load_config(config_dir) or {})
    saved = False

    window = tkinter.Tk()
    window.title(TITLE)
    window.resizable(False, False)
    frame = ttk.Frame(window, padding=12)
    frame.grid()

    url = tkinter.StringVar(value=form["url"])
    key = tkinter.StringVar(value=form["key"])
    album = tkinter.StringVar(value=form["album"])
    flags = {name: tkinter.BooleanVar(value=form[name])
             for name in ("album_by_year", "recursive", "live_delete", "catch_up_delete")}

    def add_row(row, label, variable, show=None):
        ttk.Label(frame, text=label).grid(row=row, column=0, sticky="w", pady=2)
        ttk.Entry(frame, textvariable=variable, width=48, show=show).grid(row=row, column=1, columnspan=2, pady=2)

    add_row(0, "Server URL (ending in /api)", url)
    add_row(1, "API key", key, show="*")
    add_row(2, "Album name (optional)", album)

    ttk.Label(frame, text="Folders to watch").grid(row=3, column=0, sticky="nw", pady=2)
    folders = tkinter.Listbox(frame, width=48, height=5)
    folders.grid(row=3, column=1, pady=2)
    for directory in form["directories"]:
        folders.insert(tkinter.END, directory)
    buttons = ttk.Frame(frame)
    buttons.grid(row=3, column=2, sticky="n", padx=6)
    ttk.Button(buttons, text="Add...", command=lambda: add_folder()).pack(fill="x")
    ttk.Button(buttons, text="Remove", command=lambda: remove_folder()).pack(fill="x", pady=2)

    def add_folder():
        chosen = filedialog.askdirectory(parent=window)
        if chosen:
            folders.insert(tkinter.END, chosen)

    def remove_folder():
        for index in reversed(folders.curselection()):
            folders.delete(index)

    checkboxes = (
        ("recursive", "Include sub-folders"),
        ("album_by_year", "File uploads into one album per year"),
        ("live_delete", "Move the upload to the Immich trash when I delete a file"),
        ("catch_up_delete", "At startup, trash uploads whose file is gone (only when the folder is reachable)"),
    )
    for row, (name, label) in enumerate(checkboxes, start=4):
        ttk.Checkbutton(frame, text=label, variable=flags[name]).grid(row=row, column=0, columnspan=3, sticky="w")

    def save():
        nonlocal saved
        edited = {"url": url.get(), "key": key.get(), "album": album.get(),
                  "directories": list(folders.get(0, tkinter.END)),
                  **{name: variable.get() for name, variable in flags.items()}}
        errors, warnings = settings.validate_form(edited)
        if errors:
            messagebox.showerror(TITLE, "\n".join(errors), parent=window)
            return
        if warnings and not messagebox.askyesno(TITLE, "\n".join(warnings) + "\n\nSave anyway?", parent=window):
            return
        settings.save_config(config_dir, settings.config_from_form(edited))
        saved = True
        if on_saved:
            on_saved()
        messagebox.showinfo(TITLE, "Settings saved. Restart the app for them to take effect.", parent=window)
        window.destroy()

    actions = ttk.Frame(frame)
    actions.grid(row=8, column=0, columnspan=3, sticky="e", pady=(10, 0))
    ttk.Button(actions, text="Cancel", command=window.destroy).pack(side="right", padx=4)
    ttk.Button(actions, text="Save", command=save).pack(side="right")

    window.mainloop()
    return saved
