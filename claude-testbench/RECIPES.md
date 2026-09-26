# Live-server recipes (verified working)

Copy-paste patterns for driving the running blakserv over the **maintenance port** (live = **9998**,
sandbox = 9999). Every command below was confirmed against the live server. Read `CLAUDE.md` for the
protocol basics; this file is the "how do I actually do X" cookbook.

## Ground rules (don't skip)
- Commands are terminated by **CR (`\r`), never `\n`**. Sending `\n` runs nothing.
- `send object <id> <Msg> [params...]` reply format:
  `:< return from OBJECT <id> MESSAGE <Msg> (<msgid>)` then a value line `: OBJECT <id>` / `: INT <n>` /
  `: $ 0` (nil) / `: STRING ...`, then `:>`.
- **Parse the VALUE line only** — `^:\s*(OBJECT \d+|INT -?\d+|\$)`. Do NOT match the "return from OBJECT"
  echo line (that bug made me misread state).
- Params are `<name> <type> <value>` triples. Types: `int`, `object`. Constant names resolve
  (`RID_TOS`, `SID_BLIND`, class names). e.g. `... what object 49966 new_row int 58`.
- **Object 0 = SYS/System** (`send object 0 <SysMessage>`).
- Fast path: use `kodbench.Bench(launch=False)` (connects to the live 9998) and its helpers below.

## Find a player
```
show name <username>                 -> ":< object <id>"     (e.g. diggie -> 111)
send object <id> GetOwner            -> ": OBJECT <roomid>   is CLASS <RoomClass>"
send object <id> GetRow              -> ": INT <row>"
send object <id> GetCol              -> ": INT <col>"
```

## Spawn a mob (and put it in front of a player)
```
create object <MonsterClass>         -> "Created object <mobid>."   (created UNPLACED, not in a room yet)
# place it in the player's room at the player's square (UtilGoNearSquare finds a valid nearby cell):
send object 0 UtilGoNearSquare what object <mobid> where object <roomid> new_row int <row> new_col int <col>
                                     -> ": INT 1"   (1 = placed OK; the mob's AI activates once in a room)
```
Class names are the KOD class, e.g. `GiantRat` (`giarat.kod`), `Troll`, `Claude`.

## Kill a mob (the RIGHT way)
```
send object <mobid> Killed what object <killer>   -> runs the real death: corpse + loot drop, removes the mob
send object <mobid> GetOwner                      -> ": $ 0"   (no owner = dead/removed = confirmed)
```
- `<killer>` = a **player** object -> that player gets **XP + kill credit** + the corpse to loot.
- `<killer>` = the **room** object (or any non-`Player`) -> death happens but **NO player gets XP**
  (the `Killed` handler's XP branch is gated on `IsClass(what,&Player)`). Use this to despawn cleanly.

**DO NOT** kill by raw `AssessDamage ... damage int 99999`. It drops the mob to negative health but leaves
it in a broken half-dead state that then **can't process `Killed`**, and it **orphans the mob's loot**
(items end up with owner `$`, unrecoverable). Always use `Killed`.

## Place items on a monster or a player
```
create object <ItemClass>                          -> "Created object <itemid>."
# put in INVENTORY (held, not worn) -- works on monsters AND players:
send object <targetid> NewHold what object <itemid>
send object <itemid> GetOwner                      -> ": OBJECT <targetid>"   (confirms it's held)
# EQUIP/wear it (players only, after NewHold):
send object <targetid> UserUseItem what object <itemid>
```
- `NewHold` only = in the pack. Add `UserUseItem` to actually wear/wield it.
- Item classes are the KOD class, e.g. `TrollMask` (`trollmsk.kod`), `LeatherArmor`.
- If a mob holds items and you kill it with `Killed`, the items drop as loot on the corpse. (A raw-damage
  kill orphans them instead -- another reason to use `Killed`.)

## Make a monster cast a spell at a target (with the real projectile)
```
send object 0 FindSpellByNum NUM int SID_BLIND     -> the Blind spell singleton (e.g. 48193)
create listnode object <targetid> nil 0            -> builds the list [target]; "Created list node <lid>."
send object <spellobj> CastSpell who object <casterid> lTargets list <lid> iSpellPower int 50
```
- `lTargets` is a LIST param. The maintenance parser passes a list by **list id**: `create listnode <ftag> <fdata> <rtag> <rdata>`
  does `Cons(first,rest)`, so `create listnode object <t> nil 0` = `[t]`. Then pass it as `... lTargets list <lid>`.
- Going through the spell's `CastSpell` runs the spell's own override -> **flying projectile + cast anim** (via
  `SomethingShot`) then the effect. For a monster caster the parent `CastSpell` only does User/DM-gated effects, so
  there's NO mana/reagent/karma cost -- it just works.
- Quicker but NO projectile: `send object <spellobj> DoSpell what object <caster> oTarget object <target> iDuration int 8000`
  (single-object target, applies the effect directly). Use CastSpell when you want it to look real.
- Verify it landed: `send object <target> IsEnchanted what object <spellobj>` -> `INT 1`.
- **Gotcha:** monsters spawned in a TOWN (e.g. Tos/room 42692) get killed by town guards within seconds, and a
  system save renumbers every object. Re-find live targets by `show instances <Class>` filtered on `GetOwner == room`
  rather than reusing old ids.

## Handy lookups
```
show instances <Class>   -> value line ": OBJECT <id> OBJECT <id> ..."  (parse the OBJECT ids)
show object <id>          -> dump the object's properties
set object <id> <prop> <value>   -> set a single property directly (build test state)
```

## Fast path via kodbench (recommended)
```python
import sys; sys.path.insert(0, "claude-testbench")
from kodbench import Bench
with Bench(launch=False) as b:              # connect to the LIVE server (9998); does NOT boot/kill it
    pid = b.find_player("diggie")           # -> "111"
    rat = b.spawn_near(pid, "GiantRat")     # spawn + place on the player -> mob id
    b.give(rat, "TrollMask")                # troll mask into the rat's pack (add wear=True to equip)
    b.kill(rat, by=b.where(pid)[0])         # kill with the ROOM as killer -> no player XP
    # b.kill(rat, by=pid)                    # ...or credit the player (XP)
```

## Worked example (exactly what we ran live)
diggie=obj 111 in Tos room 42692 at (58,13); spawn a rat on him, mask in its pack, kill with room as killer:
```
show name diggie                                     -> object 111
send object 111 GetOwner/GetRow/GetCol               -> room 42692, 58, 13
create object GiantRat                               -> Created object 49966
send object 0 UtilGoNearSquare what object 49966 where object 42692 new_row int 58 new_col int 13  -> INT 1
send object 49966 Killed what object 42692           -> dead, no XP (room is the killer)
```


## Spawned monsters vanish after a few minutes

**Always `SetDontDispose` BEFORE placing a hand-spawned monster.**

```
create object <Class>                                  -> id
send object <id> SetDontDispose bValue int 1           <-- do this FIRST
send object 0 UtilGoNearSquare what object <id> where object <room> new_row int <r> new_col int <c>
```

Rooms sweep themselves with `Room.DestroyDisposable`, and `monster.kod` deletes any monster that
isn't an NPC, has no master, and has no `pbDontDispose` set. A mob you created by hand is exactly
that. Symptom: the spawn reports success, `GetOwner` looks right, but the monster is gone minutes
later -- and in between you get the confusing half-state where `GetOwner` still returns the room
while `show belong <room>` no longer lists it. The source calls this flag the "admin-created
beasties" case. `mcp_blakserv.py`'s `spawn` tool now sets it automatically.
