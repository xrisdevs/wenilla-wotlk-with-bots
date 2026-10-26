#!/usr/bin/env python3
"""Fill empty local secrets; never overwrite existing values."""
import pathlib, secrets, os
root=pathlib.Path(__file__).resolve().parents[1]
p=root/'.env'
s=p.read_text() if p.exists() else (root/'.env.example').read_text()
for key in ('MYSQL_ROOT_PASSWORD','MYSQL_PASSWORD','ARENA_SOAP_PASS'):
    s=s.replace(key+'=\n',key+'='+secrets.token_hex(24)+'\n')
p.write_text(s); p.chmod(0o600)
print('Local .env prepared. Set WOW_CLIENT_DIR before running Docker.')
