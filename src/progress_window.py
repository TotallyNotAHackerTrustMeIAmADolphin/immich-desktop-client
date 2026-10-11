"""The small progress window: a bar, what is being uploaded, and the files that failed.

view_model() is the testable part; open_progress() only draws it and polls a Status, so worker threads never
touch Tk (see GuiRunner).
"""
from dataclasses import dataclass

from status import State

TITLE = "Immich Desktop Client - Progress"
POLL_MILLISECONDS = 500


@dataclass(frozen=True)
class ProgressView:
    headline: str
    mode: str  # "determinate", "indeterminate" or "idle"
    fraction: float
    current_file: str
    failures: list


def view_model(snapshot):
    busy = snapshot.state in (State.STARTING, State.CATCHING_UP, State.UPLOADING, State.UNREACHABLE)
    if busy and snapshot.total > 0:
        mode, fraction = "determinate", min(snapshot.done / snapshot.total, 1.0)
    elif busy:
        mode, fraction = "indeterminate", 0.0
    else:
        mode, fraction = "idle", 0.0
    return ProgressView(
        headline=snapshot.text,
        mode=mode,
        fraction=fraction,
        current_file=snapshot.current_file or "",
        failures=[f"{path}  -  {reason}" for path, reason in snapshot.failures],
    )


def open_progress(status, should_close=lambda: False):
    """Show the window and block (on the GUI thread) until it is closed."""
    import tkinter
    from tkinter import ttk

    window = tkinter.Tk()
    window.title(TITLE)
    window.attributes('-topmost', True)
    window.minsize(480, 280)
    frame = ttk.Frame(window, padding=12)
    frame.pack(fill="both", expand=True)

    headline = tkinter.StringVar()
    current = tkinter.StringVar()
    ttk.Label(frame, textvariable=headline, font=("TkDefaultFont", 11, "bold")).pack(anchor="w")
    bar = ttk.Progressbar(frame, length=440, maximum=1.0)
    bar.pack(fill="x", pady=8)
    ttk.Label(frame, textvariable=current, wraplength=440).pack(anchor="w")
    ttk.Label(frame, text="Failed items (the app retries them with \"Retry failed items\" in the tray menu):").pack(
        anchor="w", pady=(10, 2))
    failures = tkinter.Listbox(frame, height=6)
    failures.pack(fill="both", expand=True)
    ttk.Button(frame, text="Close", command=window.destroy).pack(anchor="e", pady=(10, 0))

    state = {"mode": None}

    def refresh():
        snapshot = status.snapshot()
        if should_close() or snapshot.state is State.REFUSED:
            window.destroy()  # the app is quitting, or a fatal window is waiting for the GUI thread
            return
        view = view_model(snapshot)
        headline.set(view.headline)
        current.set(view.current_file)
        if view.mode != state["mode"]:
            bar.stop()
            if view.mode == "indeterminate":
                bar.configure(mode="indeterminate")
                bar.start(40)
            else:
                bar.configure(mode="determinate")
            state["mode"] = view.mode
        if view.mode != "indeterminate":
            bar["value"] = view.fraction
        if list(failures.get(0, tkinter.END)) != view.failures:
            failures.delete(0, tkinter.END)
            for row in view.failures:
                failures.insert(tkinter.END, row)
        window.after(POLL_MILLISECONDS, refresh)

    refresh()
    window.mainloop()
