import importlib.util
import pathlib
import unittest

path = pathlib.Path(__file__).resolve().parents[1] / 'scripts/check-pvp-requests.py'
spec = importlib.util.spec_from_file_location('pvp_requests', path)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class RequestAuditTests(unittest.TestCase):
    def test_case_and_separator_normalization_and_optional_misses(self):
        requested, missing = module.missing_files(
            {'files': [{'name': r'World\Maps\PVPZone05\PVPZone05.wdt'}]},
            [{'world/maps/pvpzone05/pvpzone05.wdt': 200,
              'Interface/Optional.blp': 404, '__index': 200}])
        self.assertEqual(len(requested), 1)
        self.assertEqual(missing, set())

    def test_successfully_loaded_original_asset_must_be_present(self):
        _, missing = module.missing_files({'files': []}, [{'Item/Sword.m2': 200}])
        self.assertEqual(missing, {'item/sword.m2'})
