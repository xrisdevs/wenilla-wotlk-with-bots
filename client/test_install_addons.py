import hashlib
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

spec = importlib.util.spec_from_file_location('install_addons', Path(__file__).with_name('install-addons.py'))
installer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(installer)


class InstallerTests(unittest.TestCase):
    def run_archive(self, entries, expected_hash=None):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'addons').mkdir()
            buffer = io.BytesIO()
            with zipfile.ZipFile(buffer, 'w') as archive:
                for name, text in entries.items():
                    archive.writestr(name, text)
            data = buffer.getvalue()
            manifest = [{'name':'Test', 'url':'https://invalid.example/test.zip',
                         'sha256':expected_hash or hashlib.sha256(data).hexdigest(),
                         'folders':{'Test':'Test'}}]
            (root / 'addons/pvp-addons.json').write_text(json.dumps(manifest))
            for name in ('ArenaCompat', 'ArenaPvP', 'BotArenaSpectator'):
                (root / 'addons' / name).mkdir()
                (root / 'addons' / name / (name+'.toc')).write_text('## Interface: 30300')
            with patch.object(installer, 'ROOT', root), patch.object(installer.urllib.request, 'urlopen', return_value=io.BytesIO(data)):
                names = installer.install(root / 'installed')
                self.assertEqual(json.loads((root/'installed/index.json').read_text()), names)
                self.assertTrue((root/'installed/Test/Test.toc').is_file())
                return names

    def test_verified_archive_installs_and_indexes(self):
        self.assertIn('Test', self.run_archive({'Test/Test.toc':'## Interface: 30300\n'}))

    def test_checksum_failure_does_not_install(self):
        with self.assertRaisesRegex(ValueError, 'Checksum mismatch'):
            self.run_archive({'Test/Test.toc':'## Interface: 30300'}, '0'*64)

    def test_traversal_rejected_even_with_matching_checksum(self):
        with self.assertRaisesRegex(ValueError, 'Unsafe addon'):
            self.run_archive({'../escaped':'bad', 'Test/Test.toc':'## Interface: 30300'})

    def test_missing_toc_rejected(self):
        with self.assertRaisesRegex(ValueError, 'Missing addon TOC'):
            self.run_archive({'Test/script.lua':'return true'})


if __name__ == '__main__':
    unittest.main()
