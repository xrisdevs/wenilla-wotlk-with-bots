#!/usr/bin/env python3
"""Live regression: exact bot team starts on all enabled arenas; cleans up its own matches."""
import sys,json,time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import arena_ctl as c
ids=[]
try:
 for arena in ('na','be','rl'):
  before={m['id'] for m in json.loads(c.soap('botarena json'))['matches']}
  c.soap(f'botarena start 3 {arena} tsg tsg')
  new=[m for m in json.loads(c.soap('botarena json'))['matches'] if m['id'] not in before]
  ids.append(new[-1]['id'])
 for i in range(65):
  time.sleep(1)
  matches=[m for m in json.loads(c.soap('botarena json'))['matches'] if m['id'] in ids]
  for m in matches:
   if m['bgStatus']!=2: continue
   assert len(m['bots'])==6,m
   if i>=2:
    assert all(b['setupVerified'] and b['startDistance']<=1 for b in m['bots']),m
 assert all(m['bgStatus']==3 for m in matches),matches
 print('PASS all 18 bots stayed at team starts through preparation and gates opened on Nagrand, Blades Edge, Ruins',flush=True)
finally:
 for mid in ids:c.soap(f'botarena stop {mid}')
