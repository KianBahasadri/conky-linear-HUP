import pytest

import fetch_minecraft_status as minecraft


def test_clean_description_flattens_nested_extra_and_strips_color_codes():
    description = {
        "text": "\u00a7aHello",
        "extra": [
            " ",
            {"text": "\u00a7bworld", "extra": [{"text": "\u00a7l!"}]},
        ],
    }

    assert minecraft.clean_description(description) == "Hello world!"


def test_parse_server_host_port(monkeypatch):
    monkeypatch.setenv("MINECRAFT_SERVER", "example.org:25566")
    monkeypatch.delenv("MINECRAFT_SERVER_HOST", raising=False)
    monkeypatch.delenv("MINECRAFT_SERVER_PORT", raising=False)

    assert minecraft.parse_server() == ("example.org", 25566)


def test_parse_server_split_form(monkeypatch):
    monkeypatch.delenv("MINECRAFT_SERVER", raising=False)
    monkeypatch.setenv("MINECRAFT_SERVER_HOST", "split.example.org")
    monkeypatch.setenv("MINECRAFT_SERVER_PORT", "25567")

    assert minecraft.parse_server() == ("split.example.org", 25567)


def test_parse_server_rejects_bad_port(monkeypatch):
    monkeypatch.delenv("MINECRAFT_SERVER", raising=False)
    monkeypatch.setenv("MINECRAFT_SERVER_HOST", "split.example.org")
    monkeypatch.setenv("MINECRAFT_SERVER_PORT", "bad")

    with pytest.raises(ValueError, match="MINECRAFT_SERVER_PORT must be a number"):
        minecraft.parse_server()
