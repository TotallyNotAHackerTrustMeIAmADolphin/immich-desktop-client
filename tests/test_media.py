from immich import is_media_file

EXTENSIONS = (".jpg", ".png", ".mp4")


def test_uppercase_extensions_are_media():
    assert is_media_file("/pics/IMG_0001.JPG", EXTENSIONS)
    assert is_media_file("/pics/clip.Mp4", EXTENSIONS)


def test_other_files_are_not_media():
    assert not is_media_file("/pics/notes.txt", EXTENSIONS)
