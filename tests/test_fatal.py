import logging

import pytest

import fatal


def test_a_fatal_error_is_logged_shown_and_ends_the_app(caplog):
    shown = []

    with caplog.at_level(logging.INFO), pytest.raises(SystemExit) as exit_info:
        fatal.die("Refusing to start: server too old", show=shown.append)

    assert exit_info.value.code == 1
    assert shown == ["Refusing to start: server too old"]
    assert "Refusing to start: server too old" in caplog.text
    assert [r.levelname for r in caplog.records] == ["ERROR"]


def test_a_missing_display_does_not_stop_the_app_from_exiting(caplog):
    def no_display(message):
        raise RuntimeError("no display")

    with caplog.at_level(logging.INFO), pytest.raises(SystemExit) as exit_info:
        fatal.die("could not reach the server", show=no_display)

    assert exit_info.value.code == 1
    assert "could not reach the server" in caplog.text


def test_dialogs_can_be_switched_off_for_unattended_runs(monkeypatch):
    monkeypatch.setenv(fatal.NO_DIALOGS_ENV, "1")
    shown = []

    with pytest.raises(SystemExit):
        fatal.die("boom", show=shown.append)

    assert shown == []


def test_announce_logs_and_shows_but_does_not_exit(caplog):
    shown = []

    with caplog.at_level(logging.INFO):
        fatal.announce("heads up", show=shown.append)

    assert shown == ["heads up"]
    assert "heads up" in caplog.text
