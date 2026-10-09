from config import CONFIG_FILENAME, load_config, write_template_config


def test_loads_existing_config_file(tmp_path):
    (tmp_path / CONFIG_FILENAME).write_text("api:\n  key: abc\n")
    assert load_config(tmp_path) == {"api": {"key": "abc"}}


def test_missing_config_means_first_run(tmp_path):
    assert load_config(tmp_path) is None


def test_missing_config_directory_means_first_run(tmp_path):
    assert load_config(tmp_path / "does-not-exist") is None


def test_config_that_is_a_directory_is_renamed_aside(tmp_path):
    broken = tmp_path / CONFIG_FILENAME
    broken.mkdir()
    (broken / "example-config.yaml").write_text("x: 1")

    assert load_config(tmp_path) is None

    assert not broken.is_dir()
    aside = [p for p in tmp_path.iterdir() if p.name.startswith(CONFIG_FILENAME)]
    assert len(aside) == 1 and (aside[0] / "example-config.yaml").exists()


def test_repeated_directory_breakage_does_not_collide(tmp_path):
    for _ in range(2):
        (tmp_path / CONFIG_FILENAME).mkdir()
        assert load_config(tmp_path) is None
    assert len([p for p in tmp_path.iterdir() if p.name.startswith(CONFIG_FILENAME)]) == 2


def test_template_is_written_once_and_never_overwrites(tmp_path):
    path = write_template_config(tmp_path / "newdir")
    assert path.is_file() and "api:" in path.read_text()
    path.write_text("mine: true")
    write_template_config(tmp_path / "newdir")
    assert path.read_text() == "mine: true"
