import logging
import sys
import threading

import pytest

import applog


@pytest.fixture(autouse=True)
def _shutdown_logging():
    yield
    applog.shutdown_logging()


@pytest.fixture
def log_file(tmp_path):
    path = applog.setup_logging(tmp_path)
    return path


def read_log(path):
    for handler in logging.getLogger().handlers:
        handler.flush()
    return path.read_text(encoding="utf-8")


def test_log_records_land_in_the_log_file_in_the_config_dir(log_file, tmp_path):
    logging.getLogger("x").info("hallo")

    assert log_file == tmp_path / "immich-desktop-client.log"
    text = read_log(log_file)
    assert "hallo" in text and "INFO" in text


def test_the_log_rotates_and_keeps_three_files_at_most(log_file):
    logger = logging.getLogger("x")
    for _ in range(40):
        logger.info("x" * 100_000)  # ~4 MB in total

    names = sorted(p.name for p in log_file.parent.iterdir())
    assert names == ["immich-desktop-client.log", "immich-desktop-client.log.1",
                     "immich-desktop-client.log.2"]
    assert all(p.stat().st_size <= 1024 * 1024 + 100_100 for p in log_file.parent.iterdir())


def test_print_and_stderr_output_land_in_the_log(tmp_path):
    # set up inside the test: pytest's own capture swaps sys.stdout between fixture setup and the call
    log_file = applog.setup_logging(tmp_path)
    print("from print")
    sys.stderr.write("from stderr\n")

    text = read_log(log_file)
    assert "from print" in text and "from stderr" in text


def test_redirection_works_when_there_is_no_console(tmp_path, monkeypatch):
    monkeypatch.setattr(sys, "stdout", None)  # what a windowed exe has
    monkeypatch.setattr(sys, "stderr", None)
    path = applog.setup_logging(tmp_path)
    try:
        print("still logged")
        assert "still logged" in read_log(path)
    finally:
        applog.shutdown_logging()


def test_uncaught_exceptions_in_threads_and_the_main_thread_are_logged(log_file):
    def boom():
        raise RuntimeError("worker exploded")

    thread = threading.Thread(target=boom)
    thread.start()
    thread.join()
    try:
        raise ValueError("main exploded")
    except ValueError:
        sys.excepthook(*sys.exc_info())

    text = read_log(log_file)
    assert "worker exploded" in text and "main exploded" in text


def test_shutdown_restores_the_streams(tmp_path):
    before = (sys.stdout, sys.stderr, sys.excepthook)
    applog.setup_logging(tmp_path)
    applog.shutdown_logging()

    assert (sys.stdout, sys.stderr, sys.excepthook) == before


def test_a_registered_secret_never_reaches_the_log(log_file):
    applog.register_secret("s3cr3t-key")
    logging.getLogger("x").info("sending x-api-key s3cr3t-key to the server")
    logging.getLogger("x").error("failed", exc_info=RuntimeError("401 for key s3cr3t-key"))
    print("stdout also s3cr3t-key")

    text = read_log(log_file)
    assert "s3cr3t-key" not in text
    assert "sending x-api-key" in text and "***" in text


def test_open_log_hands_the_path_to_the_opener(tmp_path):
    opened = []

    applog.open_log(tmp_path / "x.log", opener=opened.append)

    assert opened == [tmp_path / "x.log"]


def test_open_log_reports_the_path_when_nothing_can_open_it(tmp_path, caplog):
    with caplog.at_level(logging.INFO):
        applog.open_log(tmp_path / "x.log", opener=None)

    assert str(tmp_path / "x.log") in caplog.text
