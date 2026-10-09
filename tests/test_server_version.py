import pytest

import immich


def build(tmp_path):
    return immich.Immich("http://immich.test/api", "key", album_name="a", album_id="1",
                         shelve_path=str(tmp_path / "s"))


@pytest.mark.parametrize("version", [
    {"major": 3, "minor": 0, "patch": 0},
    {"major": 3, "minor": 1, "patch": 0},
    {"major": 4, "minor": 0, "patch": 2},
])
def test_supported_versions_are_accepted(api, tmp_path, version):
    api.version = version
    build(tmp_path)


@pytest.mark.parametrize("version", [
    {"major": 2, "minor": 9, "patch": 9},
    {"major": 1, "minor": 118, "patch": 0},
    {},
    {"major": "x"},
    "garbage",
])
def test_old_or_unparseable_versions_are_refused(api, tmp_path, version):
    api.version = version
    with pytest.raises(immich.UnsupportedServerError):
        build(tmp_path)


def test_unreachable_server_is_a_transient_error_not_a_refusal(api, tmp_path):
    api.unreachable = True
    with pytest.raises(immich.ServerUnreachableError):
        build(tmp_path)
    assert not issubclass(immich.ServerUnreachableError, immich.UnsupportedServerError)
