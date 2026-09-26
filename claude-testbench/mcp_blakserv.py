#!/usr/bin/env python3
"""
mcp_blakserv.py -- a zero-dependency MCP (Model Context Protocol) stdio server
that exposes the running Blakod / Meridian 59 server (its maintenance port) as a
clean set of "dungeon master" tools.

This is Layer 1 of the DM companion: the *hands*. Any MCP client (Claude Code,
Claude Desktop, a custom Agent SDK loop) can load this and drive the live world
with real tools instead of hand-writing maintenance commands.

- Transport: newline-delimited JSON-RPC 2.0 over stdin/stdout (the MCP stdio
  transport). No third-party packages required -- stdlib only.
- Actions go through the SAME proven path as kodbench (CR-terminated commands to
  the maintenance port on 9998), reusing kodbench.Bench(launch=False).
- It attaches to the ALREADY-RUNNING server; it never boots or kills it.

Register it by adding .mcp.json at the repo root (see claude-testbench/README.md),
then reload the MCP servers in your client.
"""
import sys, os, re, json, traceback

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from kodbench import Bench  # proven socket + CR protocol + helpers

PROTOCOL_VERSION = "2024-11-05"
SERVER_INFO = {"name": "blakserv-dm", "version": "0.1.0"}

# Friendly spell aliases -> the SID_ constant the server resolves in FindSpellByNum.
SPELL_SIDS = {
    "blind": "SID_BLIND", "hold": "SID_HOLD", "paralyze": "SID_HOLD",
    "fireball": "SID_FIREBALL", "fire": "SID_FIREBALL",
}

# ---------------------------------------------------------------------------
# lazy, self-healing connection to the live server
# ---------------------------------------------------------------------------
_bench = None

def bench():
    """Return a connected Bench, (re)connecting on demand. Raises on failure."""
    global _bench
    if _bench is None:
        b = Bench(launch=False)      # attach to running server on 9998
        b.start()                    # connect only; never boots/kills
        _bench = b
    return _bench

def _reset():
    global _bench
    try:
        if _bench:
            _bench.stop()
    except Exception:
        pass
    _bench = None

# ---------------------------------------------------------------------------
# small helpers on top of the raw maintenance protocol
# ---------------------------------------------------------------------------
# blakserv/admin.h: MAX_ADMIN_COMMAND is 120 and maintenance.c keeps chars only while
# len < 119, so a longer command line is SILENTLY TRUNCATED -- no error, no warning.
# Every command we build has to fit, so long narration must be split.
MAX_CMD = 119

def _chunks(text, budget):
    """Split text into pieces that fit `budget` chars, breaking on word boundaries."""
    words = str(text).replace("\r", " ").replace("\n", " ").split()
    if budget < 12:                       # pathological prefix; refuse to emit confetti
        return [" ".join(words)[:max(budget, 1)]]
    out, cur = [], ""
    for w in words:
        if len(w) > budget:               # single monster word: hard-split it
            if cur:
                out.append(cur); cur = ""
            while len(w) > budget:
                out.append(w[:budget]); w = w[budget:]
        if not cur:
            cur = w
        elif len(cur) + 1 + len(w) <= budget:
            cur += " " + w
        else:
            out.append(cur); cur = w
    if cur:
        out.append(cur)
    return out or [""]

def _make_resource(b, text):
    """Create a dynamic resource string for narration; return its numeric id."""
    clean = str(text).replace("\r", " ").replace("\n", " ")
    r = b.cmd("create resource %s" % clean)
    # blakserv replies with the id FIRST and never echoes the word "resource":
    #   "1003262 (dynamic) = The air stirs."
    # An id-second regex never matches, which silently broke whisper/say_to_room.
    m = re.search(r"^\s*(\d+)\s+\(dynamic\)", r, re.M)
    return m.group(1) if m else None

def _resolve_target(b, who):
    """Accept a player NAME or a numeric object id -> object id string (or None)."""
    who = str(who).strip()
    if who.isdigit():
        return who
    return b.find_player(who)

def _spell_object(b, spell):
    """Accept 'blind' / 'SID_BLIND' / 'Blind' (class) -> the live spell object id."""
    s = str(spell).strip()
    sid = SPELL_SIDS.get(s.lower())
    if sid is None and s.upper().startswith("SID_"):
        sid = s.upper()
    if sid:
        return b._ret_obj(b.cmd("send object 0 FindSpellByNum NUM int %s" % sid))
    # else treat as a class name and grab the singleton instance
    inst = b.instances(s)
    return inst[0] if inst else None

