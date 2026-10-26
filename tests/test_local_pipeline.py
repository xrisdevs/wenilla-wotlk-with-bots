import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

spec=importlib.util.spec_from_file_location('local_pipeline',Path(__file__).resolve().parents[1]/'deploy/hetzner/pipeline.py')
pipeline=importlib.util.module_from_spec(spec);spec.loader.exec_module(pipeline)

class PipelineTests(unittest.TestCase):
    def invoke(self,state,remote,run_effect=None):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);config=root/'config.json'
            config.write_text(json.dumps({'repository':'https://example.invalid/project.git','state_directory':str(root)}))
            (root/'state.json').write_text(json.dumps(state))
            with patch('sys.argv',['pipeline','--config',str(config)]),patch.object(pipeline,'output',return_value=remote+' refs/heads/arena-with-bots'),patch.object(pipeline,'run',side_effect=run_effect) as run:
                error=None
                try:pipeline.main()
                except Exception as exc:error=exc
                return json.loads((root/'state.json').read_text()),run.call_count,error
    def test_unchanged_revision_does_not_build_or_connect(self):
        state,calls,error=self.invoke({'deployed':'a'*40},'a'*40)
        self.assertEqual(calls,0);self.assertIsNone(error)
    def test_failed_revision_waits_for_retry_or_new_push(self):
        state,calls,error=self.invoke({'deployed':'a'*40,'failed':'b'*40},'b'*40)
        self.assertEqual(calls,0);self.assertIsNone(error)
    def test_unavailable_docker_records_failure_without_advancing_deployment(self):
        state,calls,error=self.invoke({'deployed':'a'*40},'b'*40,subprocess.CalledProcessError(1,['docker','info']))
        self.assertIsNotNone(error);self.assertEqual(calls,1)
        self.assertEqual(state['deployed'],'a'*40);self.assertEqual(state['failed'],'b'*40)

if __name__=='__main__': unittest.main()
