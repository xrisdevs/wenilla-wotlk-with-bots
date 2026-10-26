#!/usr/bin/env python3
"""Run on the deployment host, after a local build. Does not reset live databases."""
import gzip, os, pathlib, shutil, subprocess, sys, time, urllib.request, json, re
root=pathlib.Path(sys.argv[1]);sha=sys.argv[2];core=sys.argv[3]=='1';presets=sys.argv[4]=='1'
if not re.fullmatch('[0-9a-f]{40}',sha): raise SystemExit('Invalid release revision')
os.chdir(root)
compose=['docker','compose','-f','docker-compose.yml','-f','deploy/hetzner/compose.yml','--profile','browser']
def run(args,**kw):return subprocess.run(args,check=True,**kw)
backup=root/'artifacts/deploy'/sha;backup.mkdir(parents=True,exist_ok=True);backup.chmod(0o700)
# Pause the public service while taking matching guest-state and SQL snapshots.
# Restore service availability if backup creation fails before activation starts.
if shutil.disk_usage(root).free < 5*1024**3: raise RuntimeError('Insufficient disk for deployment backup')
previous=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip()
(backup/'previous-revision').write_text(previous+'\n')
run(compose+['stop','browser'])
try:
    if not (backup/'database.sql.gz').exists():
        producer=subprocess.Popen(compose+['exec','-T','db','sh','-c','MYSQL_PWD="$MYSQL_ROOT_PASSWORD" exec mysqldump -uroot --single-transaction --hex-blob --set-gtid-purged=OFF --no-tablespaces --databases auth characters world'],stdout=subprocess.PIPE)
        temporary=backup/'database.sql.gz.partial'
        with gzip.open(temporary,'wb') as output: shutil.copyfileobj(producer.stdout,output)
        if producer.wait(): raise RuntimeError('Database backup failed; activation cancelled')
        temporary.replace(backup/'database.sql.gz')
    run(['docker','run','--rm','-v','wenilla-wotlk_lobby-data:/state:ro','-v',str(backup)+':/backup','wenilla/trinitycore','tar','-C','/state','-czf','/backup/guest-state.tar.gz','.'])
except Exception:
    subprocess.run(compose+['up','-d','--no-build','browser'])
    raise
run(['git','fetch','origin','arena-with-bots'])
run(['git','checkout','--detach',sha])
if core:
    run(compose+['stop','worldserver','authserver'])
    source=root/'server'
    if source.exists():
        previous=backup/'previous-server'
        if previous.exists(): raise RuntimeError('Previous source backup already exists; review the failed deployment before retrying')
        source.rename(previous)
    run(['python3','scripts/setup-sources.py','server']);run(['bash','scripts/apply-custom.sh'])
    # Preserve prior installed binaries before replacing the inactive server install.
    producer=subprocess.Popen(['docker','run','--rm','-v','wenilla-wotlk_tc-install:/from:ro','wenilla/trinitycore','tar','-C','/from','-czf','-','.'],stdout=subprocess.PIPE)
    with (backup/'previous-install.tar.gz').open('wb') as output:shutil.copyfileobj(producer.stdout,output)
    if producer.wait(): raise RuntimeError('Install backup failed')
    with (backup/'install.tar.gz').open('rb') as data:
        run(['docker','run','--rm','-i','-v','wenilla-wotlk_tc-install:/to','wenilla/trinitycore','tar','-C','/to','-xzf','-'],stdin=data)
if presets:run(['python3','scripts/init-arena.py'])
run(compose+['up','-d','--no-build','db','authserver','worldserver','browser','caddy'])
for attempt in range(90):
    try:
        with urllib.request.urlopen('http://127.0.0.1:8090/healthz',timeout=5) as response:
            if json.load(response).get('ready'):break
    except Exception:pass
    time.sleep(2)
else:raise RuntimeError('Deployment is not healthy; previous source/install and SQL backup are retained for recovery')
print('Deployment healthy:',sha)
