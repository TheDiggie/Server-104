#!/usr/bin/env python3
"""
kodbench - headless gameplay test harness for the Blakod (Meridian 59 "104") server.

WHY THIS EXISTS
    Compiling KOD (`nmake debug=1`) only proves a change parses. It does NOT prove
    the gameplay logic runs. This harness drives `blakserv` through its MAINTENANCE
    PORT (a plain-text admin socket) so you can, headlessly and without the graphical
    client: reload KOD, spawn objects, fire messages, and read back runtime errors --
    i.e. actually verify a gameplay change instead of guessing.

HOW blakserv EXPOSES CONTROL (verified from blakserv/*.c)
    * MaintenancePort default 9998 (blakserv.cfg [Socket] MaintenancePort).
    * MaintenanceMask default "::ffff:127.0.0.1" -> localhost is allowed out of the box.
    * MySQL is OFF by default (Enabled No) -> the server boots standalone, file-based.
    * Admin verbs (blakserv/adminfn.c) used here:
        reload <sub>                         - re-read changed KOD from loadkod/
        create object <Class> [#p=v ...]     - spawn an object; prints its object id
        send object <id> <Msg> [#p=v ...]    - send a message to an object; prints return
        send class <Class> <Msg> [#p=v ...]  - send to every object of a class

KNOWN ENV GOTCHA (important)
    The flat `loadkod/` dir the server loads compiled .bof from can be emptied by
    OneDrive sync (this repo lives under OneDrive). `sync-loadkod` repopulates it from
    the kod source tree so the server can actually load. If you hit repeated flakiness,
    run the server tree from a LOCAL (non-OneDrive) disk.

SAFETY
    By default this operates on an isolated SANDBOX (run/testserver) with its own
    savegame, logs, and ports, so it can never corrupt the real run/server savegame.
    Teardown hard-kills the process (never triggers a save).

USAGE
    python kodbench.py setup                       # (re)create the sandbox from run/server
    python kodbench.py sync-loadkod                # copy kod/**/*.bof -> sandbox loadkod/ (flat)
    python kodbench.py cmd "create object Claude"  # one-shot: boot, run one admin command, print, teardown
    python kodbench.py smoke                        # spawn NecromancerEffigy, fire CastSpell, assert no new errors
    python kodbench.py test <file.txt>             # run newline-separated admin commands, report error delta

    As a library:
        from kodbench import Bench
        with Bench() as b:
            b.reload()
            oid = b.create("NecromancerEffigy")
            b.send(oid, "CastSpell")
            new = b.errors_since_start()
            assert not any("C_Random" in e or "C_Nth" in e for e in new)
"""
import argparse
import glob
import os
import pathlib
import re
import shutil
import socket
import subprocess
import sys
import time

REPO       = pathlib.Path(__file__).resolve().parents[1]      # folder is at <repo>/claude-testbench
KOD_DIR    = REPO / "kod"
LIVE_DIR   = REPO / "run" / "server"
SANDBOX    = REPO / "run" / "testserver"
MAINT_HOST = "127.0.0.1"
SANDBOX_MAINT_PORT = 9999                                       # != live default 9998
SANDBOX_GAME_PORT  = 5960                                       # != live default 5959


# ----------------------------------------------------------------------------- setup
def setup_sandbox(force=False):
    """Clone run/server -> run/testserver (minus debug junk), give it its own ports."""
    if SANDBOX.exists() and force:
        shutil.rmtree(SANDBOX, ignore_errors=True)
    if not SANDBOX.exists():
        print(f"cloning {LIVE_DIR} -> {SANDBOX} ...")
        shutil.copytree(
            LIVE_DIR, SANDBOX,
            ignore=shutil.ignore_patterns("*.pdb", "*.map"),
        )
    _patch_cfg(SANDBOX / "blakserv.cfg")
    print(f"sandbox ready: {SANDBOX}")


