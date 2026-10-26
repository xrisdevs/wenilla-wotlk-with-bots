#!/usr/bin/env python3
"""Initialize durable state once, then supervise the complete private game stack."""
import gzip, os, pathlib, re, secrets, signal, subprocess, sys, time

P = pathlib.Path('/persist')
P.mkdir(exist_ok=True)
for d in ('mysql', 'lobby', 'logs'):
    (P / d).mkdir(exist_ok=True)
for required in ('game-data', 'server-data'):
    if not (P / required / '.ready').exists():
        raise SystemExit(f'Missing /persist/{required}/.ready; upload the data before starting.')
for key in ('ARENA_DB_PASSWORD', 'ARENA_SOAP_PASS'):
    if not re.fullmatch(r'[A-Za-z0-9]{32,128}', os.environ.get(key, '')):
        raise SystemExit(f'{key} must be a generated alphanumeric Fly secret.')
subprocess.run(['chown', '-R', 'mysql:mysql', '/persist/mysql'], check=True)
pathlib.Path('/run/mysqld').mkdir(exist_ok=True)
subprocess.run(['chown', 'mysql:mysql', '/run/mysqld'], check=True)
mysql_args = ['mysqld', '--user=mysql', '--datadir=/persist/mysql', '--bind-address=127.0.0.1',
              '--socket=/run/mysqld/mysqld.sock', '--mysqlx=0', '--max-allowed-packet=256M',
              '--innodb-buffer-pool-size=512M']
if not (P / 'mysql/mysql').exists():
    subprocess.run(mysql_args + ['--initialize-insecure'], check=True)
mysql = subprocess.Popen(mysql_args)
def sql(query, database=None):
    return subprocess.run(['mysql', '-uroot', '--max-allowed-packet=256M'] + ([database] if database else []), input=query, text=isinstance(query, str), check=True)
try:
    for _ in range(120):
        if subprocess.run(['mysqladmin', '-uroot', 'ping'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode == 0:
            break
        if mysql.poll() is not None:
            raise RuntimeError('MySQL exited during startup')
        time.sleep(1)
    else:
        raise RuntimeError('MySQL startup timed out')
    db_password = os.environ['ARENA_DB_PASSWORD']
    sql(f"CREATE USER IF NOT EXISTS 'trinity'@'localhost' IDENTIFIED BY '{db_password}'; ALTER USER 'trinity'@'localhost' IDENTIFIED BY '{db_password}';")
    for db in ('auth', 'characters', 'world'):
        sql(f"CREATE DATABASE IF NOT EXISTS `{db}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci; GRANT ALL ON `{db}`.* TO 'trinity'@'localhost';")
    if not (P / '.database-ready').exists():
        for db in ('auth', 'characters', 'world'):
            print(f'Importing clean {db} seed', flush=True)
            with gzip.open(f'/app/seed/{db}.sql.gz', 'rb') as f:
                sql(f.read(), db)
        (P / '.database-ready').touch()
    sys.path.insert(0, '/app/controller')
    from arena_ctl import srp6_verifier
    salt, verifier = srp6_verifier(os.environ['ARENA_SOAP_USER'], os.environ['ARENA_SOAP_PASS'])
    sql(f"INSERT INTO account(username,salt,verifier,expansion) VALUES('ARENAOP',UNHEX('{salt.hex()}'),UNHEX('{verifier.hex()}'),2) ON DUPLICATE KEY UPDATE salt=VALUES(salt),verifier=VALUES(verifier); REPLACE INTO account_access(AccountID,SecurityLevel,RealmID) SELECT id,3,-1 FROM account WHERE username='ARENAOP'; UPDATE realmlist SET address='127.0.0.1',localAddress='127.0.0.1',port=8085,flag=0;", 'auth')
    # Configuration and credentials are ephemeral; durable game state lives on the volume.
    pathlib.Path('/run/arena').mkdir(mode=0o700, exist_ok=True)
    for server in ('authserver', 'worldserver'):
        text = pathlib.Path(f'/opt/trinitycore/etc/{server}.conf.dist').read_text()
        values = {}
        for line in pathlib.Path(f'/app/conf/{server}.overrides').read_text().splitlines():
            if line.strip() and not line.lstrip().startswith('#'):
                k, v = line.split('=', 1); values[k.strip()] = v.strip()
        values.update({'LoginDatabaseInfo': f'"127.0.0.1;3306;trinity;{db_password};auth"', 'BindIP': '"127.0.0.1"', 'LogsDir': '"/persist/logs"', 'Updates.EnableDatabases': '0'})
        if server == 'worldserver':
            values.update({'WorldDatabaseInfo': f'"127.0.0.1;3306;trinity;{db_password};world"', 'CharacterDatabaseInfo': f'"127.0.0.1;3306;trinity;{db_password};characters"', 'DataDir': '"/persist/server-data"', 'SOAP.IP': '"127.0.0.1"', 'Console.Enable': '0'})
        for k, v in values.items():
            text, n = re.subn(r'^' + re.escape(k) + r'\s*=.*$', f'{k} = {v}', text, flags=re.M)
            if not n: text += f'\n{k} = {v}\n'
        path = pathlib.Path(f'/run/arena/{server}.conf'); path.write_text(text); path.chmod(0o600)
finally:
    subprocess.run(['mysqladmin', '-uroot', 'shutdown'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    mysql.wait(timeout=60)
os.execvp('supervisord', ['supervisord', '-n', '-c', '/app/deploy/fly/supervisord.conf'])
