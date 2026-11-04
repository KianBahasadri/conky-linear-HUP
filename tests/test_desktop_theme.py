import subprocess

import pytest

import watch_desktop_theme as theme


@pytest.mark.parametrize(
    ("scheme", "gtk_theme", "expected"),
    [
        ("prefer-dark", "Adwaita", "dark"),
        ("prefer-light", "Adwaita-dark", "light"),
        ("default", "Adwaita", "light"),
        ("default", "Yaru-Dark", "dark"),
        ("default", None, "light"),
        (None, "Adwaita-dark", "dark"),
        (None, "Adwaita", "light"),
        (None, None, "dark"),
    ],
)
def test_detect_theme_honors_explicit_preference_then_legacy_gtk_theme(
    monkeypatch, scheme, gtk_theme, expected,
):
    settings = {"color-scheme": scheme, "gtk-theme": gtk_theme}
    monkeypatch.setattr(theme, "read_setting", settings.get)
    assert theme.detect_theme() == expected


@pytest.mark.parametrize(
    "error",
    [FileNotFoundError(), subprocess.CalledProcessError(1, "gsettings"),
     subprocess.TimeoutExpired("gsettings", 2)],
)
def test_read_setting_tolerates_missing_or_unresponsive_settings(monkeypatch, error):
    def fail(*args, **kwargs):
        raise error

    monkeypatch.setattr(theme.subprocess, "run", fail)
    assert theme.read_setting("color-scheme") is None


def test_read_setting_decodes_gvariant_string(monkeypatch):
    def run(command, **kwargs):
        assert command == ["gsettings", "get", theme.SCHEMA, "color-scheme"]
        assert kwargs["timeout"] == 2 and kwargs["check"]
        return subprocess.CompletedProcess(command, 0, "'prefer-dark'\n")

    monkeypatch.setattr(theme.subprocess, "run", run)
    assert theme.read_setting("color-scheme") == "prefer-dark"


def test_listener_publishes_initial_theme_and_both_kinds_of_change(monkeypatch, tmp_path):
    path = tmp_path / "cache" / "desktop-theme"
    settings = {"color-scheme": "prefer-dark", "gtk-theme": "Adwaita"}
    monkeypatch.setattr(theme, "read_setting", settings.get)

    class Monitor:
        finished = False

        @property
        def stdout(self):
            assert path.read_text() == "dark\n", "snapshot must precede event handling"
            settings["color-scheme"] = "prefer-light"
            yield "color-scheme: 'prefer-light'\n"
            assert path.read_text() == "light\n"
            settings.update({"color-scheme": "default", "gtk-theme": "Yaru-dark"})
            yield "gtk-theme: 'Yaru-dark'\n"
            assert path.read_text() == "dark\n"
            settings["gtk-theme"] = "Adwaita"
            yield "gtk-theme: 'Adwaita'\n"
            assert path.read_text() == "light\n"
            stamp = path.stat().st_mtime_ns
            yield "gtk-theme: 'Adwaita'\n"
            yield "font-name: 'Sans 11'\n"
            assert path.stat().st_mtime_ns == stamp, "unchanged themes must not rewrite the cache"
            self.finished = True

        def wait(self):
            assert self.finished
            return 0

        def poll(self):
            return 0 if self.finished else None

    def popen(command, **kwargs):
        assert command == ["gsettings", "monitor", theme.SCHEMA]
        assert kwargs["text"] and kwargs["stdout"] == subprocess.PIPE
        return Monitor()

    monkeypatch.setattr(theme.subprocess, "Popen", popen)
    assert theme.watch_theme(path) == 1, "a stopped listener must be retried"


def test_missing_monitor_still_publishes_fallback(monkeypatch, tmp_path):
    def unavailable(*args, **kwargs):
        raise FileNotFoundError("gsettings")

    monkeypatch.setattr(theme.subprocess, "Popen", unavailable)
    monkeypatch.setattr(theme, "read_setting", lambda key: None)
    path = tmp_path / "desktop-theme"
    assert theme.watch_theme(path) == 1
    assert path.read_text() == "dark\n"
