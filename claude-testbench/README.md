# claude-testbench

Tooling for the **Claude Code VS Code extension** (and any other Claude/agent working in this
repo) to **test gameplay changes at runtime**, not just compile them.

## What this is for

The Blakod (Meridian 59 "104") server compiles KOD with `nmake debug=1`. That only proves a
change *parses* — it says nothing about whether the gameplay logic actually runs. Historically
that gap is exactly how this codebase accumulated **64,000+ silent runtime errors** in
`run/server/channel/error.txt` (Blakod logs runtime errors and keeps going, so nothing crashes
and nobody notices).

This folder lets an agent close that gap. It drives the running `blakserv` through its
**maintenance port** — a plain-text admin socket — to:

- reload changed KOD,
- spawn objects (`create object <Class>`),
- fire messages at them (`send object <id> <Message>`),
- and read back any new runtime errors.

So a change like "guard the effigy's empty spell list" can be **verified for real**: spawn a
`NecromancerEffigy`, fire `CastSpell`, and confirm zero `C_Random`/`C_Nth` errors appear.

## Files

| File | Purpose |
|---|---|
| `kodbench.py` | The harness. Launches an isolated server sandbox, connects to the maintenance socket, runs admin commands, inspects `error.txt`. CLI + importable `Bench` class. |
| `mcp_blakserv.py` | **The DM interface (MCP server).** Exposes the live server as clean tools (spawn/kill/give/cast/whisper/say/look…) any MCP client can call. See below. |
| `RECIPES.md` | Verified cookbook: spawn/kill/place-items, forced spell casts, list params, gotchas. |
| `CLAUDE.md` | **Operating guide for agents.** Any Claude working here should read this first — protocol facts, exact verbs, verify workflow, safety/env gotchas. |
| `README.md` | This file (humans). |

## The DM interface (MCP server) — Layer 1 of the AI dungeon master

`mcp_blakserv.py` is a **zero-dependency** [MCP](https://modelcontextprotocol.io) stdio server (stdlib
only — no `pip install`). It attaches to the **already-running** server on the maintenance port (9998)
and exposes real tools so Claude can drive the world directly instead of hand-writing commands:

`server_status`, `find_player`, `list_players`, `whereis`, `look`, `instances`, `spawn`, `kill`,
`give`, `cast`, `whisper` (private text to a player), `say_to_room` (narration), `get_prop`,
`set_prop`, `raw` (escape hatch).

**Enable it:**
1. The repo root has `.mcp.json` registering the server (`command: python`, `args: claude-testbench/mcp_blakserv.py`).
2. In your MCP client (Claude Code), **reload MCP servers / restart the session** and **approve** `blakserv-dm` when prompted.
3. Boot the game server (so port 9998 is live). The tools attach on first use; they never boot or kill it.

**Verify without a client** (handshake + tool list; tool calls report "server down" gracefully if it's off):
```powershell
python claude-testbench\mcp_blakserv.py   # then paste JSON-RPC lines, or pipe them in
```

**Design intent:** this is the *hands*. On top of it comes Layer 2 (an event feed so the DM can
*react*) and Layer 3 (an autonomous DM daemon via the Agent SDK). Build them against this interface.

### Safety
- It talks to the **running** server you point it at (9998 by default = your local test server). It never
  boots, saves, or kills the server.
- `cast`/`kill`/`spawn` change live game state. `kill` defaults to **room-as-killer (no player XP)**; pass
  `credit=<player>` only when you want to award XP.
- Re-resolve ids each session — a server save renumbers objects (see RECIPES.md).

## Quick start

```powershell
# from the repo root, after `nmake debug=1` in kod\
python claude-testbench\kodbench.py setup          # make the isolated sandbox (once)
python claude-testbench\kodbench.py sync-loadkod   # copy compiled .bof into the sandbox
python claude-testbench\kodbench.py smoke          # spawn effigy + fire CastSpell + assert no crash
```

## Safety

- It runs against an **isolated sandbox** (`run/testserver`) with its own savegame, logs, and
  ports (game `5960`, maintenance `9999`) — it can **never** touch the real `run/server` save.
- Teardown **hard-kills** the process, so no savegame is ever written by a test.

## Known environment gotcha (read this)

This repo lives under **OneDrive**, which intermittently empties `run/server/loadkod/` — the
flat directory the server loads compiled `.bof` from. When that happens the server can't load
game code (and *your live server won't restart either*). `kodbench.py sync-loadkod` repopulates
it from the kod source tree, and the harness auto-syncs on start. For a durable fix, run the
server tree from a **local (non-OneDrive) disk**.
