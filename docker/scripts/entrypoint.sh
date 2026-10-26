#!/usr/bin/env bash
# Generate <server>.conf from the installed .conf.dist plus key=value overrides in /conf/<server>.overrides, then exec it.
set -euo pipefail
SERVER="$1"            # authserver | worldserver
CONFDIR=/opt/trinitycore/etc
RUNCONF=/run/trinity; mkdir -p "$RUNCONF" /logs
cp "$CONFDIR/$SERVER.conf.dist" "$RUNCONF/$SERVER.conf"
if [ -f "/conf/$SERVER.overrides" ]; then
  python3 - "$RUNCONF/$SERVER.conf" "/conf/$SERVER.overrides" <<'PY'
import re, sys, os
conf, ovr = sys.argv[1], sys.argv[2]
text = open(conf).read()
lines = open(ovr).readlines()
if os.environ.get("PVP_SERVER_PROFILE") == "1":
    lines += open("/conf/pvp-server.overrides").readlines()
for line in lines:
    line = line.strip()
    if not line or line.startswith('#'): continue
    k, v = [s.strip() for s in line.split('=', 1)]
    v = v.replace('@DB_PASSWORD@', os.environ['MYSQL_PASSWORD'])
    pat = re.compile(r'^' + re.escape(k) + r'\s*=.*$', re.M)
    text, n = pat.subn(f'{k} = {v}', text)
    if n == 0: text += f'\n{k} = {v}\n'
open(conf, 'w').write(text)
PY
fi
# wait for the DB
for i in $(seq 1 60); do
  MYSQL_PWD="$MYSQL_PASSWORD" mysql --protocol=TCP -h db -u trinity -N -e "SELECT 1" >/dev/null 2>&1 && break; echo "waiting for db ($i)"; sleep 2
done
# Prepare the verified world seed in this container; no separate setup container is needed.
if [ "${PVP_SERVER_PROFILE:-0}" = 1 ]; then
  # Fail closed on an unprepared/full database. Never run upstream updates on a trimmed world.
  profile_version=$(MYSQL_PWD="$MYSQL_PASSWORD" mysql --protocol=TCP -h db -u trinity -N -e 'SELECT schema_version FROM world.pvp_profile_metadata WHERE id=1')
  [ "$profile_version" = 1 ] || { echo "PvP profile is missing or unsupported" >&2; exit 1; }
  profile_pin=$(MYSQL_PWD="$MYSQL_PASSWORD" mysql --protocol=TCP -h db -u trinity -N -e 'SELECT source_pin FROM world.pvp_profile_metadata WHERE id=1')
  [ "$profile_pin" = "$(git -C /src rev-parse HEAD)" ] || { echo "PvP source pin changed: regenerate the profile from an updated full database" >&2; exit 1; }
  if [ "$SERVER" = worldserver ]; then
    [ -r /data/pvp-profile.json ] || { echo "Verified PvP map data is missing" >&2; exit 1; }
  fi
elif [ "$SERVER" = worldserver ]; then
  python3 /scripts/fetch-tdb.py
fi
# worldserver looks for the TDB_full_world_*.sql base file in its working directory
WD=/run/trinity/wd; mkdir -p "$WD"; cd "$WD"
if [ "$SERVER" = worldserver ] && [ "${PVP_SERVER_PROFILE:-0}" != 1 ]; then for f in /tdb/*.sql; do [ -e "$f" ] && ln -sf "$f" "$WD/"; done; fi
exec "/opt/trinitycore/bin/$SERVER" -c "$RUNCONF/$SERVER.conf"
