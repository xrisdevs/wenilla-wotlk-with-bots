#!/usr/bin/env python3
"""Initialize arena presets and the private operator after the first DB import."""
import pathlib, sys
ROOT=pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'controller'))
import arena_ctl
values={}
for line in (ROOT/'.env').read_text().splitlines():
    if '=' in line and not line.lstrip().startswith('#'):
        k,v=line.split('=',1);values[k.strip()]=v.strip()
password=values.get('ARENA_SOAP_PASS','')
if len(password)<32: raise SystemExit('Run scripts/init-env.py to generate ARENA_SOAP_PASS first.')
arena_ctl.account_create(values.get('ARENA_SOAP_USER','ARENAOP'), password, 3)
arena_ctl.sql('world',(ROOT/'custom/sql/world_botarena_gear.sql').read_text())
print('Operator and arena presets initialized. Restart worldserver to reload gear.')
