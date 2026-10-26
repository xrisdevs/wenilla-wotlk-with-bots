#!/usr/bin/env python3
"""Generate Season 8 (Wrathful Gladiator) PvP gear sets per class/spec for the arena bots.

Reads item_template from the world DB, picks set pieces, off-pieces, weapons, relics and trinkets by role,
assigns standard WotLK PvP enchants and gems, and writes custom/sql/world_botarena_gear.sql
(tables botarena_gear + botarena_gear_gems), then applies it unless --no-apply.
"""
import argparse
import os
import subprocess

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "custom", "sql", "world_botarena_gear.sql")

# bot slots (botcommon.h)
MH, OH, RANGED, HEAD, SHOULDERS, CHEST, WAIST, LEGS, FEET, WRIST, HANDS, BACK, BODY, RING1, RING2, TRINK1, TRINK2, NECK = range(18)
# InventoryType
INV = {"head": 1, "neck": 2, "shoulder": 3, "chest": 5, "waist": 6, "legs": 7, "feet": 8, "wrist": 9, "hands": 10, "finger": 11,
       "trinket": 12, "weapon": 13, "shield": 14, "ranged": 15, "back": 16, "2h": 17, "robe": 20, "mainhand": 21, "offhand": 22,
       "held": 23, "thrown": 25, "rangedright": 26, "relic": 28}
# stat types
STAT = {"agi": 3, "str": 4, "int": 5, "spi": 6, "sta": 7, "hit": 31, "crit": 32, "haste": 36, "exp": 37, "ap": 38, "arp": 44,
        "sp": 45, "mp5": 43, "res": 35, "def": 12}
ROLE_WEIGHTS = {
    "caster": {"sp": 1.0, "crit": 0.7, "haste": 0.8, "hit": 0.5, "int": 0.3, "spi": 0.1, "sta": 0.2, "res": 0.5},
    "healer": {"sp": 1.0, "mp5": 1.5, "spi": 0.8, "int": 0.6, "haste": 0.6, "crit": 0.4, "sta": 0.3, "res": 0.6},
    "str":    {"ap": 1.0, "str": 2.2, "crit": 0.9, "arp": 0.8, "exp": 0.7, "hit": 0.5, "sta": 0.3, "res": 0.5},
    "agi":    {"ap": 1.0, "agi": 2.2, "crit": 0.9, "arp": 0.8, "hit": 0.5, "exp": 0.5, "sta": 0.3, "res": 0.5},
}
# enchants (SpellItemEnchantment ids) per role per slot
ENCH = {
    "caster": {HEAD: 3820, SHOULDERS: 3810, CHEST: 3832, WRIST: 2332, HANDS: 3246, LEGS: 3719, FEET: 3232, BACK: 3831},
    "healer": {HEAD: 3819, SHOULDERS: 3809, CHEST: 3832, WRIST: 2332, HANDS: 3246, LEGS: 3719, FEET: 3232, BACK: 3831},
    "str":    {HEAD: 3817, SHOULDERS: 3808, CHEST: 3832, WRIST: 3845, HANDS: 1603, LEGS: 3823, FEET: 3232, BACK: 1099},
    "agi":    {HEAD: 3817, SHOULDERS: 3808, CHEST: 3832, WRIST: 3845, HANDS: 1603, LEGS: 3823, FEET: 3232, BACK: 1099},
}
WEAPON_ENCH = {"melee1h": 3789, "melee2h": 3827, "caster1h": 3834, "caster2h": 3854, "dk2h": 3368, "ranged": 3608}
# gems: red, yellow, blue, meta
GEMS = {
    "caster": (40113, 40155, 40133, 41285),
    "healer": (40113, 40127, 40133, 41401),
    "str":    (40111, 40142, 40129, 41398),
    "agi":    (40112, 40147, 40130, 41398),
}
MEDALLION_A = 51377

