#!/usr/bin/env python3
"""Package our spectator addon and enforce the shared display profile in the browser page."""
import importlib.util
import json
import pathlib
import re
import shutil
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]

def prepare(source):
    spec = importlib.util.spec_from_file_location('display', ROOT / 'client/configure-display.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    web = source / 'web'
    addons = web / 'addons'
    addons.mkdir(exist_ok=True)
    addon_spec = importlib.util.spec_from_file_location('install_addons', ROOT / 'client/install-addons.py')
    addon_module = importlib.util.module_from_spec(addon_spec)
    addon_spec.loader.exec_module(addon_module)
    addon_module.install(addons)
    profile = dict(module.PROFILE)
    profile['realmName'] = 'Trinity'
    profile['gxMultisample'] = '4'  # WebGPU's supported multisample count.
    config = '[cvars]\n' + ''.join(f'{key} = {json.dumps(value)}\n' for key, value in profile.items())
    script = "// Shared maximum-quality display settings.\nlocalStorage.setItem('benilla:/benilla-config/config.toml', " + json.dumps(config) + ");\n" + (ROOT / 'client/lobby/display.js').read_text()
    (web / 'arena-display.js').write_text(script)
    shutil.copyfile(ROOT / 'client/lobby/game-session.js', web / 'game-session.js')
    page = (web / 'index.html').read_text()
    if 'connectLobby' not in page:
        page = page.replace('  const w = await boot(init);', "  const { connectLobby } = await import('./game-session.js');\n  await connectLobby();\n  const w = await boot(init);")
    if 'arena-display.js' not in page:
        page = page.replace('<title>wenilla</title>', '<title>WoW Arena Bots</title>\n<script src="./arena-display.js"></script>')
        page = page.replace('#benilla { display: block; width: 100vw; height: 100vh; }', '#benilla { display: block; width: min(100vw, 177.7778vh); height: min(100vh, 56.25vw); margin: auto; }\n  body { display: flex; align-items: center; justify-content: center; }')
    page = re.sub(r'#benilla \{[^}]*\}', '#benilla { display: block; width: calc(var(--arena-width, 1920px) / var(--arena-dpr, 1)) !important; height: calc(var(--arena-height, 1080px) / var(--arena-dpr, 1)) !important; position: absolute; left: 50%; top: 50%; transform: translate(-50%, -50%) scale(var(--arena-scale, 1)); transform-origin: center; }', page)
    (web / 'index.html').write_text(page)

if __name__ == '__main__':
    prepare(pathlib.Path(sys.argv[1]).resolve())
