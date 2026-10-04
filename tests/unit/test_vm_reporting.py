import json
from pathlib import Path
import subprocess
import tempfile
import unittest

from tests.vm.report import render
from tests.vm.update import adapt_update


class UpdateAdapterTests(unittest.TestCase):
    def test_defers_only_restart_and_preserves_update_failure(self):
        source = ('#!/bin/bash\nset -e\n'
                  'true\n  omarchy-update-status\n  omarchy-update-restart\n')
        adapted = adapt_update(source)
        self.assertIn('timeout --kill-after=5s 60s omarchy-update-status', adapted)
        self.assertNotIn('\n  omarchy-update-restart\n', adapted)
        result = subprocess.run(['bash', '-c', adapt_update(source.replace('true\n', 'exit 23\n'))],
                                capture_output=True)
        self.assertEqual(result.returncode, 23)

    def test_changed_upstream_fails_closed(self):
        with self.assertRaisesRegex(RuntimeError, 'lifecycle changed'):
            adapt_update('#!/bin/bash\necho changed\n')


class ReportTests(unittest.TestCase):
    def test_guest_step_records_failure_without_continuing(self):
        source = (Path(__file__).parents[1] / 'vm/guest.sh').read_text()
        functions = source.split("CURRENT_STEP=''", 1)[1].split('cleanup() {', 1)[0]
        with tempfile.TemporaryDirectory() as directory:
            script = ('set -euo pipefail\nARTIFACTS=$1\nMODE=upgrade\nPHASE=initial\n'
                      "CURRENT_STEP=''\n" + functions +
                      '\ntrap \'rc=$?; [[ -z $CURRENT_STEP ]] || record_step FAIL "$rc"\' EXIT\n'
                      "step first true\nstep second bash -c 'exit 23'\nstep unreachable true\n")
            result = subprocess.run(['bash', '-c', script, 'fixture', directory], capture_output=True)
            self.assertEqual(result.returncode, 23)
            records = [json.loads(line) for line in
                       (Path(directory) / 'results-initial.jsonl').read_text().splitlines()]
            self.assertEqual([(r['name'], r['status'], r['exit_code']) for r in records],
                             [('first', 'PASS', 0), ('second', 'FAIL', 23)])

    def test_late_failure_keeps_prior_pass_and_reports_missing_coverage(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            records = [dict(target='upgrade', phase='initial', name=name, status=status,
                            seconds=3, exit_code=code)
                       for name, status, code in [('Bootstrap', 'PASS', 0), ('Update', 'FAIL', 124)]]
            (root / 'results-initial.jsonl').write_text('\n'.join(map(json.dumps, records)))
            report = render(root, {'UPGRADE_CANDIDATE': 'failure'})
            self.assertIn('Passed: **1** · Failed: **1**', report)
            self.assertIn('Bootstrap | PASS', report)
            self.assertIn('Update | FAIL', report)
            self.assertIn('exit 124', report)
            self.assertIn('UNVERIFIED', report)

    def test_no_artifacts_never_claims_guest_success(self):
        with tempfile.TemporaryDirectory() as directory:
            report = render(Path(directory), {})
            self.assertIn('No acceptance records available', report)
            self.assertIn('UNKNOWN', report)

    def test_truncated_record_is_visible(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'results-initial.jsonl').write_text('{')
            self.assertIn('Unreadable result', render(root, {}))