def _patch_cfg(cfg: pathlib.Path):
    """Ensure the sandbox uses non-conflicting ports and localhost maintenance."""
    lines = cfg.read_text(errors="ignore").splitlines() if cfg.exists() else []
    have = {ln.split()[0] for ln in lines if ln.strip() and not ln.startswith("#")}
    inject = []
    if "Port" not in have:
        inject.append(f"Port                 {SANDBOX_GAME_PORT}")
    if "MaintenancePort" not in have:
        inject.append(f"MaintenancePort      {SANDBOX_MAINT_PORT}")
    if "MaintenanceMask" not in have:
        inject.append("MaintenanceMask      ::ffff:127.0.0.1")
    if not inject:
        return
    out = []
    for ln in lines:
        out.append(ln)
        if ln.strip() == "[Socket]":
            out.extend(inject)
    cfg.write_text("\n".join(out) + "\n")


# --------------------------------------------------------------------- loadkod repair
def sync_loadkod(target: pathlib.Path = None):
    """Copy every compiled kod/**/*.bof into <server>/loadkod/ (flat).

    Works around OneDrive emptying loadkod. Names are unique per class, so a flat
    copy is what the server expects. Also copies matching .rsc if present.
    """
    target = target or SANDBOX
    dest = target / "loadkod"
    dest.mkdir(exist_ok=True)
    n = 0
    for bof in KOD_DIR.rglob("*.bof"):
        shutil.copy2(bof, dest / bof.name)
        n += 1
    print(f"synced {n} .bof -> {dest}")
    if n == 0:
        print("  WARNING: no .bof found in the kod tree -- run `nmake debug=1` in kod/ first.")
    return n


