# Expired credentials and stale cache

## Panel behavior for expired accounts

When any account's credentials expire or a live fetch fails, the rate limit panel should keep showing the **last cached usage fill and reset time** for each window. Do not blank the bar or replace the countdown with `refresh` while that window's cached reset is still in the future.

Only after a window's cached reset time has already passed should that bar fall back to the empty `refresh` prompt. If there is no cached sample at all, keep the account row visible with empty bars rather than removing it.

Claude is the exception: its 5h window is not meaningful once the OAuth grant is stale, so the renderer draws an empty 5h `refresh` bar while waiting for re-auth. Provider-specific notes below cover how each fetcher refreshes tokens and where the stale cache lives.

## Provider credential handling

Each provider fetcher handles expired or rejected credentials differently:

- **Codex** reads `~/.local/share/clusterfork-auth/codex/auth.json.*` (or the legacy `~/.codex/auth.json.*` when the shared store is absent). On HTTP `401` or `403`, it refreshes the OAuth access token with the auth file's `refresh_token`, writes the new tokens back to that file (mode `0600`), and retries the usage request once. It does not keep a separate stale-cache fallback for auth failures. For paid accounts whose API response is missing future reset windows, it can carry forward still-valid windows from the previous `codex-usage.json` write. It can also apply local session rate limits from Codex rollout logs when those windows uniquely match one account's API response.
- **Claude** reads `~/.claude/.credentials.json.*`. It refreshes expired access tokens with the credentials file's `refresh_token` and writes the new tokens back to that suffixed file (mode `0600`). It never writes `~/.claude/.credentials.json` and never refreshes a grant whose refresh token equals the one in that file, because Claude Code owns that file and a competing refresh would revoke the token Claude Code holds. While waiting for Claude Code to rotate an expired shared grant, the panel serves the last successful quota from `cache/claude-usage-cache-<label>.json`. Between live API calls, fresh cache entries are reused for `CLAUDE_USAGE_TTL` seconds. When stale data is shown, the renderer draws an empty 5h bar labeled `refresh` (see the Claude exception above).
- **Cursor** reads `~/.local/share/clusterfork-auth/cursor/auth.json.*` (or the legacy `~/.config/cursor/auth.json.*` when the shared store is absent). It does not refresh tokens itself; it uses the access token stored in the auth file. On HTTP errors or missing usage buckets, the account row is written with empty bars and no stale-cache fallback. Cursor must refresh `auth.json` on its own.
- **Gemini** reads Antigravity Keyring items discovered from `~/.gemini/antigravity-cli/rotate-auth`. The fetcher never edits Keyring credentials directly. For the selected profile only, HTTP `401` or `403` triggers `agy models`, a re-read of the CLI-refreshed Keyring item, and one retry. Inactive profiles are never refreshed because that would require switching the active account. On any remaining error, the panel serves the last successful quota from `cache/gemini-usage-cache-<label>.json` under the general expired-account panel rule above.
- **Grok** reads `~/.grok/auth.json.*`. It does not refresh tokens itself; Grok CLI refreshes `auth.json` in place while you are actively using Grok. On any fetch error, including HTTP `401` expired credentials, the panel serves the last successful monthly usage from `cache/grok-usage-cache-<label>.json`, falling back to the last good account entry in `grok-usage.json` if no per-account cache exists yet. Usage is unlikely to change while Grok is idle, so stale data is intentional and follows the general expired-account panel rule above.
- **OpenCode Go** fetches the authenticated web dashboard using the `opencode.ai` cookies from Firefox (`cookies.sqlite`), or an optional `OPENCODE_COOKIE` / `OPENCODE_AUTH_COOKIE` override. It does not read OpenCode's local auth files, call the OpenCode API, or refresh credentials. If the dashboard request fails, it serves the last successful response from `cache/opencode-web-cache.json` under the general expired-account panel rule above. If that cache is missing too, it still writes the OpenCode row with empty 5h/weekly/monthly bars instead of removing it. Log into opencode.ai in Firefox again when auth is gone.

Pioneer was removed from the rate limit panel and no longer has credential or cache handling.

## Claude rotation recovery

Claude rotation recovery is separate from ordinary expiry handling. Claude Code rotates the refresh token of the logged-in account, which invalidates a copied credentials file for the same account. The fetcher recovers in two ways, both gated on the live file's profile email matching the email recorded for that account in `cache/claude-usage-cache-<label>.json`:

- It detects a changed default-file token (fingerprint in `cache/claude-default-token.fingerprint`) and copies the rotated tokens into the matching suffixed file within one loop iteration.
- As a backstop, it re-adopts from `~/.claude/.credentials.json` when a refresh fails with `invalid_grant`.
- The account email is recorded automatically after the first successful fetch. A new `~/.claude/.credentials.json.<label>` copy therefore needs one successful fetch before rotation recovery works for it.
