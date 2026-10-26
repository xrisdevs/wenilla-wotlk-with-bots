#!/usr/bin/env python3
"""Snapshot a running full stack into an EMPTY isolated PvP project's DB, then trim it.

Never prunes the source. SQL snapshots and reports are private, local artifacts.
The target must use a wenilla-pvp-* project name and have no world tables.
"""
import argparse
import gzip
import json
import os
from pathlib import Path
import re
import sqlite3
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def compose(project):
    return ['docker', 'compose', '-p', project, '-f', str(ROOT/'docker-compose.yml'),
            '-f', str(ROOT/'docker/pvp-server.compose.yml')]


def sql(project, query):
    result = subprocess.run(compose(project)+['exec', '-T', 'db', 'sh', '-c',
        'MYSQL_PWD="$MYSQL_ROOT_PASSWORD" mysql -uroot --batch --skip-column-names'],
        input=query, text=True, capture_output=True, check=True)
    return result.stdout.strip()


def summary(project):
    tables = ['world.item_template', 'world.creature_template', 'world.gameobject_template',
              'world.botarena_gear', 'world.botarena_gear_gems', 'auth.account', 'characters.characters']
    return {name: int(sql(project, f'SELECT COUNT(*) FROM {name}')) for name in tables}



def snapshot_guests(project, path):
    # The consolidated runtime has no Python interpreter. Use a short-lived helper,
    # mounting the source state read-only and SQLite's online backup API.
    container = subprocess.check_output(compose(project)+['ps','-q','browser'], text=True).strip()
    if not container or '\n' in container:
        raise RuntimeError('Expected one source browser container')
    code = "import sqlite3,sys; source=sqlite3.connect('file:/state/guests.sqlite?mode=ro',uri=True); target=sqlite3.connect(':memory:'); source.backup(target); sys.stdout.buffer.write(target.serialize())"
    with path.open('wb') as output:
        subprocess.run(['docker','run','--rm','--volumes-from',container+':ro',
                        'wenilla/trinitycore','python3','-c',code], stdout=output, check=True)
    os.chmod(path, 0o600)


