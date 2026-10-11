import logging
import os
import sys
import threading
from logging.handlers import RotatingFileHandler
from pathlib import Path

LOG_FILENAME = "immich-desktop-client.log"

_handler = None
_saved = None
_secrets = []


def register_secret(value):
    """Never let this value (an API key) reach the log; it is replaced by *** wherever it appears."""
    if value and value not in _secrets:
        _secrets.append(str(value))


class _RedactingFormatter(logging.Formatter):
    def format(self, record):
        text = super().format(record)  # includes the traceback, so exception texts are covered too
        for secret in _secrets:
            text = text.replace(secret, "***")
        return text


class _LogStream:
    """File-like stand-in for sys.stdout/sys.stderr, which are None in a windowed exe."""

    def __init__(self, logger, level):
        self.__logger = logger
        self.__level = level
        self.__buffer = ""
        self.__busy = threading.local()

    def write(self, text):
        if getattr(self.__busy, "active", False):
            return len(text)  # the logging machinery itself wrote here: don't recurse
        self.__busy.active = True
        try:
            self.__buffer += text
            *lines, self.__buffer = self.__buffer.split("\n")
            for line in lines:
                if line.strip():
                    self.__logger.log(self.__level, line)
        finally:
            self.__busy.active = False
        return len(text)

    def flush(self):
        pass

    def isatty(self):
        return False


def setup_logging(config_dir):
    global _handler, _saved
    shutdown_logging()
    path = Path(config_dir) / LOG_FILENAME
    path.parent.mkdir(parents=True, exist_ok=True)
    _handler = RotatingFileHandler(path, maxBytes=1024 * 1024, backupCount=2, encoding="utf-8")
    _handler.setFormatter(_RedactingFormatter("%(asctime)s %(levelname)s %(message)s"))
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.addHandler(_handler)

    _saved = (sys.stdout, sys.stderr, sys.excepthook, threading.excepthook)
    sys.stdout = _LogStream(logging.getLogger("stdout"), logging.INFO)
    sys.stderr = _LogStream(logging.getLogger("stderr"), logging.WARNING)

    def log_uncaught(exc_type, exc, tb):
        logging.getLogger("uncaught").error("uncaught exception", exc_info=(exc_type, exc, tb))

    def log_thread_uncaught(args):
        logging.getLogger("uncaught").error(
            f"uncaught exception in thread {args.thread.name if args.thread else '?'}",
            exc_info=(args.exc_type, args.exc_value, args.exc_traceback))

    sys.excepthook = log_uncaught
    threading.excepthook = log_thread_uncaught
    return path


def shutdown_logging():
    global _handler, _saved
    _secrets.clear()
    if _saved is not None:
        sys.stdout, sys.stderr, sys.excepthook, threading.excepthook = _saved
        _saved = None
    if _handler is not None:
        logging.getLogger().removeHandler(_handler)
        _handler.close()
        _handler = None


def open_log(path, opener=getattr(os, "startfile", None)):
    """Show the log file with the system's default program; where that is not possible, just say where it is."""
    if opener is None:
        logging.getLogger(__name__).info("log file: %s", path)
        return
    opener(path)