# class ids / spec ids (botcommon.h)
PROFILES = [
    # cls, spec, role, armor subclass (cloth1/leather2/mail3/plate4), itemset, weapon plan, ranged plan
    (1, 1, "str", 4, 765, "2h", "thrown"),        # warrior arms
    (1, 2, "str", 4, 765, "2h", "thrown"),        # warrior fury
    (2, 4, "healer", 4, 767, "1h+shield", "relic"),  # paladin holy
    (2, 6, "str", 4, 766, "2h", "relic"),         # paladin ret
    (3, 7, "agi", 3, 772, "2h", "bow"),           # hunter bm
    (3, 8, "agi", 3, 772, "2h", "bow"),           # hunter mm
    (3, 9, "agi", 3, 772, "2h", "bow"),           # hunter surv
    (4, 10, "agi", 2, 776, "dagger+dagger", "thrown"),  # rogue assa
    (4, 11, "agi", 2, 776, "1h+dagger", "thrown"),      # rogue combat
    (4, 12, "agi", 2, 776, "dagger+dagger", "thrown"),  # rogue sub
    (5, 13, "healer", 1, 777, "1h+held", "wand"),   # priest disc
    (5, 14, "healer", 1, 777, "1h+held", "wand"),   # priest holy
    (5, 15, "caster", 1, 778, "1h+held", "wand"),   # priest shadow
    (6, 16, "str", 4, 768, "dk2h", "relic"),      # dk blood
    (6, 17, "str", 4, 768, "dk2h", "relic"),      # dk frost
    (6, 18, "str", 4, 768, "dk2h", "relic"),      # dk unholy
    (7, 19, "caster", 3, 769, "1h+shield", "relic"),  # shaman ele
    (7, 20, "agi", 3, 770, "1h+1h", "relic"),         # shaman enh
    (7, 21, "healer", 3, 771, "1h+shield", "relic"),  # shaman resto
    (8, 22, "caster", 1, 779, "1h+held", "wand"),   # mage arcane
    (8, 23, "caster", 1, 779, "1h+held", "wand"),   # mage fire
    (8, 24, "caster", 1, 779, "1h+held", "wand"),   # mage frost
    (9, 25, "caster", 1, 780, "1h+held", "wand"),   # warlock aff
    (9, 26, "caster", 1, 780, "1h+held", "wand"),   # warlock demo
    (9, 27, "caster", 1, 780, "1h+held", "wand"),   # warlock destro
    (11, 28, "caster", 2, 774, "2h", "relic"),    # druid balance (staff)
    (11, 29, "agi", 2, 775, "2h", "relic"),       # druid feral (staff/polearm)
    (11, 30, "healer", 2, 773, "2h", "relic"),    # druid resto (staff)
]
CLASS_BIT = {1: 1, 2: 2, 3: 4, 4: 8, 5: 16, 6: 32, 7: 64, 8: 128, 9: 256, 11: 1024}
RELIC_SUBCLASS = {2: 7, 6: 10, 7: 9, 11: 8}  # libram, sigil, totem, idol (ITEM_SUBCLASS_ARMOR_*)
STAT_COLS = ",".join(f"stat_type{i},stat_value{i}" for i in range(1, 11))


def q(sql):
    r = subprocess.run(["docker", "compose", "exec", "-T", "db", "sh", "-c", 'MYSQL_PWD="$MYSQL_PASSWORD" exec mysql -utrinity "$@"', "mysql", "--batch", "--skip-column-names", "world"],
                       cwd=ROOT, input=sql, capture_output=True, text=True)
    if r.returncode != 0:
        raise SystemExit(r.stderr)
    return [line.split("\t") for line in r.stdout.splitlines()]


def load_items():
    rows = q(f"SELECT entry,name,class,subclass,InventoryType,AllowableClass,ItemLevel,itemset,{STAT_COLS} FROM item_template "
             f"WHERE (name LIKE 'Wrathful Gladiator%' OR name LIKE 'Relentless Gladiator%' OR name LIKE 'Medallion of the %' OR name LIKE 'Battlemaster%') AND ItemLevel>=245;")
    items = []
    for r in rows:
        stats = {}
        for i in range(10):
            t, v = int(r[8 + 2 * i]), int(r[9 + 2 * i])
            if t and v:
                stats[t] = stats.get(t, 0) + v
        items.append(dict(entry=int(r[0]), name=r[1], cls=int(r[2]), sub=int(r[3]), inv=int(r[4]), allow=int(r[5]),
                          ilvl=int(r[6]), set=int(r[7]), stats=stats))
    return items


def score(item, role):
    w = ROLE_WEIGHTS[role]
    s = 0.0
    for name, weight in w.items():
        s += weight * item["stats"].get(STAT[name], 0)
    return s + item["ilvl"] * 0.5 + (40 if item["name"].startswith("Wrathful") else 0)


def allowed(item, cls):
    a = item["allow"]
    return a in (-1, 0, 0xFFFFFFFF) or (a & CLASS_BIT[cls])


