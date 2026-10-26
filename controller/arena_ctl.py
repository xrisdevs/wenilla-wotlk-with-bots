#!/usr/bin/env python3
"""BotArena controller: orchestrate the TrinityCore+NPCBots stack, GM commands and bot arena matches.

No third-party dependencies. Talks to worldserver via SOAP (port 7878), to MySQL via `docker compose exec db mysql`,
and to Docker via `docker compose`.

Examples:
  arena_ctl.py up                      # start db + authserver + worldserver
  arena_ctl.py logs -f                 # tail worldserver logs
  arena_ctl.py account create OPERATOR PASSWORD --gm 3
  arena_ctl.py cmd ".server info"      # any GM command via SOAP
  arena_ctl.py start 3 na rmp tsg      # bot 3v3: RMP (A) vs TSG (H) in Nagrand
  arena_ctl.py spectate Caster         # teleport character 'Caster' in as invisible spectator
  arena_ctl.py cam auto Caster         # auto camera for that spectator
  arena_ctl.py json                    # live match state as JSON
  arena_ctl.py serve 8765              # tiny HTTP JSON endpoint (/status) for overlays
"""
import argparse
import base64
import hashlib
import http.server
import json
import os
import re
import secrets
import subprocess
import sys
import urllib.request
import xml.etree.ElementTree as ET

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SOAP_URL = os.environ.get("ARENA_SOAP_URL", "http://127.0.0.1:7878/")
SOAP_USER = os.environ.get("ARENA_SOAP_USER", "ARENAOP")
SOAP_PASS = os.environ.get("ARENA_SOAP_PASS", "")


# ----------------------------------------------------------------------------- docker helpers
def compose(*args, check=True, capture=False, input_text=None):
    cmd = ["docker", "compose", *args]
    return subprocess.run(cmd, cwd=ROOT, check=check, text=True,
                          capture_output=capture, input=input_text)


def sql(db, query, capture=True):
    """Use a configured private MySQL host, or the local development container."""
    if os.environ.get("ARENA_DB_HOST"):
        env = {**os.environ, "MYSQL_PWD": os.environ["ARENA_DB_PASSWORD"]}
        r = subprocess.run(["mysql", "--protocol=TCP", "--connect-timeout=10",
                            "-h", os.environ["ARENA_DB_HOST"],
                            "-P", os.environ.get("ARENA_DB_PORT", "3306"),
                            "-u", os.environ.get("ARENA_DB_USER", "trinity"),
                            "--batch", "--skip-column-names", db],
                           input=query, text=True, capture_output=True, env=env, timeout=30)
    else:
        r = compose("exec", "-T", "db", "sh", "-c", 'MYSQL_PWD="$MYSQL_PASSWORD" exec mysql -utrinity --batch --skip-column-names "$1"', "mysql", db,
                    check=False, capture=True, input_text=query)
    if r.returncode != 0:
        raise SystemExit(f"mysql error: {r.stderr.strip()}")
    return r.stdout


# ----------------------------------------------------------------------------- SOAP
def soap(command):
    envelope = f"""<?xml version="1.0" encoding="utf-8"?>
<SOAP-ENV:Envelope xmlns:SOAP-ENV="http://schemas.xmlsoap.org/soap/envelope/" xmlns:ns1="urn:TC">
  <SOAP-ENV:Body><ns1:executeCommand><command>{escape(command)}</command></ns1:executeCommand></SOAP-ENV:Body>
</SOAP-ENV:Envelope>"""
    req = urllib.request.Request(SOAP_URL, data=envelope.encode(), method="POST")
    req.add_header("Content-Type", "text/xml; charset=utf-8")
    req.add_header("Authorization", "Basic " + base64.b64encode(f"{SOAP_USER}:{SOAP_PASS}".encode()).decode())
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            body = resp.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "replace")
    except Exception as e:  # noqa: BLE001
        raise SystemExit(f"SOAP request failed ({SOAP_URL}): {e}. Is worldserver up and the account an admin?")
    # result is in <result>...</result>, faults in <faultstring>
    try:
        root = ET.fromstring(body)
    except ET.ParseError:
        return body
    for tag in ("result", "faultstring"):
        for el in root.iter():
            if el.tag.endswith(tag) and el.text is not None:
                return el.text
    return body


def escape(s):
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


# ----------------------------------------------------------------------------- SRP6 (TrinityCore 3.3.5 auth)
SRP_N = int("894B645E89E1535BBDAD5B8B290650530801B18EBFBF5E8FAB3C82872A3E9BB7", 16)
SRP_G = 7


