# Minecraft overlay

- The Minecraft panel uses the Java server status protocol directly over TCP.
- If `PEBBLEHOST_API_KEY` is present, the fetcher also reads PebbleHost resource stats and player names.
- `pebblehost-api.yaml` is a vendored copy of PebbleHost's official [OpenAPI schema](https://api.pebblehost.com/api.yaml), retained as the development reference for those responses. Refresh it from that URL and review the diff when the provider changes its API.
- PebbleHost server lookup is automatic from `MINECRAFT_SERVER`; `MINECRAFT_SERVER_HOST` and `MINECRAFT_SERVER_PORT` are the split alternative form, and `PEBBLEHOST_SERVER_ID` can force a specific server identifier.
- When the server is empty, the panel shows how long it has been since a player was last **observed** online (for example `Last player 12m ago`), using only successful status queries.
- A large gap since the previous successful poll (laptop sleep, network down, fetch stopped) clears that idle timer so the panel does not claim the server was empty while it was not watching. Failed polls preserve the last known observation markers but do not extend “empty time.”
- `MINECRAFT_LAST_SEEN_MAX_GAP_SECONDS` (default `300`) is the maximum allowed gap between successful polls for continuous last-seen tracking.
- The panel is launched in the bottom-left corner by default.
- Set `MINECRAFT_OVERLAY_ENABLED=0` to disable the Minecraft overlay and its refresh loop.
- `MINECRAFT_REFRESH_SECONDS`, `MINECRAFT_GAP_X`, `MINECRAFT_GAP_Y`, `MINECRAFT_STATUS_TIMEOUT_SECONDS`, and `MINECRAFT_PROTOCOL_VERSION` can tune refresh cadence, placement, timeout, and protocol negotiation.