def pick(items, cls, role, pred):
    cands = [i for i in items if allowed(i, cls) and pred(i)]
    if not cands:
        return None
    return max(cands, key=lambda i: (score(i, role), i["ilvl"]))


def weapons(items, cls, role, plan):
    """Return {slot: (item, enchant)} for MH/OH."""
    def w(pred):
        return pick(items, cls, role, lambda i: i["cls"] == 2 and pred(i))
    out = {}
    melee_ench = WEAPON_ENCH["melee1h"]
    if plan == "2h":
        it = w(lambda i: i["inv"] == INV["2h"])
        if it: out[MH] = (it, WEAPON_ENCH["caster2h"] if role in ("caster", "healer") else WEAPON_ENCH["melee2h"])
    elif plan == "dk2h":
        it = w(lambda i: i["inv"] == INV["2h"])
        if it: out[MH] = (it, WEAPON_ENCH["dk2h"])
    elif plan == "1h+shield":
        it = w(lambda i: i["inv"] in (INV["weapon"], INV["mainhand"]))
        if it: out[MH] = (it, WEAPON_ENCH["caster1h"] if role in ("caster", "healer") else melee_ench)
        sh = pick(items, cls, role, lambda i: i["inv"] == INV["shield"])
        if sh: out[OH] = (sh, 0)
    elif plan == "1h+held":
        it = w(lambda i: i["inv"] in (INV["weapon"], INV["mainhand"]))
        if it: out[MH] = (it, WEAPON_ENCH["caster1h"])
        held = pick(items, cls, role, lambda i: i["inv"] == INV["held"])
        if held: out[OH] = (held, 0)
    elif plan == "dagger+dagger":
        mh = w(lambda i: i["inv"] in (INV["weapon"], INV["mainhand"]) and i["sub"] == 15)
        oh = w(lambda i: i["inv"] in (INV["weapon"], INV["offhand"]) and i["sub"] == 15)
        if mh: out[MH] = (mh, melee_ench)
        if oh: out[OH] = (oh, melee_ench)
    elif plan == "1h+dagger":
        mh = w(lambda i: i["inv"] in (INV["weapon"], INV["mainhand"]) and i["sub"] in (7, 0, 4, 13))
        oh = w(lambda i: i["inv"] in (INV["weapon"], INV["offhand"]) and i["sub"] == 15)
        if mh: out[MH] = (mh, melee_ench)
        if oh: out[OH] = (oh, melee_ench)
    elif plan == "1h+1h":
        mh = w(lambda i: i["inv"] in (INV["weapon"], INV["mainhand"]) and i["sub"] != 15)
        oh = w(lambda i: i["inv"] in (INV["weapon"], INV["offhand"]) and i["sub"] != 15)
        if mh: out[MH] = (mh, melee_ench)
        if oh: out[OH] = (oh, melee_ench)
    return out


def ranged(items, cls, role, plan):
    if plan == "bow":
        it = pick(items, cls, role, lambda i: i["cls"] == 2 and i["inv"] == INV["rangedright"] and i["sub"] in (2, 3, 18))
        return (it, WEAPON_ENCH["ranged"]) if it else None
    if plan == "thrown":
        it = pick(items, cls, role, lambda i: i["cls"] == 2 and i["inv"] == INV["thrown"])
        return (it, 0) if it else None
    if plan == "wand":
        it = pick(items, cls, role, lambda i: i["cls"] == 2 and i["sub"] == 19)
        return (it, 0) if it else None
    if plan == "relic":
        sub = RELIC_SUBCLASS.get(cls)
        it = pick(items, cls, role, lambda i: i["inv"] == INV["relic"] and i["sub"] == sub)
        return (it, 0) if it else None
    return None


