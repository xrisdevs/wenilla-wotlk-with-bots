import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location('closure', Path(__file__).resolve().parents[1]/'scripts/check-pvp-closure.py')
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


class ClosureAuditTests(unittest.TestCase):
    def test_rejects_lost_dynamic_assets_changed_bytes_and_trace_gaps(self):
        entry = {'name': 'Character/Human/Human.m2', 'size': 10, 'sha256': 'original'}
        old = {'maps': ['arena'], 'files': [entry]}
        removed = {'maps': ['arena'], 'files': []}
        self.assertTrue(m.audit(old, removed, {'kept': {}}, []))
        changed = {'maps': ['arena'], 'files': [{**entry, 'sha256': 'changed'}]}
        self.assertTrue(m.audit(old, changed, {'kept': {'character/human/human.m2': 'root'}}, []))
        self.assertTrue(m.audit(old, old, {'kept': {'character/human/human.m2': 'root'}}, [{'World/needed.m2': 200}]))
        self.assertFalse(m.audit(old, old, {'kept': {'character/human/human.m2': 'root'}}, [{'CHARACTER\\Human\\Human.m2': 200, 'optional': 404}]))