def install_guests(project, path, merge=False):
    with sqlite3.connect(path) as state:
        accounts = [int(row[0]) for row in state.execute('SELECT account FROM guests')]
    if accounts:
        found = int(sql(project, 'SELECT COUNT(*) FROM auth.account WHERE id IN ('+','.join(map(str,accounts))+')'))
        if found != len(accounts):
            raise RuntimeError('Guest ownership references accounts absent from the target snapshot')
    code = """import os,sqlite3,shutil
from pathlib import Path
source=Path('/seed/guests.sqlite'); target=Path('/state/guests.sqlite')
if target.exists():
    if not MERGE: raise SystemExit('Target guest state already exists')
    db=sqlite3.connect(target)
    db.execute("ATTACH DATABASE '/seed/guests.sqlite' AS seed")
    with db:
        db.execute('INSERT OR IGNORE INTO guests SELECT * FROM seed.guests')
        db.execute('INSERT OR IGNORE INTO characters SELECT * FROM seed.characters')
        missing=db.execute('SELECT COUNT(*) FROM seed.guests s LEFT JOIN guests g ON g.token=s.token AND g.account=s.account WHERE g.token IS NULL').fetchone()[0]
        if missing: raise RuntimeError('Conflicting guest ownership; refusing migration')
    db.close()
else:
    shutil.copyfile(source,target)
os.chown(target,65534,65534);os.chmod(target,0o600)
""".replace('MERGE',repr(merge))
    subprocess.run(['docker','run','--rm','-v',f'{path.resolve()}:/seed/guests.sqlite:ro',
                    '-v',f'{project}_lobby-data:/state','wenilla/trinitycore','python3','-c',code],check=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-project', default='wenilla-wotlk')
    parser.add_argument('--project', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if not re.fullmatch(r'wenilla-pvp-[a-z0-9-]+', args.project) or args.project == args.source_project:
        raise SystemExit('Target must be a separate wenilla-pvp-* project')
    output = args.output.resolve()
    if output.exists():
        raise SystemExit('Choose a new private output directory')
    output.mkdir(parents=True, mode=0o700)
    os.chmod(output, 0o700)
    subprocess.run(compose(args.project)+['up', '-d', '--wait', 'db'], check=True)
    if int(sql(args.project, "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema IN ('world','characters','auth')")):
        raise SystemExit('Target DB is not empty; refusing to replace existing state')
    if int(sql(args.source_project, "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema='world' AND table_name='pvp_profile_metadata'")):
        raise SystemExit('Source is already trimmed; rebuild from an updated full baseline')
    snapshot_guests(args.source_project, output/'guests.sqlite')
    before = summary(args.source_project)
    print('Snapshotting full databases into private local backup...', flush=True)
    dump = subprocess.Popen(compose(args.source_project)+['exec','-T','db','sh','-c',
        'MYSQL_PWD="$MYSQL_ROOT_PASSWORD" mysqldump -uroot --single-transaction --quick --hex-blob --no-tablespaces --set-gtid-purged=OFF --databases auth characters world'], stdout=subprocess.PIPE)
    partial = output/'full.sql.gz.partial'
    with gzip.open(partial, 'wb') as target:
        while chunk := dump.stdout.read(1024*1024):
            target.write(chunk)
    if dump.wait():
        raise SystemExit('Snapshot failed; original DB unchanged')
    os.chmod(partial, 0o600)
    snapshot = output/'full.sql.gz'
    partial.rename(snapshot)
    print('Importing snapshot into isolated DB...', flush=True)
    restore = subprocess.Popen(compose(args.project)+['exec','-T','db','sh','-c',
        'MYSQL_PWD="$MYSQL_ROOT_PASSWORD" mysql -uroot'], stdin=subprocess.PIPE)
    with gzip.open(snapshot, 'rb') as source:
        while chunk := source.read(1024*1024):
            restore.stdin.write(chunk)
    restore.stdin.close()
    if restore.wait():
        raise SystemExit('Restore failed; target remains inactive')
    if summary(args.project) != before:
        raise SystemExit('Snapshot row counts changed; do not activate target')
    profile = json.loads((ROOT/'docker/pvp-server.json').read_text())
    map_ids = ','.join(str(int(m)) for m in profile['pvp_maps'])
    tables = set(sql(args.project, 'SHOW TABLES FROM world').splitlines())
    changes = []
    locales = sorted(t for t in tables if t.endswith('_locale'))
    for table in locales + ['quest_poi', 'quest_poi_points', 'game_weather']:
        if table in tables:
            changes.append(f'TRUNCATE TABLE `{table}`;')
    changes += [
        f'DELETE FROM creature WHERE map NOT IN ({map_ids}) AND id NOT IN (SELECT entry FROM creature_template_npcbot_extras);',
        f'DELETE FROM gameobject WHERE map NOT IN ({map_ids});',
        f'DELETE FROM creature_template_npcbot_wander_nodes WHERE mapid NOT IN ({map_ids});',
    ]
    refs = {'creature': {'creature_addon':'guid', 'creature_movement_override':'SpawnId',
                        'game_event_creature':'guid', 'game_event_model_equip':'guid', 'game_event_npcflag':'guid'},
            'gameobject': {'gameobject_addon':'guid','gameobject_overrides':'spawnId','game_event_gameobject':'guid'}}
    changed = set(locales + ['creature','gameobject','creature_template_npcbot_wander_nodes'])
    for parent, children in refs.items():
        for table, col in children.items():
            if table in tables:
                changes.append(f'DELETE c FROM `{table}` c LEFT JOIN `{parent}` p ON c.`{col}`=p.guid WHERE p.guid IS NULL;')
                changed.add(table)
    changes += [
        'DELETE f FROM creature_formations f LEFT JOIN creature a ON a.guid=f.leaderGUID LEFT JOIN creature b ON b.guid=f.memberGUID WHERE a.guid IS NULL OR b.guid IS NULL;',
        'DELETE s FROM spawn_group s LEFT JOIN creature c ON s.spawnId=c.guid LEFT JOIN gameobject g ON s.spawnId=g.guid WHERE (s.spawnType=0 AND c.guid IS NULL) OR (s.spawnType=1 AND g.guid IS NULL);',
        'DELETE p FROM pool_members p LEFT JOIN creature c ON p.spawnId=c.guid LEFT JOIN gameobject g ON p.spawnId=g.guid WHERE (p.type=0 AND c.guid IS NULL) OR (p.type=1 AND g.guid IS NULL);',
        'DELETE s FROM smart_scripts s LEFT JOIN creature c ON s.entryorguid=-c.guid LEFT JOIN gameobject g ON s.entryorguid=-g.guid WHERE s.entryorguid<0 AND ((s.source_type=0 AND c.guid IS NULL) OR (s.source_type=1 AND g.guid IS NULL));',
        'DELETE r FROM linked_respawn r LEFT JOIN creature c ON c.guid=r.guid LEFT JOIN creature lc ON lc.guid=r.linkedGuid LEFT JOIN gameobject g ON g.guid=r.guid LEFT JOIN gameobject lg ON lg.guid=r.linkedGuid WHERE (r.linkType IN (0,1) AND c.guid IS NULL) OR (r.linkType IN (2,3) AND g.guid IS NULL) OR (r.linkType IN (0,3) AND lc.guid IS NULL) OR (r.linkType IN (1,2) AND lg.guid IS NULL);',
        # Retain paths referenced by templates or any SmartAI parameter as a conservative safety margin.
        'CREATE TEMPORARY TABLE pvp_keep_paths (id INT UNSIGNED PRIMARY KEY);',
        'INSERT IGNORE INTO pvp_keep_paths SELECT path_id FROM creature_addon UNION SELECT path_id FROM creature_template_addon;',
    ]
    for i in range(1,7):
        changes.append(f'INSERT IGNORE INTO pvp_keep_paths SELECT action_param{i} FROM smart_scripts;')
    changes += ['DELETE w FROM waypoint_data w LEFT JOIN pvp_keep_paths k ON k.id=w.id WHERE k.id IS NULL;',
                'DROP TEMPORARY TABLE pvp_keep_paths;']
    changed.update(['creature_formations','spawn_group','pool_members','smart_scripts','linked_respawn','waypoint_data'])
    print('Trimming clone; preserving shared definitions and all player data...', flush=True)
    sql(args.project, 'USE world;\n'+ '\n'.join(changes))
    # Rebuild changed InnoDB tables so deleted rows actually release allocated table space.
    sql(args.project, 'USE world; OPTIMIZE TABLE '+','.join(f'`{t}`' for t in sorted(changed))+ ';')
    after = summary(args.project)
    if before != after:
        raise SystemExit('Critical row counts changed; refusing completion marker')
    if int(sql(args.project, 'SELECT COUNT(*) FROM world.creature_template_npcbot_wander_nodes')) == 0:
        raise SystemExit('NPCBot PvP navigation nodes are missing')
    install_guests(args.project, output/'guests.sqlite')
    source_pin = json.loads((ROOT/'sources.json').read_text())['server']['revision']
    sql(args.project, f'''CREATE TABLE world.pvp_profile_metadata (id INT PRIMARY KEY, schema_version INT NOT NULL, source_pin CHAR(40) NOT NULL, built_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP);
        INSERT INTO world.pvp_profile_metadata (id,schema_version,source_pin) VALUES(1,1,'{source_pin}');''')
    stats = sql(args.project, "SELECT table_schema,ROUND(SUM(data_length+index_length)/1024/1024,2) FROM information_schema.tables WHERE table_schema IN ('auth','characters','world') GROUP BY table_schema;")
    report = {'schema_version': 1, 'source_pin': source_pin, 'preserved_counts': after,
              'empty_locale_tables': locales, 'database_mib': stats.splitlines(), 'profile': profile}
    (output/'report.json').write_text(json.dumps(report,indent=2)+'\n')
    print(stats, flush=True)
    print('PvP database ready; original databases and TDB cache untouched.', flush=True)


if __name__ == '__main__':
    main()
