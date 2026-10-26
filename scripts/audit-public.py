#!/usr/bin/env python3
"""Audit tracked publication files. This complements, not replaces, manual review."""
import pathlib, re, subprocess, sys
root=pathlib.Path(__file__).resolve().parents[1]
files=subprocess.check_output(['git','ls-files','-z'],cwd=root).decode().split('\0')
patterns=[r'/Users/[A-Za-z0-9_.-]+/',r'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----',r'gh[pousr]_[A-Za-z0-9]{30,}',r'github_pat_[A-Za-z0-9_]{40,}',r'AKIA[0-9A-Z]{16}']
errors=[]
for name in filter(None,files):
    p=root/name
    if not p.is_file(): continue
    if name.startswith(('artifacts/','server/','client/benilla-src/')) or p.suffix.lower() in ('.mpq','.dbc','.sqlite','.wasm','.pem','.key') or (name.startswith('.env') and name!='.env.example'):
        errors.append(name+': prohibited publication file')
    text=p.read_text(errors='replace')
    for pattern in patterns:
        if re.search(pattern,text): errors.append(name+': private path/key pattern detected')
if errors: print('\n'.join(errors));sys.exit(1)
print(f'Publication audit passed for {len(files)-1} tracked files; manually review identifiers and patch contents too.')
