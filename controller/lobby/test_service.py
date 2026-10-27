import unittest, tempfile, pathlib, time, sys
from unittest.mock import patch
sys.path.insert(0,str(pathlib.Path(__file__).parent))
from service import Lobby, make_app, BUILDS, random_character_name
from aiohttp import web, CookieJar
from aiohttp.test_utils import TestClient, TestServer

class QueueTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.lobby=Lobby(':memory:');self.calls=[]
        async def soap(command):self.calls.append(command);return 'LOBBY_OK match 42'
        self.lobby.soap=soap
    def add(self, account,size,seen=None):
        name='Player'+chr(65+account)
        self.lobby.db.execute('INSERT INTO characters VALUES(?,?,?,1)',(account,name,1))
        e={'account':account,'name':name,'size':size,'seen':seen or time.time(),'joined':time.time()}
        self.lobby.members[account]=e;self.lobby.queues[size].append(e)
    async def test_two_players_are_not_a_two_v_two(self):
        for i in range(3):self.add(i,2)
        await self.lobby.matchmake(2)
        self.assertEqual(self.calls,[]);self.assertEqual(self.lobby.status(0)['needed'],4)
        self.add(3,2);await self.lobby.matchmake(2)
        self.assertEqual(len(self.calls),1);self.assertIn('2 players',self.calls[0]);self.assertEqual(len(self.calls[0].split()),9)
        self.assertTrue(all(self.lobby.status(i)['state']=='playing' for i in range(4)))
    async def test_three_v_three_is_separate_and_requires_six(self):
        for i in range(5):self.add(i,3)
        self.add(6,2);await self.lobby.matchmake(3);self.assertEqual(self.calls,[])
        self.add(5,3);await self.lobby.matchmake(3)
        self.assertEqual(len(self.calls),1);self.assertEqual(self.lobby.status(6)['state'],'queued')
    async def test_stale_players_do_not_start_matches(self):
        for i in range(4):self.add(i,2, time.time()-30 if i==0 else None)
        await self.lobby.matchmake(2);self.assertEqual(self.calls,[]);self.assertNotIn(0,self.lobby.members)
    async def test_cancel_removes_membership(self):
        self.add(1,2);self.lobby.cancel(1);self.assertEqual(self.lobby.status(1)['state'],'idle');self.assertEqual(self.lobby.queues[2],[])
    async def test_failed_start_is_not_reported_as_playing(self):
        for i in range(4):self.add(i,2)
        async def fail(_):return 'LOBBY_ERROR unavailable'
        self.lobby.soap=fail;await self.lobby.matchmake(2)
        self.assertTrue(all(self.lobby.status(i)['state']=='error' for i in range(4)))
    async def test_cannot_prepare_someone_elses_character(self):
        self.add(1,2)
        with self.assertRaises(web.HTTPForbidden):self.lobby.owned({'account':2},'PlayerB')
    async def test_name_injection_is_rejected(self):
        with self.assertRaises(web.HTTPBadRequest):self.lobby.owned({'account':1},"x'; DROP TABLE characters")

    async def test_friend_teams_are_isolated_and_consumed_once(self):
        def entry(account,size=2):return {'account':account,'name':'Player'+chr(65+account),'size':size,'seen':time.time()}
        self.lobby.join_team('1234ABCD',entry(0))
        self.lobby.join_team('1234ABCD',entry(0))
        await self.lobby.match_team('1234ABCD');self.assertEqual(self.calls,[])
        with self.assertRaises(web.HTTPConflict):self.lobby.join_team('1234ABCD',entry(1,3))
        self.lobby.join_team('ABCD1234',entry(2))
        self.lobby.join_team('1234ABCD',entry(1))
        await self.lobby.match_team('1234ABCD')
        self.assertEqual(self.calls,['botarena lobby match 2 bots PlayerA PlayerB'])
        self.assertEqual(self.lobby.status(0),self.lobby.status(1))
        self.assertEqual(self.lobby.status(2)['waiting'],1)
        with self.assertRaises(web.HTTPConflict):self.lobby.join_team('1234ABCD',entry(3))
        await self.lobby.match_team('1234ABCD');self.assertEqual(len(self.calls),1)
        self.lobby.cancel(2);self.assertEqual(self.lobby.status(2)['state'],'idle')
    async def test_failed_friend_start_does_not_retry(self):
        for i in range(2):self.lobby.join_team('1234ABCD',{'account':i,'name':'Player'+chr(65+i),'size':3,'seen':time.time()})
        async def fail(_):raise web.HTTPServiceUnavailable()
        self.lobby.soap=fail
        await self.lobby.match_team('1234ABCD')
        self.assertTrue(all(self.lobby.status(i)['state']=='error' for i in range(2)))
        self.assertIn('1234ABCD',self.lobby.used_codes)

class HttpTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.client=TestClient(TestServer(make_app(':memory:')),cookie_jar=CookieJar(unsafe=True));await self.client.start_server()
    async def asyncTearDown(self):await self.client.close()
    async def test_no_session_cannot_fetch_credentials(self):
        r=await self.client.get('/api/credentials');self.assertEqual(r.status,401);self.assertEqual(r.headers['Cache-Control'],'no-store')
    async def test_cross_origin_mutation_rejected(self):
        r=await self.client.post('/api/session',headers={'Origin':'https://other.invalid'});self.assertEqual(r.status,403)
    async def test_private_gateway_requires_guest(self):
        for path in ('/data/__index', '/game/data/__index', '/ws/8085', '/game/ws/3724', '/%64ata/__index', '/game/%77s/8085'):
            r=await self.client.get(path)
            self.assertEqual(r.status,401,path)
    async def test_https_origin_works_behind_fly_proxy(self):
        lobby=self.client.server.app['lobby']
        async def sql(db, query):
            return '42' if query.startswith('SELECT id') else ''
        lobby.sql=sql
        with patch.dict('os.environ', {'ARENA_PUBLIC_ORIGIN':'https://arena.example'}):
            r=await self.client.post('/api/session',headers={'Origin':'https://arena.example'})
            self.assertEqual(r.status,200)
            self.assertTrue(r.cookies['arena_guest']['secure'])
            r=await self.client.post('/api/session',headers={'Origin':'https://evil.example'})
            self.assertEqual(r.status,403)
    async def test_cross_origin_websocket_refused(self):
        self.client.server.app['lobby'].guest=lambda req:{'account':1}
        with patch.dict('os.environ', {'ARENA_PUBLIC_ORIGIN':'https://arena.example'}):
            r=await self.client.get('/ws/8085',headers={'Origin':'https://evil.example'})
            self.assertEqual(r.status,403)
    async def test_return_logs_out_only_the_owned_character(self):
        lobby=self.client.server.app['lobby'];calls=[]
        lobby.guest=lambda req:{'account':1}
        lobby.db.execute('INSERT INTO characters VALUES(1,"Ownhero",1,1)')
        lobby.db.execute('INSERT INTO characters VALUES(2,"Otherhero",1,1)')
        async def soap(command):calls.append(command);return 'LOBBY_OK left'
        lobby.soap=soap
        r=await self.client.post('/api/leave',json={'name':'Otherhero','logout':True})
        self.assertEqual(r.status,403);self.assertEqual(calls,[])
        r=await self.client.post('/api/leave',json={'name':'Ownhero','logout':True})
        self.assertEqual(r.status,200);self.assertEqual(calls,['botarena lobby logout Ownhero'])
    async def test_recovery_resolves_online_characters_from_guest_account(self):
        lobby=self.client.server.app['lobby'];lobby.guest=lambda req:{'account':7};calls=[]
        async def sql(db,query):
            self.assertIn('account=7 AND online=1',query)
            return 'Ownhero\n'
        async def soap(command):calls.append(command);return 'LOBBY_OK left'
        lobby.sql=sql;lobby.soap=soap
        lobby.members[7]={'account':7};lobby.queues[2]=[{'account':7},{'account':8}]
        lobby.games[7]={'state':'playing'}
        r=await self.client.post('/api/recover',json={'name':'Otherhero'})
        self.assertEqual(r.status,200);self.assertEqual(calls,['botarena lobby logout Ownhero'])
        self.assertNotIn(7,lobby.members);self.assertNotIn(7,lobby.games)
        self.assertEqual(lobby.queues[2],[{'account':8}])
    async def test_recovery_requires_session(self):
        r=await self.client.post('/api/recover');self.assertEqual(r.status,401)
    async def test_spectator_arena_is_a_bounded_choice(self):
        lobby=self.client.server.app['lobby'];lobby.guest=lambda req:{'account':1}
        lobby.db.execute('INSERT INTO characters VALUES(1,"Ownhero",1,1)')
        r=await self.client.post('/api/play',json={'name':'Ownhero','mode':'watch','size':2,'arena':'na; server shutdown'})
        self.assertEqual(r.status,400)
    async def test_graphical_trees_match_the_playable_build(self):
        for b in BUILDS:
            self.assertEqual(len(b['talentTrees']),3)
            nodes=[n for tree in b['talentTrees'] for n in tree['nodes']]
            self.assertEqual(sum(n['rank'] for n in nodes),71)
            self.assertTrue(all(0<=n['rank']<=n['maxRank'] for n in nodes))
            self.assertEqual({n['id']:n['rank'] for n in nodes if n['rank']},{n['id']:n['rank'] for n in b['talentSummary']})
            self.assertTrue(all(g.get('icon') for g in b['gear']))
    async def test_native_tooltip_catalog_is_complete(self):
        for b in BUILDS:
            self.assertEqual(b['tooltipLevel'],80)
            for item in b['gear']:
                self.assertGreaterEqual(len(item['tooltip']),2)
                self.assertIn(item['inventorySlot'],range(1,20))
            for entry in b['glyphs']+[n for tree in b['talentTrees'] for n in tree['nodes']]:
                self.assertGreaterEqual(len(entry['tooltip']),3)
        sword=BUILDS[0]['gear'][0]['tooltip']
        text='\n'.join(line[0] for line in sword)
        self.assertIn('attack power by 334',text)
        self.assertIn('critical strike rating by 106',text)
        self.assertIn('resilience rating by 122',text)
        self.assertIn('+20 Strength',text)
        self.assertIn('Socket Bonus: +12 Attack Power',text)

    async def test_catalog_has_ten_classes_and_valid_point_totals(self):
        self.assertEqual(len({b['classId'] for b in BUILDS}),10)
        for b in BUILDS:self.assertEqual(len(b['talents']),71);self.assertEqual(len(b['glyphs']),6);self.assertEqual(sum(g['minor'] for g in b['glyphs']),3)

if __name__=='__main__':unittest.main()


class NameTests(unittest.IsolatedAsyncioTestCase):
    def test_generated_names_avoid_triples_at_prefix_boundary(self):
        def pick(choices):
            if 'Zen' in choices: return 'Zen'
            return 'a' if choices == 'aeiou' else 'n'
        with patch('service.secrets.choice', side_effect=pick):
            name = random_character_name()
        self.assertEqual(name, 'Zenananan')
        self.assertNotRegex(name.lower(), r'(.)\1\1')

    async def test_typed_triples_are_rejected_before_character_reservation(self):
        lobby = Lobby(':memory:')
        lobby.guest = lambda request: {'account': 1}
        class Request:
            async def json(self): return {'build': BUILDS[0]['id'], 'name': 'Zennnatei'}
        try:
            with self.assertRaises(web.HTTPBadRequest):
                await lobby.reserve(Request())
            self.assertEqual(lobby.db.execute('SELECT COUNT(*) FROM characters').fetchone()[0], 0)
        finally:
            lobby.db.close()
