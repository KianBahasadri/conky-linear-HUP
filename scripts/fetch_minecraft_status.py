#!/usr/bin/env python3
import json
import os
import socket
import struct
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ENV_PATH = ROOT / ".env"
CACHE_DIR = ROOT / "cache"
STATUS_PATH = CACHE_DIR / "minecraft-status.json"
LOG_PATH = CACHE_DIR / "conky-minecraft.log"
PEBBLEHOST_API_URL = "https://panel.pebblehost.com/api/client"


def load_env(path):
    if not path.exists():
        return

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue

        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def log_event(message):
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().astimezone().isoformat(timespec="seconds")
    with LOG_PATH.open("a", encoding="utf-8") as log_file:
        log_file.write(f"[{timestamp}] fetch_minecraft_status: {message}\n")


def atomic_write_json(path, data):
    tmp_path = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    tmp_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    os.replace(tmp_path, path)


def encode_varint(value):
    value &= 0xFFFFFFFF
    out = bytearray()

    while True:
        byte = value & 0x7F
        value >>= 7
        if value:
            out.append(byte | 0x80)
        else:
            out.append(byte)
            break

    return bytes(out)


def read_exact(sock, length):
    chunks = []
    remaining = length

    while remaining > 0:
        chunk = sock.recv(remaining)
        if not chunk:
            raise ConnectionError("server closed connection")
        chunks.append(chunk)
        remaining -= len(chunk)

    return b"".join(chunks)


def read_varint(sock):
    value = 0

    for offset in range(5):
        byte = read_exact(sock, 1)[0]
        value |= (byte & 0x7F) << (7 * offset)
        if not byte & 0x80:
            return value

    raise ValueError("invalid VarInt from server")


def read_string(sock):
    length = read_varint(sock)
    return read_exact(sock, length).decode("utf-8")


def pack_string(value):
    raw = value.encode("utf-8")
    return encode_varint(len(raw)) + raw


def send_packet(sock, payload):
    sock.sendall(encode_varint(len(payload)) + payload)


def parse_server():
    server = os.environ.get("MINECRAFT_SERVER", "").strip()
    host = os.environ.get("MINECRAFT_SERVER_HOST", "").strip()
    port_text = os.environ.get("MINECRAFT_SERVER_PORT", "25565").strip()

    if server:
        if server.startswith("[") and "]:" in server:
            host, port_text = server[1:].split("]:", 1)
        elif ":" in server and server.rsplit(":", 1)[1].isdigit():
            host, port_text = server.rsplit(":", 1)
        else:
            host = server

    if not host:
        raise ValueError("Set MINECRAFT_SERVER in .env")

    try:
        port = int(port_text)
    except ValueError as error:
        raise ValueError("MINECRAFT_SERVER_PORT must be a number") from error

    if port < 1 or port > 65535:
        raise ValueError("MINECRAFT_SERVER_PORT must be 1-65535")

    return host, port


def flatten_description(value):
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return "".join(flatten_description(item) for item in value)
    if isinstance(value, dict):
        text = value.get("text", "")
        extra = value.get("extra", [])
        return str(text) + flatten_description(extra)
    return ""


def clean_description(value):
    # Strip Minecraft section-sign color/control codes.
    cleaned = []
    skip = False
    for char in flatten_description(value):
        if skip:
            skip = False
            continue
        if char == "\u00a7":
            skip = True
            continue
        cleaned.append(char)
    return " ".join("".join(cleaned).split())


def query_status(host, port, timeout, protocol_version):
    started = time.monotonic()

    with socket.create_connection((host, port), timeout=timeout) as sock:
        sock.settimeout(timeout)
        handshake = (
            encode_varint(0)
            + encode_varint(protocol_version)
            + pack_string(host)
            + struct.pack(">H", port)
            + encode_varint(1)
        )
        send_packet(sock, handshake)
        send_packet(sock, encode_varint(0))

        _packet_length = read_varint(sock)
        packet_id = read_varint(sock)
        if packet_id != 0:
            raise ValueError(f"unexpected response packet id {packet_id}")

        payload = json.loads(read_string(sock))

    latency_ms = int((time.monotonic() - started) * 1000)
    players = payload.get("players") or {}
    version = payload.get("version") or {}
    sample_players = [
        str(player.get("name"))
        for player in players.get("sample") or []
        if isinstance(player, dict) and player.get("name")
    ]

    return {
        "ok": True,
        "updatedAt": datetime.now(timezone.utc).isoformat(),
        "label": os.environ.get("MINECRAFT_SERVER_LABEL", "").strip() or "Minecraft",
        "address": f"{host}:{port}",
        "onlinePlayers": int(players.get("online") or 0),
        "maxPlayers": int(players.get("max") or 0),
        "latencyMs": latency_ms,
        "version": str(version.get("name") or "Unknown"),
        "description": clean_description(payload.get("description") or ""),
        "playerNames": sample_players,
        "serverInfoOk": False,
    }


