"""Desktop notifications for the few status changes worth interrupting someone for."""
import logging

from status import State

log = logging.getLogger(__name__)

TITLE = "Immich Desktop Client"


class Notifier:
    """Subscribe an instance to a Status. notify(title, message) is the (best effort) toast."""

    def __init__(self, notify, enabled=lambda: True):
        self.__notify = notify
        self.__enabled = enabled
        self.__was_unreachable = False
        self.__scans_seen = 0

    def __call__(self, snapshot):
        try:
            self.__handle(snapshot)
        except Exception as e:  # a missing toast backend must never disturb the sync
            log.warning(f"could not show a notification: {e!r}")

    def __handle(self, snapshot):
        unreachable = snapshot.state is State.UNREACHABLE
        became_unreachable = unreachable and not self.__was_unreachable
        self.__was_unreachable = unreachable

        scan_done = snapshot.scans_finished > self.__scans_seen
        self.__scans_seen = snapshot.scans_finished

        if not self.__enabled():
            return
        if became_unreachable:
            self.__notify(TITLE, "The Immich server cannot be reached. Retrying in the background.")
        if scan_done and snapshot.scan_failed > 0:
            self.__notify(TITLE, f"Catch-up finished: {snapshot.scan_uploaded} uploaded, "
                                 f"{snapshot.scan_failed} failed. See the log for details.")