# ---------------------------------------------------------------------------
# tool implementations  --  each takes (b, args) and returns a readable string
# ---------------------------------------------------------------------------
def t_server_status(b, a):
    return "Connected to the live Blakod server maintenance port (9998). Ready."

def t_find_player(b, a):
    pid = b.find_player(a["name"])
    return "player '%s' -> object %s" % (a["name"], pid) if pid else "no player named '%s' online" % a["name"]

def t_whereis(b, a):
    tid = _resolve_target(b, a["target"])
    if not tid:
        return "could not resolve '%s'" % a["target"]
    room, row, col = b.where(tid)
    return "object %s is in room %s at (row %s, col %s)" % (tid, room, row, col)

def t_look(b, a):
    tid = _resolve_target(b, a["target"])
    if not tid:
        return "could not resolve '%s'" % a["target"]
    # if target is a mobile, look at its room; if it's already a room id, use it
    room = b._ret_obj(b.get(tid, "GetOwner")) or tid
    raw = b.cmd("show belong %s" % room)
    return "contents of room %s (objects owned by it):\n%s" % (room, raw.strip())

def t_list_players(b, a):
    return "logged-in users:\n" + b.cmd("who").strip()

def t_instances(b, a):
    ids = b.instances(a["cls"])
    return "%d instance(s) of %s: %s" % (len(ids), a["cls"], ", ".join(ids) if ids else "(none)")

def t_spawn(b, a):
    cls = a["monster"]
    count = int(a.get("count", 1))
    near = a.get("near")
    room = a.get("room")
    row = a.get("row")
    col = a.get("col")
    if near:
        pid = _resolve_target(b, near)
        if not pid:
            return "could not resolve player '%s' to spawn near" % near
        room, row, col = b.where(pid)
    if not room:
        return "specify 'near' (a player) or a 'room' id"
    spread = [(0, 0), (1, 1), (-1, 1), (1, -2), (-2, -1), (2, 2), (-2, 2), (2, -1)]
    out = []
    for i in range(count):
        mob = b.spawn(cls)
        if not mob:
            out.append("#%d create FAILED (bad class '%s'?)" % (i + 1, cls)); continue
        # BEFORE placing: rooms periodically sweep themselves via
        # Room.DestroyDisposable, and monster.kod deletes any monster that isn't an
        # NPC, has no master, and has no pbDontDispose.  A hand-spawned mob is
        # exactly that, so without this it vanishes minutes later -- the placement
        # looks fine, then the monster is silently gone.  This flag is what the
        # source calls the "admin-created beasties" case.
        b.cmd("send object %s SetDontDispose bValue int 1" % mob)
        dr, dc = spread[i % len(spread)]
        r = (int(row) + dr) if row not in (None, "") else 0
        c = (int(col) + dc) if col not in (None, "") else 0
        ok = b.place(mob, room, r, c)
        out.append("#%d -> obj %s @room %s (%s,%s) placed=%s" % (i + 1, mob, room, r, c, ok))
    return "spawned %s x%d:\n  %s" % (cls, count, "\n  ".join(out))

def t_kill(b, a):
    mob = str(a["mob"])
    credit = a.get("credit")  # a player -> XP; omitted -> room (no XP)
    if credit:
        killer = _resolve_target(b, credit)
        if not killer:
            return "could not resolve credit player '%s'" % credit
    else:
        killer = b._ret_obj(b.get(mob, "GetOwner"))  # the room = no XP
        if not killer:
            return "mob %s has no room owner (already dead?)" % mob
    b.kill(mob, killer)
    gone = b._ret_obj(b.get(mob, "GetOwner")) is None
    return "sent Killed to %s (killer=%s, xp=%s). dead=%s" % (mob, killer, bool(credit), gone)

def t_give(b, a):
    target = _resolve_target(b, a["target"])
    if not target:
        return "could not resolve target '%s'" % a["target"]
    item = b.give(target, a["item"], wear=bool(a.get("equip", False)))
    if not item:
        return "failed to create item '%s'" % a["item"]
    return "gave item %s (obj %s) to %s%s" % (a["item"], item, target, " and equipped it" if a.get("equip") else "")

