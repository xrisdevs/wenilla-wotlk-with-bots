#!/usr/bin/env python3
"""Check every uploaded asset against a local SHA-256 manifest before activation."""
import concurrent.futures, hashlib, json, pathlib, sys
root, manifest = pathlib.Path(sys.argv[1]), json.loads(pathlib.Path(sys.argv[2]).read_text())
def verify(entry):
    name, expected = entry
    path = root / name
    assert path.is_relative_to(root), name
    assert path.is_file() and path.stat().st_size == expected['size'], f'Missing or truncated: {name}'
    with path.open('rb') as stream:
        assert hashlib.file_digest(stream, 'sha256').hexdigest() == expected['sha256'], f'Checksum mismatch: {name}'
    print(f'Verified {name}', flush=True)
with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
    list(pool.map(verify, manifest.items()))
(root / '.ready').touch()
print(f'Verified {len(manifest)} assets ({sum(v["size"] for v in manifest.values())} bytes)', flush=True)