def srp6_verifier(username, password, salt=None):
    salt = salt or secrets.token_bytes(32)
    h1 = hashlib.sha1(f"{username.upper()}:{password.upper()}".encode()).digest()
    x = int.from_bytes(hashlib.sha1(salt + h1).digest(), "little")
    v = pow(SRP_G, x, SRP_N)
    return salt, v.to_bytes(32, "little")


def account_create(user, password, gm_level):
    if not re.fullmatch(r"[A-Za-z0-9_]{1,16}", user):
        raise ValueError("Account name must contain 1–16 letters, digits or underscores")
    salt, verifier = srp6_verifier(user, password)
    existing = sql("auth", f"SELECT id FROM account WHERE username='{user.upper()}';").strip()
    if existing:
        sql("auth", f"UPDATE account SET salt=UNHEX('{salt.hex()}'), verifier=UNHEX('{verifier.hex()}') WHERE id={existing};")
        acc_id = int(existing)
        print(f"account {user} exists (id {acc_id}), password updated")
    else:
        sql("auth", f"INSERT INTO account (username, salt, verifier, expansion) VALUES ('{user.upper()}', UNHEX('{salt.hex()}'), UNHEX('{verifier.hex()}'), 2);")
        acc_id = int(sql("auth", f"SELECT id FROM account WHERE username='{user.upper()}';").strip())
        print(f"account {user} created (id {acc_id})")
    if gm_level:
        sql("auth", f"REPLACE INTO account_access (AccountID, SecurityLevel, RealmID) VALUES ({acc_id}, {gm_level}, -1);")
        print(f"gm level {gm_level} set")


def realmlist_set(address):
    sql("auth", f"UPDATE realmlist SET address='{address}', localAddress='{address}';")
    print(sql("auth", "SELECT id, name, address, localAddress, port FROM realmlist;"))


# ----------------------------------------------------------------------------- results log
def summarize_results(last_n=0):
    """Read /logs/botarena_matches.jsonl from the logs volume and print win rates per comp pairing."""
    r = compose("exec", "-T", "worldserver", "cat", "/logs/botarena_matches.jsonl", capture=True)
    rows = [json.loads(l) for l in r.stdout.splitlines() if l.strip()]
    if last_n:
        rows = rows[-last_n:]
    if not rows:
        print("no results yet")
        return
    from collections import defaultdict
    pair = defaultdict(lambda: [0, 0, 0, 0.0])  # winsA, winsH, draws, duration
    for m in rows:
        k = f'{m["compA"]} vs {m["compH"]}'
        p = pair[k]
        if m["winner"] == "A": p[0] += 1
        elif m["winner"] == "H": p[1] += 1
        else: p[2] += 1
        p[3] += m["duration"]
    print(f"{len(rows)} matches")
    for k, (wa, wh, d, dur) in sorted(pair.items(), key=lambda kv: -sum(kv[1][:3])):
        n = wa + wh + d
        print(f"  {k:40s} n={n:3d}  A {wa/n:5.0%}  H {wh/n:5.0%}  draw {d/n:4.0%}  avg {dur/n:4.0f}s")
    dmg = defaultdict(lambda: [0, 0, 0])
    for m in rows:
        for b in m["bots"]:
            k = f'{b["class"]}/{b["spec"]}'
            dmg[k][0] += b["damage"]; dmg[k][1] += b["healing"]; dmg[k][2] += 1
    print("per spec averages (damage / healing per match):")
    for k, (dm, hl, n) in sorted(dmg.items(), key=lambda kv: -(kv[1][0] / kv[1][2])):
        print(f"  {k:18s} dmg {dm/n:8.0f}  heal {hl/n:8.0f}  (n={n})")


# ----------------------------------------------------------------------------- HTTP status endpoint
class StatusHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802
        if self.path.startswith("/status"):
            data = soap(".botarena json")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(data.encode())
        elif self.path.startswith("/cmd?"):
            from urllib.parse import parse_qs, urlparse
            q = parse_qs(urlparse(self.path).query).get("c", [""])[0]
            out = soap(q) if q.startswith(".botarena") else "only .botarena commands are allowed here"
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            self.wfile.write(out.encode())
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, *a):  # quiet
        pass


