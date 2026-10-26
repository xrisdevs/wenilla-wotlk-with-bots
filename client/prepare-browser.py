#!/usr/bin/env python3
"""Stage display settings and an empty addon manifest for the standard game UI."""
import importlib.util, json, pathlib, shutil, sys
ROOT = pathlib.Path(__file__).resolve().parents[1]
def prepare(source):
    spec = importlib.util.spec_from_file_location('display', ROOT / 'client/configure-display.py')
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    web = source / 'web'
    (web / 'addons').mkdir(exist_ok=True)
    (web / 'addons/index.json').write_text('[]')
    profile = dict(module.PROFILE); profile['gxMultisample'] = '4'
    config = '[cvars]\n' + ''.join(f'{key} = {json.dumps(value)}\n' for key,value in profile.items())
    (web / 'display.js').write_text("localStorage.setItem('benilla:/benilla-config/config.toml', " + json.dumps(config) + ");\n" + (ROOT / 'client/display.js').read_text())
if __name__ == '__main__': prepare(pathlib.Path(sys.argv[1]).resolve())
