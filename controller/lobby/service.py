#!/usr/bin/env python3
"""Guest arena lobby, private operator API and same-origin game gateway."""
import asyncio, collections, hashlib, json, os, pathlib, re, secrets, sqlite3, time
from aiohttp import web, ClientSession, ClientTimeout, WSMsgType
import sys
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import arena_ctl as core
ROOT = pathlib.Path(__file__).resolve().parents[2]
BUILDS = json.loads((pathlib.Path(__file__).with_name('builds.json')).read_text())
BUILD = {b['id']: b for b in BUILDS}
COOKIE = 'arena_guest'
LOADOUT_VERSION = 2
NAME = re.compile(r'^[A-Za-z]{2,12}$')

def public_origin(req):
    # Configure the external origin explicitly: do not trust arbitrary forwarded headers.
    return os.environ.get('ARENA_PUBLIC_ORIGIN', f'{req.scheme}://{req.host}').rstrip('/')

class Lobby:
    def __init__(self, db):
        self.db = sqlite3.connect(db)
        self.db.row_factory = sqlite3.Row
        self.db.executescript('''CREATE TABLE IF NOT EXISTS guests(token TEXT PRIMARY KEY, account INTEGER UNIQUE, username TEXT, password TEXT, created REAL);
        CREATE TABLE IF NOT EXISTS characters(account INTEGER, name TEXT UNIQUE COLLATE NOCASE, build INTEGER, prepared INTEGER DEFAULT 0, PRIMARY KEY(account,name));''')
        self.lock = asyncio.Lock()
        self.queues = {2: [], 3: []}
        self.members = {}
        self.limits = collections.defaultdict(collections.deque)
        self.games = {}
        self.last_start = {}
    async def sql(self, db, text):
        try: return await asyncio.to_thread(core.sql, db, text)
        except SystemExit as exc: raise web.HTTPServiceUnavailable(text='The character database is unavailable') from exc
    async def soap(self, text):
        try: return await asyncio.to_thread(core.soap, text)
        except SystemExit as exc: raise web.HTTPServiceUnavailable(text='World server is unavailable') from exc
    def guest(self, req):
        token = req.cookies.get(COOKIE, '')
        row = self.db.execute('SELECT * FROM guests WHERE token=?', (hashlib.sha256(token.encode()).hexdigest(),)).fetchone()
        if not row: raise web.HTTPUnauthorized(text='Guest session expired. Reload the lobby.')
        return dict(row)
    def owned(self, guest, name, prepared=False):
        if not isinstance(name,str) or not NAME.fullmatch(name): raise web.HTTPBadRequest(text='Use 2–12 letters for your character name.')
        row=self.db.execute('SELECT * FROM characters WHERE account=? AND name=? COLLATE NOCASE',(guest['account'],name)).fetchone()
        if not row or (prepared and not row['prepared']): raise web.HTTPForbidden(text='Choose and prepare your own character first.')
        return dict(row)
    async def online(self,g,name):
        result=await self.sql('characters',f"SELECT guid,class,online FROM characters WHERE account={g['account']} AND name='{name}';")
        return result.strip().split('\t') if result.strip() else []
    def public(self,g):
        chars=[dict(r) for r in self.db.execute('SELECT name,build,prepared FROM characters WHERE account=?',(g['account'],))]
        return {'characters':chars,'builds':BUILDS,'account':g['username']}
    async def session(self, req):
        try: g=self.guest(req); return web.json_response(self.public(g))
        except web.HTTPUnauthorized: pass
        async with self.lock:
            ip=(req.headers.get('Fly-Client-IP') if os.environ.get('FLY_APP_NAME') else None) or req.remote or 'local'; now=time.time(); bucket=self.limits[ip]
            while bucket and now-bucket[0]>3600: bucket.popleft()
            if len(bucket)>=20: raise web.HTTPTooManyRequests(text='Guest creation limit reached. Try again later.')
            bucket.append(now)
            user='G'+secrets.token_hex(7).upper(); password=secrets.token_hex(8).upper(); token=secrets.token_urlsafe(32)
            salt,verifier=core.srp6_verifier(user,password)
            await self.sql('auth',f"INSERT INTO account(username,salt,verifier,expansion) VALUES('{user}',UNHEX('{salt.hex()}'),UNHEX('{verifier.hex()}'),2);")
            account=int((await self.sql('auth',f"SELECT id FROM account WHERE username='{user}';")).strip())
            self.db.execute('INSERT INTO guests VALUES(?,?,?,?,?)',(hashlib.sha256(token.encode()).hexdigest(),account,user,password,now));self.db.commit()
            g={'account':account,'username':user}
            resp=web.json_response(self.public(g));resp.set_cookie(COOKIE,token,httponly=True,samesite='Strict',secure=public_origin(req).startswith('https://'),max_age=31536000,path='/');return resp
    async def credentials(self,req):
        g=self.guest(req)
        return web.json_response({'user':g['username'],'pass':g['password'],'host':'127.0.0.1','unattended':'1'})
    async def reserve(self,req):
        g=self.guest(req); data=await req.json(); build=BUILD.get(data.get('build'))
        if not build: raise web.HTTPBadRequest(text='Unknown build')
        async with self.lock:
            name=data.get('name','').strip().capitalize()
            if not name:
                name=secrets.choice(['Ash','Val','Thal','Nor','Zen','Kae','Rav'])+''.join(secrets.choice('aeiourstnl') for _ in range(6))
            if not NAME.fullmatch(name): raise web.HTTPBadRequest(text='Use 2–12 letters, without spaces or numbers.')
            old=self.db.execute('SELECT * FROM characters WHERE name=? COLLATE NOCASE',(name,)).fetchone()
            if old and old['account']==g['account'] and old['build']==build['id']:
                return web.json_response(dict(old))
            if old or (await self.sql('characters',f"SELECT guid FROM characters WHERE name='{name}';")).strip():
                raise web.HTTPConflict(text='That name is already taken.')
            count=self.db.execute('SELECT COUNT(*) FROM characters WHERE account=?',(g['account'],)).fetchone()[0]
            if count>=10: raise web.HTTPConflict(text='This guest already has ten characters. Select an existing character.')
            self.db.execute('INSERT INTO characters(account,name,build) VALUES(?,?,?)',(g['account'],name,build['id']));self.db.commit()
            return web.json_response({'name':name,'build':build['id'],'prepared':0})
    async def prepare(self,req):
        g=self.guest(req);data=await req.json();c=self.owned(g,data.get('name'))
        async with self.lock:
            row=await self.online(g,c['name'])
            if not row or row[2]!='1': raise web.HTTPConflict(text='Character is still connecting.')
            if int(row[1])!=BUILD[c['build']]['classId']: raise web.HTTPConflict(text='Character class does not match the chosen build.')
            if c['prepared'] != LOADOUT_VERSION:
                result=await self.soap(f"botarena lobby build {c['name']} {c['build']}")
                if 'LOBBY_OK' not in result: raise web.HTTPConflict(text=result[:500])
                self.db.execute('UPDATE characters SET prepared=? WHERE account=? AND name=?',(LOADOUT_VERSION,g['account'],c['name']));self.db.commit()
            return web.json_response({'ready':True})
    def cancel(self,account):
        self.members.pop(account,None)
        for q in self.queues.values(): q[:]=[x for x in q if x['account']!=account]
    async def play(self,req):
        g=self.guest(req);d=await req.json();c=self.owned(g,d.get('name'),True);size=d.get('size');mode=d.get('mode')
        if size not in (2,3) or mode not in ('watch','bots','players'): raise web.HTTPBadRequest(text='Choose 2v2 or 3v3 and a game mode.')
        arena=d.get('arena','random')
        if mode=='watch' and arena not in ('random','na','be','rl'): raise web.HTTPBadRequest(text='Choose a supported arena.')
        async with self.lock:
            if time.time()-self.last_start.get(g['account'],0)<5: raise web.HTTPTooManyRequests(text='Please wait a moment before starting another match.')
            self.last_start[g['account']]=time.time()
            self.cancel(g['account']);self.games.pop(g['account'],None)
            online=await self.online(g,c['name'])
            if not online or online[2]!='1': raise web.HTTPConflict(text='Character is not connected.')
            if mode=='players':
                entry={'account':g['account'],'name':c['name'],'size':size,'seen':time.time(),'joined':time.time()}
                self.members[g['account']]=entry;self.queues[size].append(entry)
                await self.matchmake(size)
                return web.json_response(self.status(g['account']))
            if mode=='bots':
                result=await self.soap(f"botarena lobby match {size} bots {c['name']}")
                if 'LOBBY_OK match' not in result: raise web.HTTPConflict(text=result[:500])
                match=int(re.search(r'LOBBY_OK match (\d+)',result)[1])
            else:
                comp='warrior:arms,paladin:holy' if size==2 else 'warrior:arms,dk:unholy,paladin:holy'
                # Serialize creation and resolve the newly allocated match from authoritative state.
                before=json.loads(await self.soap('botarena json'))
                result=await self.soap(f'botarena start {size} {arena} {comp} {comp}')
                after=json.loads(await self.soap('botarena json'))
                prev={m['id'] for m in before.get('matches',[])}
                new=[m for m in after.get('matches',[]) if m['id'] not in prev]
                if not new: raise web.HTTPConflict(text=result[:500])
                match=new[-1]['id']
                result=await self.soap(f"botarena spectate {c['name']} {match}")
                if 'now spectating' not in result: raise web.HTTPConflict(text=result[:500])
            self.games[g['account']]={'state':'playing','match':match,'mode':mode,'size':size}
            return web.json_response(self.games[g['account']])
    async def matchmake(self,size):
        q=self.queues[size];now=time.time()
        for x in list(q):
            if now-x['seen']>20: self.cancel(x['account'])
        if len(q)<size*2:return
        selected=q[:size*2]
        # Alternate healers between sides, then fill with damage dealers in arrival order.
        healers=[];damage=[]
        for x in selected:
            row=self.db.execute('SELECT build FROM characters WHERE account=? AND name=?',(x['account'],x['name'])).fetchone()
            (healers if BUILD[row[0]]['role']=='Healer' else damage).append(x)
        teams=[[],[]]
        for x in healers+damage:
            side=0 if len(teams[0])<=len(teams[1]) else 1;teams[side].append(x)
        names=' '.join(x['name'] for team in teams for x in team)
        result=await self.soap(f'botarena lobby match {size} players {names}')
        if 'LOBBY_OK match' not in result:
            for x in selected:
                self.cancel(x['account']);self.games[x['account']]={'state':'error','message':'A queued player became unavailable. Join the queue again.'}
            return
        match=int(re.search(r'LOBBY_OK match (\d+)',result)[1])
        for x in selected:
            self.cancel(x['account']);self.games[x['account']]={'state':'playing','mode':'players','size':size,'match':match}
    def status(self,account):
        if account in self.members:
            e=self.members[account];q=self.queues[e['size']]
            return {'state':'queued','size':e['size'],'waiting':len(q),'needed':2*e['size'],'seconds':int(time.time()-e['joined'])}
        return self.games.get(account,{'state':'idle'})
    async def queue_status(self,req):
        g=self.guest(req)
        async with self.lock:
            if g['account'] in self.members:
                entry=self.members[g['account']];entry['seen']=time.time();await self.matchmake(entry['size'])
            return web.json_response(self.status(g['account']))
    async def leave_game(self,req):
        g=self.guest(req);d=await req.json();c=self.owned(g,d.get('name'))
        async with self.lock:
            self.cancel(g['account']);self.games.pop(g['account'],None)
            action = "logout" if d.get("logout") is True else "leave"
            await self.soap(f"botarena lobby {action} {c['name']}")
        return web.json_response({'state':'idle'})
    async def leave_queue(self,req):
        g=self.guest(req)
        async with self.lock:self.cancel(g['account'])
        return web.json_response({'state':'idle'})
    async def recover(self,req):
        g=self.guest(req)
        async with self.lock:
            self.cancel(g['account']);self.games.pop(g['account'],None)
            # Resolve ownership from MySQL, never a client-supplied character name.
            names=await self.sql('characters',f"SELECT name FROM characters WHERE account={g['account']} AND online=1;")
            for name in names.splitlines():
                if not NAME.fullmatch(name):raise web.HTTPServiceUnavailable(text='Invalid character state')
                result=await self.soap(f'botarena lobby logout {name}')
                if 'LOBBY_OK' not in result and 'not online' not in result.lower():
                    raise web.HTTPServiceUnavailable(text='Waiting for character logout')
        return web.json_response({'state':'idle'})

