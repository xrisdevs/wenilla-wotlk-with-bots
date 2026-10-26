import importlib.util
from pathlib import Path
import struct
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('trim_pvp', ROOT/'scripts/trim-pvp-data.py')
trim = importlib.util.module_from_spec(spec)
spec.loader.exec_module(trim)


class PvpDataTests(unittest.TestCase):
    def setUp(self):
        self.profile = {'pvp_maps': [559], 'extra_maps': [609],
                        'staging': [{'map': 0, 'x': -8949.95, 'y': -132.493, 'radius': 1}]}

    def test_server_tile_axes_and_vmap_filename_swap(self):
        self.assertTrue(trim.selected(Path('maps/0004832.map'), self.profile))
        self.assertTrue(trim.selected(Path('vmaps/000_32_48.vmtile'), self.profile))
        self.assertFalse(trim.selected(Path('maps/0003248.map'), self.profile))
        self.assertFalse(trim.selected(Path('maps/5714832.map'), self.profile))
        self.assertTrue(trim.selected(Path('maps/5590000.map'), self.profile))
        self.assertTrue(trim.selected(Path('dbc/Spell.dbc'), self.profile))

    def test_dynamic_and_static_collision_dependencies(self):
        name = b'Gate.wmo'
        with tempfile.TemporaryDirectory() as directory:
            p = Path(directory)/'GameObjectModels.dtree'
            p.write_bytes(trim.MAGIC + struct.pack('<IBI', 10, 1, len(name)) + name + bytes(24))
            self.assertEqual(trim.models(p), {'Gate.wmo.vmo'})
            p = Path(directory)/'559_00_00.vmtile'
            spawn = struct.pack('<I', 4) + bytes(34) + bytes(24) + struct.pack('<I',len(name)) + name
            p.write_bytes(trim.MAGIC + struct.pack('<I',1) + spawn + bytes(4))
            self.assertEqual(trim.models(p), {'Gate.wmo.vmo'})

    def test_truncated_or_unsafe_model_name_fails(self):
        with self.assertRaises(ValueError):
            trim.Reader(b'\xff').u32()
        value = b'../unsafe'
        with self.assertRaises(ValueError):
            trim.Reader(struct.pack('<I',len(value))+value).name()

    def test_untiled_global_collision_dependency(self):
        name = b'Arena.wmo'
        with tempfile.TemporaryDirectory() as directory:
            p = Path(directory)/'559.vmtree'
            bih = bytes(24) + struct.pack('<II',0,0)
            spawn = struct.pack('<I',0) + bytes(34) + struct.pack('<I',len(name)) + name
            p.write_bytes(trim.MAGIC + b'\x00NODE' + bih + b'GOBJ' + spawn)
            self.assertEqual(trim.models(p), {'Arena.wmo.vmo'})
