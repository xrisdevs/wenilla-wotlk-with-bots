#!/usr/bin/env python3
"""Stage the tested browser bundle and clean SQL seeds, never local accounts."""
import gzip, pathlib, shutil, subprocess
ROOT = pathlib.Path(__file__).resolve().parents[2]
OUT = ROOT / 'artifacts/fly'
OUT.mkdir(parents=True, exist_ok=True)
shutil.copytree(ROOT / 'client/benilla-src/web/dist', OUT / 'www', dirs_exist_ok=True)
(OUT / 'seed').mkdir(exist_ok=True)
def dump(db, args):
    return subprocess.check_output(['docker', 'compose', 'exec', '-T', 'db', 'sh', '-c', 'MYSQL_PWD="$MYSQL_ROOT_PASSWORD" exec mysqldump -uroot "$@"', 'mysqldump', '--hex-blob', '--single-transaction', '--set-gtid-purged=OFF', '--no-tablespaces', '--column-statistics=0', *args, db], cwd=ROOT)
# Schema includes current custom fields; only static reference rows are copied.
for db in ('auth', 'characters', 'world'):
    data = dump(db, [] if db == 'world' else ['--no-data'])
    if db != 'world':
        tables = ['updates', 'updates_include']
        if db == 'auth': tables += ['realmlist', 'rbac_permissions', 'rbac_linked_permissions', 'rbac_default_permissions', 'build_info', 'build_auth_key', 'build_executable_hash']
        data += subprocess.check_output(['docker', 'compose', 'exec', '-T', 'db', 'sh', '-c', 'MYSQL_PWD="$MYSQL_ROOT_PASSWORD" exec mysqldump -uroot "$@"', 'mysqldump', '--hex-blob', '--single-transaction', '--set-gtid-purged=OFF', '--no-tablespaces', '--column-statistics=0', '--no-create-info', db, *tables], cwd=ROOT)
    with gzip.open(OUT / f'seed/{db}.sql.gz', 'wb') as f: f.write(data)
    print(f'Staged clean {db} seed', flush=True)
