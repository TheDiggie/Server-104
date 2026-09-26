# Operating guide: claude-testbench (read this before using the harness)

You are an AI agent working in the Blakod / Meridian 59 "104" server repo. This folder gives you
a way to **verify gameplay changes at runtime**, not just compile them. Use it whenever you edit
`.kod` and want to know the change actually *works*, or when investigating `error.txt` bugs.

> **For concrete "how do I do X" ops on the LIVE server — spawn a mob, kill a mob (with/without XP),
> put items on monsters/players — see [`RECIPES.md`](RECIPES.md).** The fast path is
> `kodbench.Bench(launch=False)` (attaches to the running server on 9998) with the helpers
> `find_player / where / spawn / place / spawn_near / give / kill / instances`, or one-shot
> `python claude-testbench/kodbench.py live "<command>"`.
>
> **If the `blakserv-dm` MCP server is loaded (see README + repo `.mcp.json`), PREFER its tools**
> (`spawn`, `kill`, `give`, `cast`, `whisper`, `say_to_room`, `look`, `whereis`, `raw`, …) over
> writing one-off Python — same actions, first-class. `mcp_blakserv.py` is Layer 1 of the DM companion.

## The core problem this solves

`nmake debug=1` in `kod/` only proves KOD parses. Blakod **logs runtime errors and keeps
running** (send-to-nil, `Nth` of nil, divide by nil, `@Message` with no handler), so broken
gameplay is invisible until you read `run/server/channel/error.txt`. Never claim a gameplay
change "works" from a clean compile alone. Use this harness to observe real behavior.

## The verify loop (do this after editing .kod)

```powershell
# 1. compile (from repo root)
cmd /c '"C:\Program Files (x86)\Microsoft Visual Studio 14.0\Common7\Tools\vsvars32.bat" >nul & cd kod & nmake debug=1'

# 2. push fresh bytecode into the sandbox (OneDrive empties loadkod; this repopulates it)
python claude-testbench\kodbench.py sync-loadkod

# 3. exercise the change and read the error delta
python claude-testbench\kodbench.py smoke          # built-in effigy example, OR:
python claude-testbench\kodbench.py cmd "create object <YourClass>"
```

First time only: `python claude-testbench\kodbench.py setup` creates the isolated sandbox.

## How the server is driven (facts, verified from blakserv/*.c)

- Control is the **maintenance port**: sandbox uses **9999** (live default is 9998).
- **MaintenanceMask** allows `127.0.0.1` by default — connect from localhost, no password.
- **MySQL is off by default** (`Enabled No`) so the server boots standalone / file-based.
- Commands are plain text terminated by **CR (`\r`), NOT LF (`\n`)** — this is the #1 gotcha
  (`maintenance.c:MaintenanceInputChar`). Sending `\n` silently buffers forever and nothing
  runs. `kodbench.cmd()` already sends `\r`; if you hand-roll a socket, use `\r`.
- The interpreter only services the maintenance session **after the game finishes loading**, so
  the **first non-empty reply == game-ready** (that's how `Bench` waits). `help` is disabled in
  maintenance mode and `status` is not a verb — don't use them as anything but a liveness probe.
- Verified verbs (all confirmed working against a live boot):
  - `reload system` -> "Garbage collecting and saving game... Unloading... Loading ... done." (loads fresh KOD)
  - `create object <Class> [#parm=val ...]` -> "**Created object <id>.**" (or "Cannot find class named ...")
  - `send object <id> <Message> [#parm=val ...]` -> "Message <Msg> completed ... :< return from OBJECT <id> ... : <retval>"
  - `send class <Class> <Message> [#parm=val ...]` -> sends to every instance of a class.
  - Blakod `Debug(...)` output and runtime errors land in `channel/error.txt` (also `debug.txt`, `god.txt`).

## Using it as a library (richer tests)

```python
import sys; sys.path.insert(0, "claude-testbench")
from kodbench import Bench

with Bench() as b:                       # boots sandbox, connects maintenance, auto-syncs loadkod
    b.reload()                           # load your just-compiled KOD
    oid = b.create("NecromancerEffigy")  # -> object id
    b.send(oid, "CastSpell")             # fire the behavior you changed
    new = b.errors_since_start()         # list[str] of error.txt lines added since boot
    crashed = [e for e in new if "C_Random" in e or "C_Nth" in e or "non-object" in e]
    assert not crashed, f"runtime errors: {crashed}"
```

`Bench` methods: `reload(what="system")`, `create(cls, parms="")`, `send(id, msg, parms="")`,
`send_class(cls, msg, parms="")`, `cmd(raw_line)`, `errors_since_start()`. It hard-kills the
server on exit (never saves).

## How to judge a result

- A fix **passes** if the runtime error(s) it targeted do **not** appear in
  `errors_since_start()` after you exercise the code path.
- Watch for the common Blakod runtime signatures: `C_Nth ... non-list`, `C_Random got low > high`,
  `... to non-object 0,0`, `InterpretBinary*_L can't ...`, `can't find a handler for MESSAGE ...`.
- "No new errors" over the exercised path is the bar. It does **not** prove balance/fun/rendering.

## Safety rules (do not violate)

- Operate on the **sandbox** (`run/testserver`) only. Never point the harness at `run/server`.
- Never issue `save game` / `SaveGame` through the harness — a test must not persist state.
- Teardown is a hard kill by design; that's intentional (protects savegames).

## Environment gotcha you WILL hit

`run/server/loadkod/` and the sandbox's `loadkod/` get **emptied by OneDrive**. Symptoms: the
server exits during boot, or reloads stale/no code. Fix: `python claude-testbench\kodbench.py
sync-loadkod` (also auto-runs on `Bench.start()`). This same emptiness means the **live**
`run/server` will fail to load on restart — if asked to fix the live server, repopulate its
`loadkod` from the kod tree (`kod/**/*.bof`) or, better, advise moving the server tree off
OneDrive to a local disk.

## What this canNOT do

- No rendering / client feel / input — it's headless logic only.
- No real multiplayer/network behavior beyond what you can script via `create`/`send`.
- No balance or "is it fun" judgement — that still needs a human playtest.
