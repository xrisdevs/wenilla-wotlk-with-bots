#!/usr/bin/env python3
"""Install checksum-pinned WotLK addons without vendoring third-party archives."""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import shutil
import tempfile
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def adapt(folder, name):
    # Explicit compatibility edits, applied only to disposable installed copies.
    toc = folder / (name + '.toc')
    text = toc.read_text(encoding='utf-8-sig')
    text = re.sub(r'(## Interface:) 30000', r'\1 30300', text)
    text = re.sub(r'^## LoadOnDemand:.*$', '', text, flags=re.M)
    if re.search(r'^## Dependencies:', text, flags=re.M):
        text = re.sub(r'^(## Dependencies:.*)$', r'\1, ArenaCompat', text, flags=re.M)
    else:
        text += '\n## Dependencies: ArenaCompat\n'
    if name in ('Gladius', 'SoundAlerter', 'OmniCC_Config'):
        text += '## LoadOnDemand: 1\n'
    toc.write_text(text)
    if name == 'Gladius':
        p = folder / 'embeds.xml'
        text = p.read_text()
        start = text.index('    <Script')
        end = text.index('    <Include file="libs\\AceAddon')
        text = text[:start] + '\n'.join([
            '    <Script file="libs/LibStub/LibStub.lua"/>',
            '    <Script file="libs/CallBackHandler-1.0/CallbackHandler-1.0.lua"/>',
            '    <Script file="libs/LibDataBroker-1.1/LibDataBroker-1.1.lua"/>',
            '    <Script file="libs/LibDBIcon-1.0/LibDBIcon-1.0.lua"/>', '']) + text[end:]
        p.write_text(text)
        # Older Lua parser builds mishandle multibyte literals in this embedded lib.
        p = folder / 'libs/LibSharedMedia-3.0/LibSharedMedia-3.0/LibSharedMedia-3.0.lua'
        text = p.read_text()
        text = re.sub(r'"[^"\n]*"', lambda m: ''.join(c if ord(c)<128 else ''.join('\\%03d'%b for b in c.encode()) for c in m[0]), text)
        p.write_text(text)
    if name == 'Quartz':
        p = folder / 'Quartz.lua'
        text = p.read_text().replace('modules = { ["*"] = true }', 'modules = { ["*"] = true, Buff=false, Flight=false, Swing=false, Timer=false, Mirror=false, Pet=false, Tradeskill=false, GCD=false, Range=false }')
        p.write_text(text)
        p = folder / 'CastBarTemplate.lua'
        text = p.read_text().replace('self.Bar:GetStatusBarTexture():SetHorizTile(false)', 'if self.Bar:GetStatusBarTexture().SetHorizTile then self.Bar:GetStatusBarTexture():SetHorizTile(false) end').replace('self.Bar:GetStatusBarTexture():SetVertTile(false)', 'if self.Bar:GetStatusBarTexture().SetVertTile then self.Bar:GetStatusBarTexture():SetVertTile(false) end')
        p.write_text(text)
        # These optional channel/swing tick tables are built before spell data exists.
        # Numeric fallbacks keep the module usable; no fabricated spell names/timers.
        for module in ('Player', 'Swing'):
            p = folder / 'modules' / (module + '.lua')
            text = re.sub(r'\[GetSpellInfo\((\d+)\)\]', r'[GetSpellInfo(\1) or \1]', p.read_text())
            p.write_text(text)
    if name == 'InterruptBar':
        p = folder / 'InterruptBar.lua'
        text = p.read_text().replace('local spellids = {', 'local spellids = {[57994] = 6, ')
        text = text.replace('cd.noomnicc = true', 'cd.noomnicc = true; cd.noCooldownCount = true')
        text = text.replace('bar = CreateFrame("Frame", nil, UIParent)', 'bar = CreateFrame("Frame", "ArenaInterruptBar", UIParent)')
        text = text.replace('local order = {6552,', 'local order = {57994, 6552,')
        # Expose a real refresh operation so defaults apply on the very first login.
        text = text.replace('local function InterruptBar_UpdateText', 'function ArenaInterruptBarRefresh() InterruptBar_UpdateBar(); bar:ClearAllPoints(); InterruptBar_LoadPosition() end\n\nlocal function InterruptBar_UpdateText')
        # Only this self-contained addon needs delayed construction. Initialize its
        # actual frames when GetSpellInfo is ready, instead of changing game APIs.
        text = text.replace('frame:RegisterEvent("VARIABLES_LOADED")', 'InterruptBar_OnLoad(frame)')
        text = ('local ready = CreateFrame("Frame")\nready:SetScript("OnUpdate", function(self)\n'
                'if not GetSpellInfo(6552) then return end\nself:SetScript("OnUpdate", nil)\n' + text + '\nend)\n')
        p.write_text(text)
    if name == 'LoseControl':
        p = folder / 'LoseControl.lua'
        text = p.read_text().replace('function LoseControl:UNIT_AURA(unitId)', 'function LoseControl:UNIT_AURA(unitId)\n    if not self.frame then return end')
        p.write_text(text)
    for p in folder.rglob('*.lua'):
        text = p.read_text(encoding='utf-8-sig', errors='surrogateescape')
        text = re.sub(r'"[^"\n]*"', lambda m: ''.join(c if ord(c)<128 else ''.join('\\%03d'%b for b in c.encode('utf-8', errors='surrogateescape')) for c in m[0]), text)
        p.write_text(text, encoding='utf-8', errors='surrogateescape')


