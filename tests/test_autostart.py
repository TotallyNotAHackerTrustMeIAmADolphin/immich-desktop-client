import autostart


class FakeRunKey:
    def __init__(self):
        self.values = {}

    def get(self, name):
        return self.values.get(name)

    def set(self, name, value):
        self.values[name] = value

    def delete(self, name):
        self.values.pop(name, None)


def test_enable_registers_the_command_and_disable_removes_it():
    key = FakeRunKey()

    assert not autostart.is_enabled(key)
    autostart.enable(r"C:\Apps\immich.exe", key)
    assert autostart.is_enabled(key)
    assert key.values[autostart.VALUE_NAME] == r'"C:\Apps\immich.exe"'

    autostart.disable(key)
    assert not autostart.is_enabled(key)


def test_disable_when_not_enabled_is_harmless():
    autostart.disable(FakeRunKey())


def test_without_a_registry_everything_is_a_safe_no_op():
    assert autostart.is_enabled(None) is False
    assert autostart.enable("x", None) is False
    assert autostart.disable(None) is False