def build():
    items = load_items()
    rows, gem_rows, report = [], [], []
    set_slots = {INV["head"]: HEAD, INV["shoulder"]: SHOULDERS, INV["chest"]: CHEST, INV["robe"]: CHEST, INV["hands"]: HANDS, INV["legs"]: LEGS}
    for cls, spec, role, armor, itemset, wplan, rplan in PROFILES:
        chosen = {}
        # set pieces: highest ilvl per slot in the set
        for inv, slot in set_slots.items():
            it = pick([i for i in items if i["set"] == itemset], cls, role, lambda i, inv=inv: i["inv"] == inv)
            if it: chosen[slot] = (it, ENCH[role].get(slot, 0))
        # armor off-pieces of the right armor subclass
        for name, slot in (("waist", WAIST), ("feet", FEET), ("wrist", WRIST)):
            it = pick(items, cls, role, lambda i, inv=INV[name]: i["inv"] == inv and i["cls"] == 4 and i["sub"] == armor and i["name"].startswith("Wrathful"))
            if it: chosen[slot] = (it, ENCH[role].get(slot, 0))
        # cloak, neck, rings
        it = pick(items, cls, role, lambda i: i["inv"] == INV["back"] and i["name"].startswith("Wrathful"))
        if it: chosen[BACK] = (it, ENCH[role].get(BACK, 0))
        it = pick(items, cls, role, lambda i: i["inv"] == INV["neck"] and i["name"].startswith("Wrathful"))
        if it: chosen[NECK] = (it, 0)
        # rings: best Wrathful ring, then the best ring with a different name (unique-equipped), Relentless allowed
        rings = sorted([i for i in items if i["inv"] == INV["finger"] and allowed(i, cls)], key=lambda i: -score(i, role))
        if rings:
            chosen[RING1] = (rings[0], 0)
            base = rings[0]["name"].split("'s ", 1)[-1]
            second = next((r for r in rings[1:] if r["name"].split("'s ", 1)[-1] != base), None)
            if second: chosen[RING2] = (second, 0)
        # trinkets: PvP medallion (alliance id; the server swaps the horde one in) + best battlemaster's
        med = next((i for i in items if i["entry"] == MEDALLION_A), None)
        if med: chosen[TRINK1] = (med, 0)
        bm = pick(items, cls, role, lambda i: i["name"].startswith("Battlemaster") and i["inv"] == INV["trinket"])
        if bm: chosen[TRINK2] = (bm, 0)
        chosen.update(weapons(items, cls, role, wplan))
        rg = ranged(items, cls, role, rplan)
        if rg: chosen[RANGED] = rg
        for slot, (it, ench) in sorted(chosen.items()):
            rows.append((cls, spec, slot, it["entry"], ench))
        g = GEMS[role]
        gem_rows.append((cls, spec) + g)
        report.append(f"class {cls:2d} spec {spec:2d} {role:6s}: {len(chosen)} pieces: " + ", ".join(f"{s}:{it['name'].replace('Wrathful Gladiator', 'WG')}" for s, (it, _) in sorted(chosen.items())))
    return rows, gem_rows, report


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-apply", action="store_true")
    a = ap.parse_args()
    rows, gem_rows, report = build()
    with open(OUT, "w") as f:
        f.write("-- Generated by controller/gear_sets.py: Season 8 PvP gear per bot class/spec\n")
        f.write("DROP TABLE IF EXISTS `botarena_gear`;\nCREATE TABLE `botarena_gear` (`class` TINYINT UNSIGNED NOT NULL, `spec` TINYINT UNSIGNED NOT NULL, `slot` TINYINT UNSIGNED NOT NULL, `item` INT UNSIGNED NOT NULL, `enchant` INT UNSIGNED NOT NULL DEFAULT 0, PRIMARY KEY (`class`,`spec`,`slot`)) ENGINE=InnoDB;\n")
        f.write("DROP TABLE IF EXISTS `botarena_gear_gems`;\nCREATE TABLE `botarena_gear_gems` (`class` TINYINT UNSIGNED NOT NULL, `spec` TINYINT UNSIGNED NOT NULL, `gem_red` INT UNSIGNED NOT NULL, `gem_yellow` INT UNSIGNED NOT NULL, `gem_blue` INT UNSIGNED NOT NULL, `gem_meta` INT UNSIGNED NOT NULL, PRIMARY KEY (`class`,`spec`)) ENGINE=InnoDB;\n")
        f.write("INSERT INTO `botarena_gear` VALUES\n" + ",\n".join(f"({c},{s},{sl},{it},{en})" for c, s, sl, it, en in rows) + ";\n")
        f.write("INSERT INTO `botarena_gear_gems` VALUES\n" + ",\n".join(f"({c},{s},{r},{y},{b},{m})" for c, s, r, y, b, m in gem_rows) + ";\n")
    print("\n".join(report))
    print(f"\nwrote {OUT}: {len(rows)} pieces, {len(gem_rows)} gem profiles")
    if not a.no_apply:
        subprocess.run(["docker", "compose", "exec", "-T", "db", "sh", "-c", 'MYSQL_PWD="$MYSQL_PASSWORD" exec mysql -utrinity "$@"', "mysql", "world"], cwd=ROOT, input=open(OUT).read(), text=True, check=True)
        print("applied to world DB")


if __name__ == "__main__":
    main()
