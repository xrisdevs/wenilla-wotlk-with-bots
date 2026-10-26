import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('prepare_pvp',Path(__file__).resolve().parents[1]/'scripts/prepare-pvp-server.py')
prepare = importlib.util.module_from_spec(spec)
spec.loader.exec_module(prepare)


class IsolatedTargetTests(unittest.TestCase):
    def test_never_runs_docker_for_full_or_source_project(self):
        for source, target in [('wenilla-wotlk','wenilla-wotlk'),('wenilla-pvp-existing','wenilla-pvp-existing')]:
            with tempfile.TemporaryDirectory() as directory:
                dest = Path(directory)/'private'
                argv=['prepare','--source-project',source,'--project',target,'--output',str(dest)]
                with patch('sys.argv',argv), patch.object(prepare.subprocess,'run') as run:
                    with self.assertRaises(SystemExit): prepare.main()
                    run.assert_not_called()
                    self.assertFalse(dest.exists())

    def test_existing_backup_directory_is_never_reused(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch('sys.argv',['prepare','--project','wenilla-pvp-new','--output',directory]), patch.object(prepare.subprocess,'run') as run:
                with self.assertRaises(SystemExit): prepare.main()
                run.assert_not_called()