@web.middleware
async def boundary(req,handler):
    if req.path.startswith('/api/'):
        if req.method not in ('GET','HEAD'):
            origin=req.headers.get('Origin')
            if origin and origin!=public_origin(req):return web.json_response({'error':'Cross-origin request refused'},status=403)
            if req.headers.get('Sec-Fetch-Site')=='cross-site':return web.json_response({'error':'Cross-origin request refused'},status=403)
        try: resp=await handler(req)
        except web.HTTPException as e: resp=web.json_response({'error':e.text},status=e.status)
        except (ValueError,TypeError,KeyError):resp=web.json_response({'error':'Invalid request'},status=400)
        except Exception:
            import logging;logging.exception('Lobby request failed')
            resp=web.json_response({'error':'The server could not complete the request. Try again.'},status=503)
        resp.headers['Cache-Control']='no-store';resp.headers['X-Content-Type-Options']='nosniff';return resp
    return await handler(req)

async def proxy(req):
    path=req.path_qs
    if path.startswith('/game/'):path=path[5:]
    if path.split('?',1)[0].startswith(('/data/', '/ws/')):
        req.app['lobby'].guest(req)
        if req.headers.get('Origin') and req.headers['Origin'] != public_origin(req):
            raise web.HTTPForbidden(text='Cross-origin game connection refused')
    url='http://127.0.0.1:8092'+path
    client=req.app['client']
    if req.headers.get('Upgrade','').lower()=='websocket':
        upstream=await client.ws_connect(url)
        ws=web.WebSocketResponse();await ws.prepare(req)
        async def forward(src,dest):
            async for msg in src:
                if msg.type==WSMsgType.BINARY:await dest.send_bytes(msg.data)
                elif msg.type==WSMsgType.TEXT:await dest.send_str(msg.data)
            await dest.close()
        await asyncio.gather(forward(ws,upstream),forward(upstream,ws));return ws
    async with client.request(req.method,url,headers={k:v for k,v in req.headers.items() if k.lower() in ('accept','accept-encoding','range','if-none-match')}) as upstream:
        resp=web.StreamResponse(status=upstream.status,headers={k:v for k,v in upstream.headers.items() if k.lower() not in ('transfer-encoding','connection','content-length')})
        await resp.prepare(req)
        async for chunk in upstream.content.iter_chunked(256*1024):await resp.write(chunk)
        return resp