def install(destination, cache=None):
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=True)
    cache = Path(cache or ROOT / 'artifacts/pvp-addons')
    cache.mkdir(parents=True, exist_ok=True)
    names = []
    for package in json.loads((ROOT / 'addons/pvp-addons.json').read_text()):
        archive = cache / (package['name'] + '.zip')
        if not archive.exists() or hashlib.sha256(archive.read_bytes()).hexdigest() != package['sha256']:
            with urllib.request.urlopen(package['url'], timeout=120) as response:
                data = response.read(128 * 1024 * 1024 + 1)
            if hashlib.sha256(data).hexdigest() != package['sha256']:
                raise ValueError('Checksum mismatch: ' + package['name'])
            archive.write_bytes(data)
        with tempfile.TemporaryDirectory(dir=destination, prefix='.install-') as temporary:
            staging = Path(temporary)
            with zipfile.ZipFile(archive) as z:
                if sum(i.file_size for i in z.infolist()) > 256 * 1024 * 1024:
                    raise ValueError('Oversized addon archive')
                for info in z.infolist():
                    path = PurePosixPath(info.filename)
                    if path.is_absolute() or '..' in path.parts or '\\' in info.filename or (info.external_attr >> 16) & 0o170000 == 0o120000:
                        raise ValueError('Unsafe addon archive member')
                z.extractall(staging)
            for name, source in package['folders'].items():
                folder = staging / source
                if not (folder / (name + '.toc')).is_file():
                    raise ValueError('Missing addon TOC: ' + name)
                # Installed copies retain all bundled licenses and notices.
                if (destination / name).exists():
                    shutil.rmtree(destination / name)
                shutil.copytree(folder, destination / name)
                for notice in folder.parent.glob('*'):
                    if notice.is_file() and notice.name.lower().startswith(('license', 'copying')):
                        shutil.copy2(notice, destination / name / notice.name)
                adapt(destination / name, name)
                names.append(name)
    for name in ('ArenaCompat', 'BotArenaSpectator', 'ArenaPvP'):
        shutil.copytree(ROOT / 'addons' / name, destination / name, dirs_exist_ok=True)
        names.append(name)
    (destination / 'index.json').write_text(json.dumps(names) + '\n')
    return names


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('destination', type=Path)
    parser.add_argument('--cache', type=Path)
    args = parser.parse_args()
    print('Installed: ' + ', '.join(install(args.destination, args.cache)))
