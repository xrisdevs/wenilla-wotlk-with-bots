import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('fetch_tdb', Path(__file__).resolve().parents[1] / 'docker/scripts/fetch-tdb.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class TdbCacheTests(unittest.TestCase):
    def test_verified_cache_works_without_network_or_extractor(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            sql = root / 'world.sql'
            sql.write_bytes(b'world seed')
            manifest = root / 'manifest.json'
            manifest.write_text(json.dumps({'release': 'test', 'archive': 'world.7z', 'sql': 'world.sql',
                                           'sql_sha256': hashlib.sha256(sql.read_bytes()).hexdigest()}))
            with patch.object(module.urllib.request, 'urlopen', side_effect=AssertionError('network used')), patch.object(module.subprocess, 'run', side_effect=AssertionError('extractor used')):
                module.fetch(manifest, root)
            self.assertEqual(sql.read_bytes(), b'world seed')

    def test_bad_cached_sql_is_rejected_without_replacing_it(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            sql = root / 'world.sql'
            sql.write_bytes(b'corrupted')
            manifest = root / 'manifest.json'
            manifest.write_text(json.dumps({'release': 'test', 'archive': 'world.7z', 'sql': 'world.sql', 'sql_sha256': '0' * 64}))
            with self.assertRaisesRegex(ValueError, 'Checksum mismatch'):
                module.fetch(manifest, root)
            self.assertEqual(sql.read_bytes(), b'corrupted')

    def test_bad_download_never_becomes_a_cached_archive_or_sql(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            payload = root / 'upstream.7z'
            payload.write_bytes(b'corrupted download')
            manifest = root / 'manifest.json'
            manifest.write_text(json.dumps({'release': 'test', 'archive': 'world.7z', 'sql': 'world.sql',
                                           'url': payload.as_uri(), 'archive_sha256': '0' * 64, 'sql_sha256': '0' * 64}))
            cache = root / 'cache'
            with self.assertRaisesRegex(ValueError, 'Checksum mismatch'):
                module.fetch(manifest, cache)
            self.assertEqual(list(cache.iterdir()), [])


if __name__ == '__main__':
    unittest.main()
