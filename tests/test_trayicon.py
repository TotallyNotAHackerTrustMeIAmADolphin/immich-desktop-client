import trayicon


def touch(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"ico")
    return path


def test_profile_icon_wins_over_bundled_and_source(tmp_path):
    profile = touch(tmp_path / "profile" / "icon.ico")
    touch(tmp_path / "bundle" / "resources" / "icon.ico")
    touch(tmp_path / "repo" / "resources" / "icon.ico")

    found = trayicon.resolve_icon_path(tmp_path / "profile", meipass=tmp_path / "bundle",
                                       source_dir=tmp_path / "repo" / "src")

    assert found == profile


def test_bundle_icon_used_when_profile_has_none(tmp_path):
    bundled = touch(tmp_path / "bundle" / "resources" / "icon.ico")

    found = trayicon.resolve_icon_path(tmp_path / "profile", meipass=tmp_path / "bundle",
                                       source_dir=tmp_path / "repo" / "src")

    assert found == bundled


def test_source_checkout_icon_used_when_not_frozen(tmp_path):
    from_repo = touch(tmp_path / "repo" / "resources" / "icon.ico")

    found = trayicon.resolve_icon_path(tmp_path / "profile", meipass=None,
                                       source_dir=tmp_path / "repo" / "src")

    assert found == from_repo


def test_none_when_no_icon_anywhere(tmp_path):
    assert trayicon.resolve_icon_path(tmp_path / "profile", meipass=None,
                                      source_dir=tmp_path / "repo" / "src") is None
