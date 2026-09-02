from datetime import datetime, timedelta, timezone

import pytest

import fetch_minecraft_status as minecraft


def _iso(dt):
    return dt.astimezone(timezone.utc).isoformat()


def test_clean_description_flattens_nested_extra_and_strips_color_codes():
    description = {
        "text": "\u00a7aHello",
        "extra": [
            " ",
            {"text": "\u00a7bworld", "extra": [{"text": "\u00a7l!"}]},
        ],
    }

    assert minecraft.clean_description(description) == "Hello world!"


class FakeSocket:
    def __init__(self, payload):
        self.payload = bytearray(payload)

    def recv(self, length):
        chunk = self.payload[:length]
        del self.payload[:length]
        return bytes(chunk)


def test_read_status_payload_honors_packet_framing():
    raw_json = b'{"players":{"online":1}}'
    packet = minecraft.encode_varint(0) + minecraft.encode_varint(len(raw_json)) + raw_json
    sock = FakeSocket(minecraft.encode_varint(len(packet)) + packet)

    assert minecraft.read_status_payload(sock) == {"players": {"online": 1}}


def test_read_status_payload_rejects_oversized_packet_before_reading_body():
    sock = FakeSocket(minecraft.encode_varint(minecraft.MAX_STATUS_PACKET_BYTES + 1))

    with pytest.raises(ValueError, match="invalid status packet length"):
        minecraft.read_status_payload(sock)


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


def test_apply_last_player_seen_sets_timestamp_when_players_online(monkeypatch):
    monkeypatch.setenv("MINECRAFT_LAST_SEEN_MAX_GAP_SECONDS", "300")
    now = datetime(2026, 8, 11, 18, 0, 0, tzinfo=timezone.utc)
    status = {
        "ok": True,
        "updatedAt": _iso(now),
        "onlinePlayers": 2,
    }

    minecraft.apply_last_player_seen(status, {})

    assert status["lastPlayerSeenAtEpoch"] == int(now.timestamp())
    assert status["lastSuccessfulAtEpoch"] == int(now.timestamp())


def test_apply_last_player_seen_carries_across_continuous_empty_polls(monkeypatch):
    monkeypatch.setenv("MINECRAFT_LAST_SEEN_MAX_GAP_SECONDS", "300")
    seen_at = datetime(2026, 8, 11, 17, 50, 0, tzinfo=timezone.utc)
    previous_success = datetime(2026, 8, 11, 17, 59, 0, tzinfo=timezone.utc)
    now = datetime(2026, 8, 11, 18, 0, 0, tzinfo=timezone.utc)
    previous = {
        "ok": True,
        "updatedAt": _iso(previous_success),
        "lastSuccessfulAt": _iso(previous_success),
        "lastSuccessfulAtEpoch": int(previous_success.timestamp()),
        "lastPlayerSeenAt": _iso(seen_at),
        "lastPlayerSeenAtEpoch": int(seen_at.timestamp()),
        "onlinePlayers": 0,
    }
    status = {
        "ok": True,
        "updatedAt": _iso(now),
        "onlinePlayers": 0,
    }

    minecraft.apply_last_player_seen(status, previous)

    assert status["lastPlayerSeenAtEpoch"] == int(seen_at.timestamp())
    assert status["lastSuccessfulAtEpoch"] == int(now.timestamp())


def test_apply_last_player_seen_drops_after_observation_gap(monkeypatch):
    monkeypatch.setenv("MINECRAFT_LAST_SEEN_MAX_GAP_SECONDS", "300")
    seen_at = datetime(2026, 8, 11, 12, 0, 0, tzinfo=timezone.utc)
    previous_success = datetime(2026, 8, 11, 12, 1, 0, tzinfo=timezone.utc)
    # Machine was offline for hours — players may have joined during the gap.
    now = datetime(2026, 8, 11, 18, 0, 0, tzinfo=timezone.utc)
    previous = {
        "ok": True,
        "updatedAt": _iso(previous_success),
        "lastSuccessfulAt": _iso(previous_success),
        "lastSuccessfulAtEpoch": int(previous_success.timestamp()),
        "lastPlayerSeenAt": _iso(seen_at),
        "lastPlayerSeenAtEpoch": int(seen_at.timestamp()),
        "onlinePlayers": 0,
    }
    status = {
        "ok": True,
        "updatedAt": _iso(now),
        "onlinePlayers": 0,
    }

    minecraft.apply_last_player_seen(status, previous)

    assert "lastPlayerSeenAt" not in status
    assert "lastPlayerSeenAtEpoch" not in status
    assert status["lastSuccessfulAtEpoch"] == int(now.timestamp())


def test_apply_last_player_seen_drops_when_previous_success_unknown(monkeypatch):
    monkeypatch.setenv("MINECRAFT_LAST_SEEN_MAX_GAP_SECONDS", "300")
    now = datetime(2026, 8, 11, 18, 0, 0, tzinfo=timezone.utc)
    previous = {
        "ok": False,
        "updatedAt": _iso(now - timedelta(hours=1)),
        "error": "timed out",
        # Stale last-seen without a recent successful poll must not be trusted.
        "lastPlayerSeenAtEpoch": int((now - timedelta(hours=2)).timestamp()),
    }
    status = {
        "ok": True,
        "updatedAt": _iso(now),
        "onlinePlayers": 0,
    }

    minecraft.apply_last_player_seen(status, previous)

    assert "lastPlayerSeenAtEpoch" not in status


def test_preserve_observation_fields_on_error_payload():
    previous = {
        "lastPlayerSeenAt": "2026-08-11T17:00:00+00:00",
        "lastPlayerSeenAtEpoch": 1780000000,
        "lastSuccessfulAt": "2026-08-11T17:05:00+00:00",
        "lastSuccessfulAtEpoch": 1780000300,
    }
    data = {"ok": False, "error": "down"}

    minecraft.preserve_observation_fields(data, previous)

    assert data["lastPlayerSeenAtEpoch"] == 1780000000
    assert data["lastSuccessfulAtEpoch"] == 1780000300
