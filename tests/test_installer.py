import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class InstallerTests(unittest.TestCase):
    def run_installer(self, *args, env=None):
        environment = os.environ.copy()
        for key in ['CODEX_HOME', 'MONITOR_TOKEN', 'MONITOR_CONFIG']:
            environment.pop(key, None)
        environment.update(env or {})
        process = subprocess.run([sys.executable, str(ROOT / 'install.py'), *map(str, args)], capture_output=True, text=True, encoding='utf-8', env=environment)
        return process.returncode, json.loads(process.stdout), process.stdout + process.stderr

    def test_custom_harness_install_is_complete_and_idempotent(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            args = ['--dest', root / 'deepseek-harness' / 'skills', '--config', root / 'client.env']
            code, result, _ = self.run_installer(*args)
            self.assertEqual(code, 0)
            self.assertEqual(result['installation'], 'installed')
            self.assertFalse(result['reporting_started'])
            target = Path(result['skill_path'])
            self.assertEqual((target / 'scripts/report.py').read_bytes(), (ROOT / 'skills/long-task-monitor/scripts/report.py').read_bytes())
            (target / 'personal-note.txt').write_text('keep me')
            code, result, _ = self.run_installer(*args)
            self.assertEqual(code, 0)
            self.assertEqual(result['installation'], 'already_installed')
            self.assertEqual((target / 'personal-note.txt').read_text(), 'keep me')

    def test_codex_respects_codex_home(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            code, result, _ = self.run_installer('--codex', '--config', root / 'client.env', env={'CODEX_HOME': str(root / 'codex')})
            self.assertEqual(code, 0)
            self.assertEqual(Path(result['skill_path']), root / 'codex' / 'skills' / 'long-task-monitor')

    def test_configuration_uses_environment_without_printing_secret_or_sending_events(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            token = 'private-reporting-token'.ljust(64, 'x')
            args = ['--dest', root / 'skills', '--config', root / 'client.env', '--server', 'https://offline.invalid/monitor/']
            code, result, output = self.run_installer(*args, env={'MONITOR_TOKEN': token})
            self.assertEqual(code, 0)
            self.assertEqual(result['configuration'], 'created')
            self.assertFalse(result['reporting_started'])
            self.assertNotIn(token, output)
            self.assertEqual((root / 'client.env').read_text(), f'MONITOR_URL=https://offline.invalid/monitor\nMONITOR_TOKEN={token}\n')
            code, result, output = self.run_installer(*args, env={'MONITOR_TOKEN': 'new'.ljust(64, 'y')})
            self.assertEqual(result['configuration'], 'kept_existing')
            self.assertIn(token, (root / 'client.env').read_text())

    def test_missing_secret_does_not_create_incomplete_configuration(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            code, result, _ = self.run_installer('--dest', root / 'skills', '--config', root / 'client.env', '--server', 'https://offline.invalid')
            self.assertEqual(code, 0)
            self.assertEqual(result['configuration'], 'needs_token')
            self.assertFalse((root / 'client.env').exists())

    def test_modified_skill_is_not_overwritten(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            args = ['--dest', root / 'skills', '--config', root / 'client.env']
            self.run_installer(*args)
            file = root / 'skills/long-task-monitor/SKILL.md'
            file.write_text('user customization')
            code, _, _ = self.run_installer(*args)
            self.assertEqual(code, 1)
            self.assertEqual(file.read_text(), 'user customization')

    def test_invalid_server_or_secret_is_rejected_before_installation(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for server, token in [('http://remote.invalid', 'x' * 64), ('https://user:secret@offline.invalid', 'x' * 64), ('https://offline.invalid:99999', 'x' * 64), ('https://offline.invalid', 'short')]:
                code, _, output = self.run_installer('--dest', root / 'skills', '--server', server, env={'MONITOR_TOKEN': token})
                self.assertEqual(code, 1)
                self.assertFalse((root / 'skills').exists())
                self.assertNotIn(token, output)


if __name__ == '__main__':
    unittest.main()
