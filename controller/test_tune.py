"""Regression checks for paired evidence, admission and incomplete evaluations."""
import unittest
from unittest.mock import patch

import tune
from benchmark import fits_pool


class TuningTests(unittest.TestCase):
    def test_old_seven_of_twelve_acceptance_is_rejected(self):
        self.assertFalse(tune.evidence([2, 1, 1, 1, 1, 1])['passed'])

    def test_small_unanimous_sample_is_not_enough(self):
        self.assertFalse(tune.evidence([2]*6)['passed'])

    def test_side_bias_does_not_win_paired_test(self):
        result = tune.evidence([1]*24)
        self.assertEqual(result['p_value'], 1)
        self.assertFalse(result['passed'])

    def test_large_consistent_advantage_passes(self):
        self.assertTrue(tune.evidence([2]*20+[0]*4, alpha=.05/12)['passed'])

    def test_margin_alone_cannot_promote(self):
        # 14 winning pairs / 24 is >58%, but compatible with sampling noise.
        self.assertFalse(tune.evidence([2]*14+[0]*10)['passed'])

    def test_plan_repeats_all_ordered_matchups_equally(self):
        from collections import Counter
        jobs = tune.paired_plan(24)
        counts = Counter((j['compA'], j['compH']) for j in jobs)
        self.assertEqual(set(counts.values()), {2})
        self.assertEqual(jobs, tune.paired_plan(24))
        self.assertEqual({j['arena'] for j in tune.paired_plan(24, 'random')}, {'na', 'be'})

    def test_dynamic_capacity_accounts_for_duplicate_classes(self):
        job = dict(compA='beastcleave', compH='rmp')
        state = dict(matches=[], capacity={'A:hunter':1, 'A:shaman':1,
                     'H:rogue':1, 'H:mage':1, 'H:priest':1})
        self.assertFalse(fits_pool(job, state))
        state['capacity']['A:shaman'] = 2
        self.assertTrue(fits_pool(job, state))

    def test_restart_invalidates_even_before_first_result(self):
        with patch.object(tune, 'server_boot', side_effect=['old','new','new']), \
             patch.object(tune, 'results', return_value=[]), \
             patch.object(tune, 'soap', return_value='ArenaBrain A: x=1\nArenaBrain H: x=1'):
            with self.assertRaisesRegex(RuntimeError, 'restarted'):
                tune.run_fixed([dict(pair=0, compA='rmp', compH='tsg', arena='na')], 1, '3')

    def test_benchmark_resume_rejects_recycled_match_ids_without_mutation(self):
        import tempfile
        import json
        import benchmark
        from pathlib import Path
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)
            (path/'restore.json').write_text('{}')
            original = json.dumps({'server_started_at':'old-process'})
            (path/'manifest.json').write_text(original)
            with patch.object(tune.sys, 'argv', ['benchmark.py', '--out', folder, '--resume']), \
                 patch.object(benchmark, 'server_boot', return_value='new-process'), \
                 patch.object(benchmark, 'soap') as soap:
                with self.assertRaisesRegex(RuntimeError, 'Cannot resume'):
                    benchmark.main()
                soap.assert_not_called()
            self.assertEqual((path/'manifest.json').read_text(), original)

    def test_failed_promotion_write_preserves_baseline(self):
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/'params'
            path.write_text('healerBias = 25\n')
            with patch.object(tune, 'PARAMS_FILE', str(path)), \
                 patch.object(tune.os, 'replace', side_effect=OSError('disk failure')):
                with self.assertRaises(OSError):
                    tune.write_params({'healerBias':30})
            self.assertEqual(path.read_text(), 'healerBias = 25\n')
            self.assertEqual(list(Path(folder).iterdir()), [path])

    def test_analyzer_excludes_invalid_setup_instead_of_scoring_draw(self):
        import tempfile
        import json
        from pathlib import Path
        from analyze_benchmark import analyze
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)
            (path/'manifest.json').write_text(json.dumps({'planned':[{}], 'start_errors':[]}))
            (path/'results.jsonl').write_text(json.dumps({'schema':2, 'valid':False})+'\n')
            (path/'snapshots.jsonl').write_text('')
            result = analyze(path)
            self.assertEqual(result['matches'], 0)
            self.assertEqual(result['excluded_invalid'], 1)
            self.assertEqual(result['compositions'], {})

    def test_training_win_cannot_promote_when_holdout_fails(self):
        import contextlib
        import io
        import tempfile
        with tempfile.TemporaryDirectory() as folder, \
             patch.object(tune.sys, 'argv', ['tune.py', '--generations', '1', '--log', folder+'/tune.jsonl']), \
             patch.object(tune, 'status', return_value={'auto':False, 'batch':{'active':False}}), \
             patch.object(tune, 'soap'), patch.object(tune, 'wait_idle'), patch.object(tune, 'apply'), \
             patch.object(tune, 'read_params', return_value={}), \
             patch.object(tune, 'evaluate', side_effect=[([2]*24, []), ([1]*24, [])]), \
             patch.object(tune, 'write_params') as write, contextlib.redirect_stdout(io.StringIO()):
            tune.main()
            write.assert_not_called()

    def test_swapped_games_keep_candidate_composition_and_map(self):
        jobs = tune.paired_plan(24)
        captured = []
        def run(jobs, *_):
            captured.append(jobs)
            side = 'A' if len(captured) == 1 else 'H'
            return [dict(pair=j['pair'], winner=side) for j in jobs]
        with patch.object(tune, 'wait_idle'), patch.object(tune, 'apply'), \
             patch.object(tune, 'run_fixed', side_effect=run):
            scores, _ = tune.evaluate({}, {}, jobs, 6, '3')
        self.assertEqual(scores, [2]*24)
        for first, second in zip(*captured):
            self.assertEqual((first['compA'], first['compH'], first['arena'], first['pair']),
                             (second['compH'], second['compA'], second['arena'], second['pair']))


if __name__ == '__main__':
    unittest.main()