# ------------------------------------------------------------------------- the harness
class Bench:
    def __init__(self, server_dir=None, maint_port=None, boot_secs=45, launch=True):
        # launch=True  -> boot the isolated sandbox (own save/ports; killed on exit).
        # launch=False -> ATTACH to the already-running LIVE server (default port 9998);
        #                 never boots or kills it, just drives it.
        self.launch = launch
        self.server_dir = pathlib.Path(server_dir or (SANDBOX if launch else LIVE_DIR))
        self.maint_port = maint_port or (SANDBOX_MAINT_PORT if launch else 9998)
        self.boot_secs = boot_secs
        self.proc = None
        self.sock = None
        self.error_log = self.server_dir / "channel" / "error.txt"
        self._error_start_lines = 0

    # -- lifecycle -----------------------------------------------------------
    def __enter__(self):
        try:
            self.start()
        except BaseException:
            self.stop()           # don't leak the process if boot/ready fails
            raise
        return self

    def __exit__(self, *exc):
        self.stop()

    def start(self):
        self._error_start_lines = self._count_errors()
        if not self.launch:
            # attach to a server that's already running (LIVE) -- no boot, no kill
            self.sock = socket.create_connection((MAINT_HOST, self.maint_port), timeout=5)
            self.sock.settimeout(3)
            time.sleep(0.3); self._drain()
            print(f"attached to LIVE maintenance :{self.maint_port}")
            return self
        if not (self.server_dir / "loadkod").exists() or not any((self.server_dir / "loadkod").glob("*.bof")):
            print("loadkod empty -> syncing from kod tree")
            sync_loadkod(self.server_dir)
        exe = self.server_dir / "blakserv.exe"
        print(f"launching {exe}")
        # CREATE_NO_WINDOW keeps it headless; cwd must be the server dir for relative paths
        self.proc = subprocess.Popen(
            [str(exe)], cwd=str(self.server_dir),
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        self._wait_for_maint()
        self._wait_for_ready()
        return self

    def _wait_for_ready(self, ready_secs=90):
        """The maintenance port opens EARLY -- LoadKodbase()/LoadAll() (the 10-30s game
        load) run after, and the command interpreter only services the maintenance
        session once the main loop is free (i.e. after the load). So poll a harmless
        command (`help`) and treat the FIRST non-empty reply as game-ready."""
        deadline = time.time() + ready_secs
        while time.time() < deadline:
            if self.proc.poll() is not None:
                raise RuntimeError("blakserv exited during game load -- check channel/error.txt")
            try:
                self.sock.sendall(b"help\r")       # CR-terminated (see cmd()); harmless probe
            except OSError:
                pass
            time.sleep(0.6)
            if self._drain().strip():              # any reply => interpreter live => load done
                print("server game-ready (maintenance interpreter responding)")
                time.sleep(1.0)
                return
            time.sleep(2)
        raise TimeoutError(f"server not game-ready within {ready_secs}s -- no reply on maintenance port")

    def _wait_for_maint(self):
        deadline = time.time() + self.boot_secs
        while time.time() < deadline:
            if self.proc.poll() is not None:
                raise RuntimeError("blakserv exited during boot -- check channel/error.txt")
            try:
                s = socket.create_connection((MAINT_HOST, self.maint_port), timeout=2)
                s.settimeout(3)
                self.sock = s
                time.sleep(0.5)
                self._drain()                       # swallow any banner/prompt
                print(f"connected to maintenance :{self.maint_port}")
                return
            except OSError:
                time.sleep(1)
        raise TimeoutError(f"maintenance port {self.maint_port} never opened within {self.boot_secs}s")

    def stop(self):
        try:
            if self.sock:
                self.sock.close()
        finally:
            self.sock = None
        if self.proc and self.proc.poll() is None:
            # hard kill: never triggers a savegame write
            subprocess.run(["taskkill", "/F", "/T", "/PID", str(self.proc.pid)],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.proc = None

    # -- maintenance socket --------------------------------------------------
    def _drain(self):
        buf = b""
        self.sock.settimeout(1.0)
        try:
            while True:
                chunk = self.sock.recv(4096)
                if not chunk:
                    break
                buf += chunk
        except socket.timeout:
            pass
        return buf.decode("latin-1", "replace")

    def cmd(self, text: str) -> str:
        """Send one admin command line, return whatever the server prints back."""
        if not self.sock:
            raise RuntimeError("not connected")
        # the maintenance protocol terminates a command on CR (\r), NOT LF -- see
        # blakserv/maintenance.c:MaintenanceInputChar. Sending \n never executes anything.
        self.sock.sendall(text.rstrip("\r\n").encode("latin-1") + b"\r")
        time.sleep(0.4)
        resp = self._drain().strip()
        print(f"> {text}\n{resp}")
        return resp

    # -- convenience verbs ---------------------------------------------------
    def reload(self, what="system"):
        return self.cmd(f"reload {what}")

    def create(self, klass: str, parms: str = "") -> str:
        """create object <Class> [#p=v ...] -> return the printed object id (best-effort)."""
        resp = self.cmd(f"create object {klass} {parms}".strip())
        digits = "".join(ch if ch.isdigit() else " " for ch in resp).split()
        return digits[-1] if digits else ""

    def send(self, objid, message: str, parms: str = ""):
        return self.cmd(f"send object {objid} {message} {parms}".strip())

    def send_class(self, klass: str, message: str, parms: str = ""):
        return self.cmd(f"send class {klass} {message} {parms}".strip())

    # -- error-log inspection ------------------------------------------------
    def _count_errors(self):
        if not self.error_log.exists():
            return 0
        with open(self.error_log, "r", errors="ignore") as f:
            return sum(1 for _ in f)

    def errors_since_start(self):
        """Lines appended to channel/error.txt since this Bench started."""
        if not self.error_log.exists():
            return []
        with open(self.error_log, "r", errors="ignore") as f:
            lines = f.readlines()
        return [ln.rstrip("\n") for ln in lines[self._error_start_lines:]]

    # -- high-level gameplay helpers (see RECIPES.md) ------------------------
    def _ret_obj(self, resp):
        m = re.search(r"^:\s*OBJECT (\d+)", resp, re.M)   # the RETURN VALUE line only
        return m.group(1) if m else None

    def _ret_int(self, resp):
        """Returns a real int (or None) -- NOT a string.  It used to return the
        match text, which made every `if not _ret_int(...)` check silently wrong:
        bool("0") is True in Python, so an INT 0 reply read as truthy."""
        m = re.search(r"^:\s*INT (-?\d+)", resp, re.M)
        return int(m.group(1)) if m else None

    def get(self, objid, message, params=""):
        """send object <id> <Message> [params] -> raw reply."""
        return self.cmd(("send object %s %s %s" % (objid, message, params)).strip())

    def find_player(self, name):
        """`show name <user>` -> object id (str) or None."""
        m = re.search(r"object (\d+)", self.cmd("show name %s" % name), re.I)
        return m.group(1) if m else None

    def where(self, objid):
        """(room_id, row, col) for a player/mob, all str or None."""
        return (self._ret_obj(self.get(objid, "GetOwner")),
                self._ret_int(self.get(objid, "GetRow")),
                self._ret_int(self.get(objid, "GetCol")))

    def spawn(self, cls, params=""):
        """create object <Class> [params] -> new object id (UNPLACED)."""
        m = re.search(r"Created object (\d+)", self.cmd(("create object %s %s" % (cls, params)).strip()))
        return m.group(1) if m else None

    def place(self, obj, room, row, col):
        """Drop <obj> into <room> at (row,col) via SYS UtilGoNearSquare -> True on success."""
        r = self.cmd("send object 0 UtilGoNearSquare what object %s where object %s new_row int %s new_col int %s"
                     % (obj, room, row, col))
        return self._ret_int(r) == 1

    def spawn_near(self, player_id, cls):
        """Spawn <cls> and place it on <player_id>'s square -> mob id."""
        room, row, col = self.where(player_id)
        mob = self.spawn(cls)
        if mob and room and row and col:
            self.place(mob, room, row, col)
        return mob

    def give(self, target, item_cls, wear=False):
        """Create <item_cls> and NewHold it into <target> (monster or player).
        wear=True also UserUseItem's it (equip; players only) -> item id."""
        item = self.spawn(item_cls)
        if item:
            self.cmd("send object %s NewHold what object %s" % (target, item))
            if wear:
                self.cmd("send object %s UserUseItem what object %s" % (target, item))
        return item

    def kill(self, mob, by):
        """send <mob> Killed with <by> as the killer (a player id credits XP; a room
        id -> no XP). ALWAYS use this, never a raw damage kill (that orphans loot)."""
        return self.cmd("send object %s Killed what object %s" % (mob, by))

    def instances(self, cls):
        """`show instances <Class>` -> list of object id strings."""
        r = self.cmd("show instances %s" % cls)
        vals = "\n".join(l for l in r.splitlines() if l.startswith(": "))
        return re.findall(r"OBJECT (\d+)", vals)


# ------------------------------------------------------------------------------- CLI
def _smoke():
    with Bench() as b:
        b.reload()
        oid = b.create("NecromancerEffigy")
        if oid:
            b.send(oid, "CastSpell")
        time.sleep(1)
        new = b.errors_since_start()
        bad = [e for e in new if "C_Random" in e or "C_Nth" in e or "non-list" in e]
        print("\n--- RESULT ---")
        print(f"new error lines: {len(new)}")
        if bad:
            print("FAIL - spell-list crash still present:")
            for e in bad:
                print("  " + e)
            return 1
        print("PASS - NecromancerEffigy.CastSpell produced no spell-list errors.")
        return 0


def main():
    ap = argparse.ArgumentParser(description="headless Blakod gameplay test harness")
    sub = ap.add_subparsers(dest="action", required=True)
    sub.add_parser("setup").add_argument("--force", action="store_true")
    sub.add_parser("sync-loadkod")
    c = sub.add_parser("cmd"); c.add_argument("command")
    lv = sub.add_parser("live"); lv.add_argument("command")   # one raw command vs the LIVE server (9998)
    sub.add_parser("smoke")
    t = sub.add_parser("test"); t.add_argument("file")
    a = ap.parse_args()

    if a.action == "setup":
        setup_sandbox(force=a.force); return 0
    if a.action == "sync-loadkod":
        sync_loadkod(); return 0
    if a.action == "cmd":
        with Bench() as b:
            b.reload(); b.cmd(a.command)
        return 0
    if a.action == "live":
        with Bench(launch=False) as b:      # attach to the running server, run one command
            b.cmd(a.command)
        return 0
    if a.action == "smoke":
        return _smoke()
    if a.action == "test":
        lines = [ln.strip() for ln in open(a.file) if ln.strip() and not ln.startswith("#")]
        with Bench() as b:
            b.reload()
            for ln in lines:
                b.cmd(ln)
            new = b.errors_since_start()
        print(f"\n--- {len(new)} new error line(s) ---")
        for e in new:
            print("  " + e)
        return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
