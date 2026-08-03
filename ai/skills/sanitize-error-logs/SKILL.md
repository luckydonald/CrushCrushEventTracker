---
name: "sanitize-error-logs"
description: "Redact personal/production data from ai/errors/*.* files for committing them, while keeping every value needed to diagnose the bug. Use whenever a user attaches or asks to clean up/redact an existing one."
---

# Sanitizing `ai/errors/*.*` files

`ai/errors/<N>.txt` or `ai/errors/<N>.<VERSION>.txt` get committed to this repo as regression evidence. They must not leak real infrastructure or personal data, but must stay byte-for-byte useful for debugging — timestamps, field names, error strings, and the *shape* of the failure must survive untouched.

## What to redact, and with what

| Real value | Pattern to find it | Replace with |
|---|---|---|
| Public/production IPs (`peer_ip=`, `Connecting to ... [x.x.x.x]`) | `grep -nE '[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}'` | `<redacted-ip>` — do **not** swap in another real-looking IP (e.g. a TEST-NET address); a plausible fake IP still reads as "this could be someone's real address," so use the literal marker |
| Entity/connection/user UUIDs (`entity_id=`, `conn_id=`, `client_entity=`, `user=<uuid>@host`) | `grep -nE '[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}'` | `<redacted-uuid>` |
| SSH key fingerprints (`fp=SHA256:...`, host key `SHA256:...`) | `grep -n 'SHA256:'` | `SHA256:<redacted>` |
| Production domain (`<project>-<slug>.<tld>`, or whatever the deployed hostname is) | `grep -n '<project>-'` / check against the known deployment domain | a generic placeholder, e.g. `base.example.com` |
| Real entity/machine display names that map to actual user infrastructure (e.g. a real hostname like `macbook`, `Win_PC`, `Work Laptio`) | contextual — these are the `host="..."` / `entity_name="..."` values in the log, and the `-L`/`-R` targets in the client transcript | generic but descriptive placeholders: `client1`, `server1`, `linux-laptop`, etc. Pick names that preserve the client/server role so the log is still readable |
| Local filesystem paths containing a real username or app-specific identifiers (e.g. `/home/user/.var/app/<flatpak-id>/.ssh/...`) | `grep -n '/home/'` | shorten to a generic path, e.g. `~/.ssh/<project>_<placeholder-name>` |
| Control-socket / mux paths embedding a UUID (`/run/user/1000/rc-<hash>-<uuid>`) | `grep -n '/run/user/'` | `/run/user/1000/rc-<redacted>` |

## What to keep exactly as-is

- Timestamps, log levels, `tracing` target names, field names (`peer_ip=`, `host=`, `port=`).
- The literal error/rejection message text (e.g. `direct-tcpip: rejected — target hostname not found (not a UUID or known alias)`, `channel 5: open failed: administratively prohibited: Rejected`) — this is the actual evidence being preserved.
- Port numbers, protocol/algorithm names (`ssh-ed25519`, `chacha20-poly1305@openssh.com`), client/server software versions.

## Consistency rules

- **One real value → one placeholder, used everywhere it appears** — across the same-numbered `.txt` and/or `.md` variants, i.e. the files for the same incident, since they describe the same session and get cross-referenced.
- Distinct real values that don't need to stay distinguishable (e.g. a ssh log with random bot IPs hitting the SSH port with unrelated password-auth probes) can all collapse to the same `<redacted-ip>` — the log's diagnostic value doesn't depend on telling those apart.
- Don't invent new UUIDs/IPs that look real (see the IP row above) — prefer the literal `<redacted-*>` marker over a TEST-NET/RFC 5737 address or a fresh random UUID. The goal is "obviously a placeholder," not "a different real-looking value."

## Verify before committing

```bash
grep -nE '[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}' ai/errors/<N>.*   # any leftover IPs
grep -nE '[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}' ai/errors/<N>.*  # any leftover UUIDs
grep -n 'SHA256:' ai/errors/<N>.*      # fingerprints should all read SHA256:<redacted>
grep -n '/home/\|/run/user/' ai/errors/<N>.*  # leftover real local paths
```

If any of these commands return a hit that isn't already a placeholder, the file isn't done yet.

## Notes

- Not every existing `ai/errors/*` file follows this convention consistently. Don't take an existing file's sanitization level as the bar; apply the table above to whatever file is being added or cleaned right now. Don't rewrite older, already-committed error files on your own initiative just because they fall short — ask first, same as any other historical cleanup.
- If working in the base repo, `ai/°base/errors/*` is to be used analogly.
