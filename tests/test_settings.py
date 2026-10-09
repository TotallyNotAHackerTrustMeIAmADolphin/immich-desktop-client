import yaml

import immich
import settings
from config import CONFIG_FILENAME, load_config

FORM = {
    "url": "https://immich.example/api",
    "key": "secret",
    "album": "",
    "album_by_year": True,
    "recursive": False,
    "directories": ["/pics", "/shots"],
    "live_delete": True,
    "catch_up_delete": False,
}


def supported(host, key):
    return None


def test_form_converts_to_the_config_layout_and_back():
    config = settings.config_from_form(FORM)

    assert config["api"] == {"url": "https://immich.example/api", "key": "secret", "album_by_year": True}
    assert config["watchdog"] == {"recursive": False, "directories": ["/pics", "/shots"]}
    assert config["delete"] == {"live": True, "catch_up": False}
    assert settings.form_from_config(config) == {**FORM}


def test_named_album_is_kept():
    assert settings.config_from_form({**FORM, "album": "laptop"})["api"]["album"] == "laptop"


def test_valid_form_has_no_errors():
    assert settings.validate_form(FORM, check_server=supported) == ([], [])


def test_missing_fields_are_reported_without_contacting_the_server():
    def must_not_be_called(host, key):
        raise AssertionError("server contacted for an incomplete form")

    errors, _ = settings.validate_form({**FORM, "url": " ", "key": "", "directories": []},
                                       check_server=must_not_be_called)
    assert len(errors) == 3


def test_unsupported_server_blocks_saving():
    def old(host, key):
        raise immich.UnsupportedServerError("server version 2.7.0 is older than the required 3.0.0")

    errors, _ = settings.validate_form(FORM, check_server=old)
    assert errors and "2.7.0" in errors[0]


def test_unreachable_server_only_warns():
    def down(host, key):
        raise immich.ServerUnreachableError("no route")

    errors, warnings = settings.validate_form(FORM, check_server=down)
    assert errors == [] and len(warnings) == 1


def test_save_writes_a_loadable_config_atomically(tmp_path):
    settings.save_config(tmp_path, settings.config_from_form(FORM))

    assert load_config(tmp_path)["api"]["key"] == "secret"
    assert [p.name for p in tmp_path.iterdir()] == [CONFIG_FILENAME]  # no temp file left behind


def test_save_over_a_directory_named_config_yaml_moves_it_aside(tmp_path):
    (tmp_path / CONFIG_FILENAME).mkdir()

    settings.save_config(tmp_path, settings.config_from_form(FORM))

    assert (tmp_path / CONFIG_FILENAME).is_file()
    assert yaml.safe_load((tmp_path / CONFIG_FILENAME).read_text())["api"]["url"] == FORM["url"]


def test_placeholder_config_prefills_an_empty_form():
    from config import TEMPLATE
    form = settings.form_from_config(yaml.safe_load(TEMPLATE))
    assert form["url"] == "" and form["key"] == "" and form["directories"] == []


def test_wrong_url_is_reported_as_such_not_as_an_old_server():
    def wrong_url(host, key):
        raise immich.InvalidServerResponseError("https://x answered HTTP 404; check that the URL ends in /api")

    errors, _ = settings.validate_form(FORM, check_server=wrong_url)
    assert errors and "/api" in errors[0] and "3.0.0" not in errors[0]