def t_cast(b, a):
    caster = _resolve_target(b, a["caster"])
    target = _resolve_target(b, a["target"])
    if not caster:
        return "could not resolve caster '%s'" % a["caster"]
    if not target:
        return "could not resolve target '%s'" % a["target"]
    spellobj = _spell_object(b, a["spell"])
    if not spellobj:
        return "could not find spell '%s'" % a["spell"]
    power = int(a.get("power", 50))
    lst = re.search(r"Created list node (\d+)", b.cmd("create listnode object %s nil 0" % target))
    if not lst:
        return "failed to build target list"
    r = b.cmd("send object %s CastSpell who object %s lTargets list %s iSpellPower int %d"
              % (spellobj, caster, lst.group(1), power))
    ok = ": $ 0" in r or "completed" in r
    return "cast spell %s (obj %s) from %s at %s power=%d -> %s" % (
        a["spell"], spellobj, caster, target, power, "ok" if ok else ("FAILED:\n" + r))

def t_whisper(b, a):
    target = _resolve_target(b, a["player"])
    if not target:
        return "could not resolve player '%s'" % a["player"]
    # "create resource " is itself a command line, so it obeys MAX_CMD too.
    lines = _chunks(a["text"], MAX_CMD - len("create resource "))
    for line in lines:
        rid = _make_resource(b, line)
        if not rid:
            return "failed to create text resource for: %s" % line
        b.cmd("send object %s MsgSendUser message_rsc resource %s" % (target, rid))
    note = "" if len(lines) == 1 else " (in %d chunks)" % len(lines)
    return "whispered to %s%s: %s" % (target, note, a["text"])

def t_say_to_room(b, a):
    room = a.get("room")
    speaker = a.get("speaker")
    if not room:
        # default room = the speaker's room, or a player's room
        anchor = speaker or a.get("near")
        if anchor:
            aid = _resolve_target(b, anchor)
            room = b._ret_obj(b.get(aid, "GetOwner")) or aid
    if not room:
        return "specify 'room' (id) or 'near' (a player) or 'speaker'"
    if not speaker:
        speaker = room  # the room itself 'speaks' -> a disembodied booming voice
    else:
        speaker = _resolve_target(b, speaker)
    # SAY_NORMAL(=1) packs the text as "0,string" -- an inline TEMP STRING, not a
    # resource id (only SAY_RESOURCE uses "4,string").  Passing a resource here
    # dispatches fine and returns $, but the client renders NOTHING.  The tag for a
    # literal temp string is `quote`, and it must be the LAST param on the line.
    prefix = "send object %s SomeoneSaidRoom what object %s type int 1 string quote " % (room, speaker)
    sent, fails = [], []
    for chunk in _chunks(a["text"], MAX_CMD - len(prefix)):
        r = b.cmd(prefix + chunk)
        (sent if ("completed" in r or ": $ 0" in r) else fails).append(chunk)
    if fails:
        return "said to room %s (speaker %s) -> FAILED on: %s" % (room, speaker, " | ".join(fails))
    note = "" if len(sent) == 1 else " (in %d chunks)" % len(sent)
    return "said to room %s (speaker %s)%s: %s" % (room, speaker, note, a["text"])

def t_get_prop(b, a):
    return b.cmd("show object %s" % a["obj"]).strip() if a.get("prop") in (None, "", "*") \
        else b.cmd("send object %s Get%s" % (a["obj"], a["prop"])).strip()

def t_set_prop(b, a):
    return b.cmd("set object %s %s %s" % (a["obj"], a["prop"], a["value"])).strip()

def t_raw(b, a):
    return b.cmd(a["command"]).strip()

# ---------------------------------------------------------------------------
# tool registry (name -> (schema, fn))
# ---------------------------------------------------------------------------
def _tool(name, desc, props, required, fn):
    return {
        "name": name,
        "description": desc,
        "inputSchema": {"type": "object", "properties": props, "required": required},
    }, fn

_S = {"type": "string"}
_I = {"type": "integer"}
_B = {"type": "boolean"}