# ----------------------------------------------------------------------------- CLI
def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("up", help="start db, authserver, worldserver")
    sub.add_parser("down", help="stop the stack")
    sub.add_parser("restart", help="restart worldserver only")
    sub.add_parser("ps", help="container status")
    lg = sub.add_parser("logs", help="worldserver logs")
    lg.add_argument("-f", action="store_true")
    lg.add_argument("-n", default="100")
    sub.add_parser("build", help="apply custom patches and rebuild the core")
    sub.add_parser("extract", help="extract client data (maps/vmaps/mmaps)")

    ac = sub.add_parser("account", help="account management")
    acs = ac.add_subparsers(dest="acmd", required=True)
    c = acs.add_parser("create")
    c.add_argument("user")
    c.add_argument("password")
    c.add_argument("--gm", type=int, default=3)
    acs.add_parser("list")

    rl = sub.add_parser("realmlist", help="set realm address")
    rl.add_argument("address", nargs="?", default="127.0.0.1")

    cm = sub.add_parser("cmd", help="run a GM command via SOAP")
    cm.add_argument("command", nargs="+")

    st = sub.add_parser("start", help="start a bot arena match")
    st.add_argument("args", nargs="*", help="[2|3|5] [na|be|rl|ds|rv|random] [compA] [compH]")
    sub.add_parser("stop")
    sub.add_parser("status")
    sub.add_parser("json")
    sub.add_parser("comps")
    sp = sub.add_parser("spectate")
    sp.add_argument("player")
    ca = sub.add_parser("cam")
    ca.add_argument("target", help="1-10 | bot name | auto | off")
    ca.add_argument("player")
    au = sub.add_parser("auto")
    au.add_argument("state", choices=["on", "off"])
    au.add_argument("delay", nargs="?", default="")
    bt = sub.add_parser("batch", help="headless match farm: batch <count> <concurrency> [2|3|5] [arena] [compA] [compH] | batch stop | batch status")
    bt.add_argument("args", nargs="*")
    br = sub.add_parser("brain", help="ArenaBrain params: show | reload | set <key> <value>")
    br.add_argument("args", nargs="*")
    rs = sub.add_parser("results", help="summarize the match results log (JSONL) from the server")
    rs.add_argument("-n", type=int, default=0, help="only the last N matches")
    sv = sub.add_parser("serve", help="HTTP JSON endpoint for overlays")
    sv.add_argument("port", nargs="?", type=int, default=8765)

    a = p.parse_args()
    if a.cmd == "up":
        compose("up", "-d", "db", "authserver", "worldserver")
    elif a.cmd == "down":
        compose("down")
    elif a.cmd == "restart":
        compose("restart", "worldserver")
    elif a.cmd == "ps":
        compose("ps")
    elif a.cmd == "logs":
        compose("logs", "--tail", a.n, *(["-f"] if a.f else []), "worldserver", check=False)
    elif a.cmd == "build":
        subprocess.run([os.path.join(ROOT, "scripts", "apply-custom.sh")], check=True)
        compose("--profile", "build", "run", "--rm", "build")
    elif a.cmd == "extract":
        compose("--profile", "extract", "run", "--rm", "extract")
    elif a.cmd == "account":
        if a.acmd == "create":
            account_create(a.user, a.password, a.gm)
        else:
            print(sql("auth", "SELECT a.id, a.username, IFNULL(aa.SecurityLevel,0) FROM account a LEFT JOIN account_access aa ON aa.AccountID=a.id;"))
    elif a.cmd == "realmlist":
        realmlist_set(a.address)
    elif a.cmd == "cmd":
        print(soap(" ".join(a.command)))
    elif a.cmd == "start":
        print(soap(".botarena start " + " ".join(a.args)))
    elif a.cmd == "stop":
        print(soap(".botarena stop all"))
    elif a.cmd == "batch":
        print(soap(".botarena batch " + " ".join(a.args)))
    elif a.cmd == "brain":
        print(soap(".botarena brain " + " ".join(a.args)))
    elif a.cmd == "results":
        summarize_results(a.n)
    elif a.cmd == "status":
        print(soap(".botarena status"))
    elif a.cmd == "json":
        out = soap(".botarena json")
        try:
            print(json.dumps(json.loads(out.strip()), indent=2))
        except ValueError:
            print(out)
    elif a.cmd == "comps":
        print(soap(".botarena comps"))
    elif a.cmd == "spectate":
        print(soap(f".botarena spectate {a.player}"))
    elif a.cmd == "cam":
        print(soap(f".botarena cam {a.target} {a.player}"))
    elif a.cmd == "auto":
        print(soap(f".botarena auto {a.state} {a.delay}".strip()))
    elif a.cmd == "serve":
        print(f"serving http://127.0.0.1:{a.port}/status")
        http.server.HTTPServer(("127.0.0.1", a.port), StatusHandler).serve_forever()


if __name__ == "__main__":
    main()