async def lobby_index(req):
    return web.FileResponse(ROOT/'client/lobby/index.html')

async def health(req):
    try:
        for host, port in ((os.environ.get('ARENA_LOGIN_HOST','127.0.0.1'),3724), (os.environ.get('ARENA_WORLD_HOST','127.0.0.1'),8085), ('127.0.0.1',8092)):
            _, writer = await asyncio.wait_for(asyncio.open_connection(host, port), 2)
            writer.close()
            await writer.wait_closed()
        await asyncio.wait_for(req.app['lobby'].sql('auth', 'SELECT 1;'), 3)
    except Exception:
        return web.json_response({'ready':False}, status=503)
    return web.json_response({'ready':True})

async def resources(app):
    async with ClientSession(auto_decompress=False,timeout=ClientTimeout(total=None,connect=10)) as client:
        app['client']=client;yield
    app['lobby'].db.close()

def make_app(db):
    app=web.Application(middlewares=[boundary],client_max_size=16384);lobby=Lobby(db);app['lobby']=lobby;app.cleanup_ctx.append(resources)
    for method,path,handler in [('POST','session',lobby.session),('GET','credentials',lobby.credentials),('POST','characters',lobby.reserve),('POST','prepare',lobby.prepare),('POST','play',lobby.play),('POST','leave',lobby.leave_game),('GET','queue',lobby.queue_status),('DELETE','queue',lobby.leave_queue)]:app.router.add_route(method,'/api/'+path,handler)
    app.router.add_get('/',lobby_index)
    app.router.add_get('/healthz',health)
    app.router.add_post('/api/recover',lobby.recover)
    app.router.add_static('/lobby/',ROOT/'client/lobby',show_index=False)
    app.router.add_route('*','/{path:.*}',proxy)
    return app

if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser();parser.add_argument('--bind',default='127.0.0.1');parser.add_argument('--port',type=int,default=8090);args=parser.parse_args()
    data=pathlib.Path(os.environ.get('ARENA_LOBBY_HOME',ROOT/'artifacts/lobby/state'));data.mkdir(parents=True,exist_ok=True,mode=0o700)
    os.umask(0o077)
    web.run_app(make_app(data/'guests.sqlite'),host=args.bind,port=args.port,access_log=None)