_REGISTRY = [
    _tool("server_status", "Check the connection to the live server.", {}, [], t_server_status),
    _tool("find_player", "Find an online player's object id by name.",
          {"name": _S}, ["name"], t_find_player),
    _tool("list_players", "List currently logged-in players.", {}, [], t_list_players),
    _tool("whereis", "Get the room and coordinates of a player (name) or object id.",
          {"target": _S}, ["target"], t_whereis),
    _tool("look", "List what's in a room (occupants/objects). Target = player name, object id, or room id.",
          {"target": _S}, ["target"], t_look),
    _tool("instances", "List live object ids of a class (e.g. GiantRat, Tyrant).",
          {"cls": _S}, ["cls"], t_instances),
    _tool("spawn", "Spawn monster(s) by class near a player or in a room. e.g. monster='Tyrant', near='diggie'.",
          {"monster": _S, "near": _S, "room": _S, "row": _I, "col": _I, "count": _I},
          ["monster"], t_spawn),
    _tool("kill", "Kill a mob the RIGHT way (send Killed). Omit 'credit' = room kills it (no player XP); "
                  "set credit=<player> to award XP.",
          {"mob": _S, "credit": _S}, ["mob"], t_kill),
    _tool("give", "Give an item (by class) to a monster or player; equip=true to wear it (players).",
          {"target": _S, "item": _S, "equip": _B}, ["target", "item"], t_give),
    _tool("cast", "Make a caster cast a spell at a target (real projectile). spell='blind'|'hold'|'fireball' "
                  "or an SID_ constant or a spell class name.",
          {"spell": _S, "caster": _S, "target": _S, "power": _I},
          ["spell", "caster", "target"], t_cast),
    _tool("whisper", "Send private text to one player (appears in their message window).",
          {"player": _S, "text": _S}, ["player", "text"], t_whisper),
    _tool("say_to_room", "Speak narration into a room. Give 'room' id or 'near' a player; optional 'speaker' "
                         "object id (default: the room itself, a disembodied voice).",
          {"text": _S, "room": _S, "near": _S, "speaker": _S}, ["text"], t_say_to_room),
    _tool("get_prop", "Read an object: whole dump (omit prop) or one Get<Prop> (e.g. prop='Health').",
          {"obj": _S, "prop": _S}, ["obj"], t_get_prop),
    _tool("set_prop", "Set a single property on an object directly.",
          {"obj": _S, "prop": _S, "value": _S}, ["obj", "prop", "value"], t_set_prop),
    _tool("raw", "Escape hatch: run a raw maintenance command and return the reply.",
          {"command": _S}, ["command"], t_raw),
]

TOOLS = [t[0] for t in _REGISTRY]
DISPATCH = {t[0]["name"]: t[1] for t in _REGISTRY}

# ---------------------------------------------------------------------------
# JSON-RPC 2.0 stdio loop
# ---------------------------------------------------------------------------
def _send(obj):
    sys.stdout.write(json.dumps(obj) + "\n")
    sys.stdout.flush()

def _result(mid, result):
    _send({"jsonrpc": "2.0", "id": mid, "result": result})

def _error(mid, code, message):
    _send({"jsonrpc": "2.0", "id": mid, "error": {"code": code, "message": message}})

def _call_tool(name, args):
    fn = DISPATCH.get(name)
    if not fn:
        return "unknown tool: %s" % name, True
    try:
        b = bench()
    except Exception as e:
        _reset()
        return ("Cannot reach the server on the maintenance port (9998). Is blakserv running?\n(%s)" % e), True
    try:
        return fn(b, args or {}), False
    except (ConnectionError, OSError) as e:
        _reset()  # drop the dead socket so the next call reconnects
        return "connection lost (%s) -- retry the action" % e, True
    except Exception as e:
        return "ERROR in %s: %s\n%s" % (name, e, traceback.format_exc()), True

def main():
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except Exception:
            continue
        mid = msg.get("id")
        method = msg.get("method")
        params = msg.get("params") or {}

        if method == "initialize":
            _result(mid, {"protocolVersion": PROTOCOL_VERSION,
                          "capabilities": {"tools": {}},
                          "serverInfo": SERVER_INFO})
        elif method in ("notifications/initialized", "initialized"):
            pass  # notification, no response
        elif method == "ping":
            _result(mid, {})
        elif method == "tools/list":
            _result(mid, {"tools": TOOLS})
        elif method == "tools/call":
            text, is_error = _call_tool(params.get("name"), params.get("arguments"))
            _result(mid, {"content": [{"type": "text", "text": text}], "isError": is_error})
        elif method in ("resources/list", "prompts/list"):
            _result(mid, {"resources": [], "prompts": []})
        else:
            if mid is not None:
                _error(mid, -32601, "method not found: %s" % method)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pass
    finally:
        _reset()
