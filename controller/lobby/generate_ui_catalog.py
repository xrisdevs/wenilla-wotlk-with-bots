#!/usr/bin/env python3
"""Enrich the preset catalog from local WotLK DBCs. Game assets remain outside git."""
import argparse,gzip,json,pathlib,struct
p=argparse.ArgumentParser();p.add_argument('--dbc-dir',type=pathlib.Path,default=pathlib.Path('artifacts/lobby/dbc'));p.add_argument('--catalog',type=pathlib.Path,default=pathlib.Path(__file__).with_name('builds.json'));a=p.parse_args()
def dbc(name):
 b=(a.dbc_dir/(name+'.dbc')).read_bytes()
 if b[:2]==b'\x1f\x8b':b=gzip.decompress(b)
 magic,n,f,size,_=struct.unpack_from('<4s4I',b);assert magic==b'WDBC'
 strings=b[20+n*size:]
 return [struct.unpack_from('<'+'I'*f,b,20+i*size) for i in range(n)],lambda x:strings[x:strings.index(b'\0',x)].decode()
sp,ss=dbc('Spell');sp={r[0]:r for r in sp};icons,ist=dbc('SpellIcon');icons={r[0]:ist(r[1]).replace('\\\\','\\') for r in icons};items,it=dbc('ItemDisplayInfo');items={r[0]:it(r[5]) for r in items};tabs,ts=dbc('TalentTab');tal,_=dbc('Talent');glyph,_=dbc('GlyphProperties');glyph={g[0]:g[1] for g in glyph}
slots={0:15,1:16,2:17,3:0,4:2,5:4,6:5,7:6,8:7,9:8,10:9,11:14,12:3,13:10,14:11,15:12,16:13,17:1}
bs=json.loads(a.catalog.read_text())
for b in bs:
 ranks={t['id']:t['rank'] for t in b['talentSummary']};b['talentTrees']=[]
 for tab in sorted([t for t in tabs if t[20]==1<<(b['classId']-1) and not t[21]],key=lambda t:t[22]):
  nodes=[]
  for t in sorted([t for t in tal if t[1]==tab[0]],key=lambda t:(t[2],t[3])):
   spell=sp[t[4]]
   nodes.append(dict(id=t[0],name=ss(spell[136]),row=t[2],column=t[3],rank=ranks.get(t[0],0),maxRank=sum(bool(x) for x in t[4:9]),icon=icons.get(spell[133],'Interface\\Icons\\INV_Misc_QuestionMark'),prerequisite=t[13],prerequisiteRank=t[16]+1 if t[13] else 0))
  b['talentTrees'].append(dict(name=ts(tab[1]),background=ts(tab[23]),points=sum(t['rank'] for t in nodes),nodes=nodes))
 for g in b['gear']:
  icon=items.get(b['previewEquipment'][slots[g['slot']]][0],'INV_Misc_QuestionMark');g['icon']='Interface\\Icons\\'+icon
 for g in b['glyphs']:g['icon']=icons.get(sp[glyph[g['id']]][133],'Interface\\Icons\\INV_Misc_QuestionMark')
a.catalog.write_text(json.dumps(bs,indent=2)+'\n')
print('Enriched',len(bs),'presets with gear icons and all three talent trees')
