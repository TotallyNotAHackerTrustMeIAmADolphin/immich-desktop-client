"""What the client is doing right now, for any front end (tray, progress window, log) to show.

The worker threads report into a Status; front ends either subscribe (called on the reporting thread, keep it
cheap) or poll snapshot(). Nothing in here touches Tk or the tray, so it is safe from any thread.
"""
import enum
import logging
import threading
from dataclasses import dataclass, field

log = logging.getLogger(__name__)

MAX_LISTED_FAILURES = 200


class State(enum.Enum):
    STARTING = "Starting"
    CATCHING_UP = "Catching up"
    UPLOADING = "Uploading"
    IDLE = "Idle"
    PAUSED = "Paused"
    UNREACHABLE = "Server unreachable, retrying"
    REFUSED = "Refused"


@dataclass(frozen=True)
class Snapshot:
    state: State
    text: str
    uploaded: int = 0
    done: int = 0
    total: int = 0
    failed: int = 0
    roots_skipped: int = 0
    current_file: str = None
    failures: list = field(default_factory=list)  # (path, reason), the most recent MAX_LISTED_FAILURES
    scanning: bool = False
    scans_finished: int = 0  # the catch-up scans completed so far, with what the latest one did:
    scan_uploaded: int = 0
    scan_failed: int = 0


class Status:
    def __init__(self):
        self.__lock = threading.Lock()
        self.__listeners = []
        self.__scan_seen = False
        self.__scanning = False
        self.__paused = False
        self.__unreachable = False
        self.__refused = None
        self.__uploaded = 0
        self.__done = 0
        self.__total = 0
        self.__current = None
        self.__failures = {}  # path -> reason, insertion ordered
        self.__skipped_roots = set()
        self.__scans_finished = 0
        self.__scan_uploaded = self.__scan_failed = 0  # of the scan in progress, then of the last one

    # ---- reporting (called by the worker threads) -------------------------------------------------------

    def scan_started(self):
        with self.__lock:
            self.__scan_seen = self.__scanning = True
            self.__skipped_roots.clear()
            self.__scan_uploaded = self.__scan_failed = 0
        self.__changed()

    def scan_finished(self):
        with self.__lock:
            self.__scanning = False
            self.__scans_finished += 1
            self.__reset_batch_if_complete()
        self.__changed()

    def queue(self, count):
        """count more files are known to be waiting for upload (so the progress can say "n of m")."""
        with self.__lock:
            self.__total += count
        self.__changed()

    def upload_started(self, path):
        with self.__lock:
            if self.__total - self.__done <= 0:
                self.__total += 1  # a live event nobody announced: a batch of one
            self.__current = path
        self.__changed()

    def upload_finished(self, path):
        with self.__lock:
            self.__uploaded += 1
            if self.__scanning:
                self.__scan_uploaded += 1
            self.__done += 1
            self.__failures.pop(path, None)
            self.__current = None
            self.__reset_batch_if_complete()
        self.__changed()

    def upload_failed(self, path, reason):
        with self.__lock:
            if self.__current == path:
                self.__done += 1
                self.__current = None
            if self.__scanning:
                self.__scan_failed += 1
            self.__failures.pop(path, None)
            self.__failures[path] = reason  # re-insert: the most recent failure is last
            self.__reset_batch_if_complete()
        self.__changed()

    def clear_failures(self):
        """Forget the listed failures; a retry puts back whatever fails again."""
        with self.__lock:
            self.__failures.clear()
        self.__changed()

    def root_skipped(self, root):
        with self.__lock:
            self.__skipped_roots.add(root)
        self.__changed()

    def set_paused(self, paused):
        with self.__lock:
            self.__paused = bool(paused)
        self.__changed()

    def server_unreachable(self):
        with self.__lock:
            self.__unreachable = True
        self.__changed()

    def server_reachable(self):
        with self.__lock:
            changed = self.__unreachable
            self.__unreachable = False
        if changed:
            self.__changed()

    def refused(self, reason):
        with self.__lock:
            self.__refused = reason
        self.__changed()

    # ---- consuming ----------------------------------------------------------------------------------------

    def subscribe(self, listener):
        with self.__lock:
            self.__listeners.append(listener)

    def snapshot(self):
        with self.__lock:
            return self.__snapshot()

    # ---- internals ----------------------------------------------------------------------------------------

    def __reset_batch_if_complete(self):
        if not self.__scanning and self.__current is None and self.__done >= self.__total:
            self.__done = self.__total = 0

    def __changed(self):
        with self.__lock:
            snapshot = self.__snapshot()
            listeners = list(self.__listeners)
        for listener in listeners:
            try:
                listener(snapshot)
            except Exception as e:  # a broken front end must never break the sync
                log.warning(f"status listener failed: {e!r}")

    def __snapshot(self):
        if self.__refused is not None:
            state, text = State.REFUSED, f"Refused: {self.__refused}"
        elif self.__unreachable:
            state, text = State.UNREACHABLE, State.UNREACHABLE.value
        elif self.__current is not None:
            state = State.UPLOADING
            text = f"Uploading {min(self.__done + 1, self.__total)} of {self.__total}"
        elif self.__scanning:
            state, text = State.CATCHING_UP, State.CATCHING_UP.value
        elif self.__paused:
            state, text = State.PAUSED, State.PAUSED.value
        elif not self.__scan_seen:
            state, text = State.STARTING, State.STARTING.value
        else:
            state, text = State.IDLE, State.IDLE.value

        suffix = []
        if self.__failures:
            suffix.append(f"{len(self.__failures)} failed")
        if self.__skipped_roots:
            count = len(self.__skipped_roots)
            suffix.append(f"{count} root{'s' if count != 1 else ''} skipped")
        if suffix and state is not State.REFUSED:
            text = " · ".join([text] + suffix)

        failures = list(self.__failures.items())[-MAX_LISTED_FAILURES:]
        return Snapshot(state=state, text=text, uploaded=self.__uploaded, done=self.__done, total=self.__total,
                        failed=len(self.__failures), roots_skipped=len(self.__skipped_roots),
                        current_file=self.__current, failures=failures,
                        scanning=self.__scanning, scans_finished=self.__scans_finished, scan_uploaded=self.__scan_uploaded,
                        scan_failed=self.__scan_failed)