def pebblehost_request(api_key, path, query=None, timeout=10):
    url = PEBBLEHOST_API_URL + path
    if query:
        url += "?" + urllib.parse.urlencode(query)

    authorization = api_key if api_key.lower().startswith("bearer ") else f"Bearer {api_key}"
    request = urllib.request.Request(
        url,
        headers={
            "Authorization": authorization,
            "Accept": "application/vnd.pterodactyl.v1+json, application/json",
            "Content-Type": "application/json",
            "User-Agent": "conky-linear-HUP/1.0",
        },
        method="GET",
    )

    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def server_matches_address(server, host, port):
    attributes = server.get("attributes") or {}
    relationships = attributes.get("relationships") or {}
    allocations = (relationships.get("allocations") or {}).get("data") or []

    for allocation in allocations:
        allocation_attributes = allocation.get("attributes") or {}
        allocation_port = allocation_attributes.get("port")
        allocation_hosts = {
            str(allocation_attributes.get("ip") or ""),
            str(allocation_attributes.get("ip_alias") or ""),
        }
        if allocation_port == port and host in allocation_hosts:
            return True

    return False


def find_pebblehost_server(api_key, host, port, timeout):
    explicit_server = os.environ.get("PEBBLEHOST_SERVER_ID", "").strip()
    if explicit_server:
        response = pebblehost_request(api_key, f"/servers/{explicit_server}", timeout=timeout)
        return response.get("attributes") or {}

    response = pebblehost_request(api_key, "", {"per_page": 50}, timeout=timeout)
    for server in response.get("data") or []:
        if server_matches_address(server, host, port):
            return server.get("attributes") or {}

    raise ValueError("no PebbleHost server allocation matched MINECRAFT_SERVER")


def collect_player_names(players_response):
    players = players_response.get("players") or {}
    names = []

    for player in players.get("list") or []:
        name = player.get("name")
        if name:
            names.append(str(name))

    return names


def query_pebblehost(host, port):
    api_key = os.environ.get("PEBBLEHOST_API_KEY", "").strip()
    if not api_key:
        return {
            "serverInfoOk": False,
            "serverInfoError": "Missing PEBBLEHOST_API_KEY",
        }

    timeout = float(os.environ.get("PEBBLEHOST_API_TIMEOUT_SECONDS", "10"))
    server = find_pebblehost_server(api_key, host, port, timeout)
    identifier = str(server.get("identifier") or server.get("uuid") or "")
    if not identifier:
        raise ValueError("matched PebbleHost server did not include an identifier")

    limits = server.get("limits") or {}
    resources_response = pebblehost_request(api_key, f"/servers/{identifier}/resources", timeout=timeout)
    players_response = pebblehost_request(api_key, f"/servers/{identifier}/minecraft/players", timeout=timeout)
    stats = resources_response.get("attributes") or {}
    resources = stats.get("resources") or {}
    memory_limit_mb = int(limits.get("memory") or 0)
    memory_mb = round((int(resources.get("memory_bytes") or 0) / 1024 / 1024), 1)

    return {
        "serverInfoOk": True,
        "serverIdentifier": identifier,
        "serverName": str(server.get("name") or ""),
        "serverState": str(stats.get("state") or ""),
        "cpuPercent": round(float(resources.get("cpu_absolute") or 0), 1),
        "memoryMb": memory_mb,
        "memoryLimitMb": memory_limit_mb,
        "uptimeSeconds": int(resources.get("uptime") or 0),
        "playerNames": collect_player_names(players_response),
    }


def write_error(message):
    data = {
        "ok": False,
        "updatedAt": datetime.now(timezone.utc).isoformat(),
        "label": os.environ.get("MINECRAFT_SERVER_LABEL", "").strip() or "Minecraft",
        "address": os.environ.get("MINECRAFT_SERVER", "").strip(),
        "error": message,
    }
    atomic_write_json(STATUS_PATH, data)
    log_event(f"error: {message}")


def main():
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    load_env(ENV_PATH)

    try:
        host, port = parse_server()
        timeout = float(os.environ.get("MINECRAFT_STATUS_TIMEOUT_SECONDS", "5"))
        protocol_version = int(os.environ.get("MINECRAFT_PROTOCOL_VERSION", "-1"))
        log_event(f"querying {host}:{port}")
        status = query_status(host, port, timeout, protocol_version)
    except Exception as error:
        write_error(f"Minecraft status failed: {error}")
        return 1

    try:
        pebblehost_status = query_pebblehost(host, port)
        status.update(pebblehost_status)
    except Exception as error:
        status.update(
            {
                "serverInfoOk": False,
                "serverInfoError": str(error),
            }
        )
        log_event(f"PebbleHost fetch failed: {error}")

    atomic_write_json(STATUS_PATH, status)
    log_event(
        f"completed fetch address={status['address']} "
        f"players={status['onlinePlayers']}/{status['maxPlayers']} latency_ms={status['latencyMs']} "
        f"server_info_ok={status.get('serverInfoOk')}"
    )
    print(json.dumps(status, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
