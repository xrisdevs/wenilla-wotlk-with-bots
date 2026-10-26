#!/usr/bin/env python3
"""Exercise ten dedicated guests, all loadouts, and real 2v2/3v3 human matches.
Requires the lobby, server and the native lobby_probe example; never uses existing player accounts.
"""
import asyncio,json,os,pathlib,sys,tempfile,time
import aiohttp
sys.path.insert(0,str(pathlib.Path(__file__).parent))
from service import ROOT,BUILDS
import arena_ctl as core

async def main():
    peers=[];processes=[]
    async def call(client,path,data=None,method='POST'):
        async with client.request(method,'http://127.0.0.1:8090/api/'+path,json=data) as r:
            body=await r.json()
            if r.status>=400:raise RuntimeError(f'{path}: {r.status}: {body.get("error")}')
            return body
    try:
        for i,b in enumerate(BUILDS):
            c=aiohttp.ClientSession(cookie_jar=aiohttp.CookieJar(unsafe=True));peers.append({'http':c,'build':b})
            cache=ROOT/f'artifacts/lobby/live-guest-{b["id"]}.json'
            if cache.exists():
                saved=json.loads(cache.read_text());c.cookie_jar.update_cookies(saved['cookies'])
            state=await call(c,'session')
            char=next((ch for ch in state['characters'] if ch['build']==b['id']),None)
            if not char:char=await call(c,'characters',{'build':b['id'],'name':''})
            cache.write_text(json.dumps({'cookies':{m.key:m.value for m in c.cookie_jar}}));cache.chmod(0o600)
            cred=await call(c,'credentials',method='GET')
            env={**os.environ,'WOW_USER':cred['user'],'WOW_PASS':cred['pass'],'WOW_CHAR':char['name'],'PROBE_RACE':str(b['raceId']),'PROBE_CLASS':str(b['classId']),'PROBE_SECONDS':'360'}
            log=open(ROOT/f'artifacts/lobby/peer-{i}.log','w')
            p=await asyncio.create_subprocess_exec(str(ROOT/'client/benilla-src/target/debug/examples/lobby_probe'),env=env,stdout=log,stderr=log);processes.append((p,log));peers[-1]['name']=char['name']
            for attempt in range(30):
                await asyncio.sleep(1)
                if p.returncode is not None:raise RuntimeError(f'Peer {b["name"]} exited: inspect peer-{i}.log')
                try:await call(c,'prepare',{'name':char['name']});break
                except RuntimeError as e:
                    if 'connecting' not in str(e) and 'teleport' not in str(e) and 'combat and' not in str(e):raise
            else:raise RuntimeError('Provisioning timed out')
            print('LOADOUT PASS',b['name'],flush=True)
        for size,group in [(2,peers[:4]),(3,peers[4:])]:
            for i,p in enumerate(group):
                status=await call(p['http'],'play',{'name':p['name'],'size':size,'mode':'players'})
                assert status['state']==('playing' if i==len(group)-1 else 'queued'),status
            for p in group:
                result=await call(p['http'],'queue',method='GET');assert result['state']=='playing',result
            print('MATCHMAKING PASS',size,'v',size,flush=True)
        await asyncio.sleep(5)
        status=json.loads(await asyncio.to_thread(core.soap,'botarena json'))
        for size in (2,3):
            matches=[m for m in status['matches'] if m['type']==size and len(m.get('humans',[]))==size*2]
            assert matches,f'Missing live {size}v{size}'
            match=matches[-1]
            assert len(match['bots'])==0,match
            assert all(p['joined'] for p in match['humans']),match
            assert sum(p['team']=='A' for p in match['humans'])==size,match
            print('ARENA ENTRY PASS',size,'v',size,'all humans joined, no bots',flush=True)
        # Check the persisted, server-created equipment/talent/glyph records, not the catalog claims.
        for p in peers:
            name=p['name']
            stats=await asyncio.to_thread(core.sql,'characters',f"SELECT c.level,(SELECT COUNT(*) FROM character_inventory i WHERE i.guid=c.guid AND i.bag=0 AND i.slot<19),(SELECT COUNT(*) FROM character_talent t WHERE t.guid=c.guid),(SELECT (glyph1>0)+(glyph2>0)+(glyph3>0)+(glyph4>0)+(glyph5>0)+(glyph6>0) FROM character_glyphs g WHERE g.guid=c.guid AND g.talentGroup=0) FROM characters c WHERE name='{name}';")
            level,items,talents,glyphs=map(int,stats.strip().split('\t'))
            assert level==80 and items>=16 and talents==len(p['build']['talentSummary']) and glyphs==6,(p['build']['name'],stats)
            print('SAVED LOADOUT PASS',p['build']['name'],flush=True)
        print('LIVE CHECK PASSED',flush=True)
    finally:
        for p in peers:
            if 'name' in p:
                try:await call(p['http'],'leave',{'name':p['name']})
                except Exception:pass
            await p['http'].close()
        for p,log in processes:
            if p.returncode is None:p.terminate()
            await p.wait();log.close()

if __name__=='__main__':asyncio.run(main())
