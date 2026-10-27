import subprocess
import sys
import unittest
from pathlib import Path
from unittest.mock import Mock, call, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'Scripts'))
from manage import SCRIPTS, main, run_action, status


class ManageTests(unittest.TestCase):
    def test_setup_and_restore_order(self):
        operations = Mock()
        with patch('manage.subprocess.run', operations.run), patch('manage.configure', operations.configure):
            run_action('setup')
            self.assertEqual(operations.mock_calls, [call.run(['/bin/bash', str(SCRIPTS / 'patch.sh'), 'apply'], check=True), call.configure('install')])
            operations.reset_mock()
            run_action('restore')
            self.assertEqual(operations.mock_calls, [call.run(['/bin/bash', str(SCRIPTS / 'patch.sh'), 'restore'], check=True), call.configure('remove')])

    def test_failed_patch_does_not_enable_automation(self):
        with patch('manage.subprocess.run', side_effect=subprocess.CalledProcessError(1, 'patch')), patch('manage.configure') as configure:
            with self.assertRaises(subprocess.CalledProcessError):
                run_action('setup')
            configure.assert_not_called()

    def test_status_reads_actual_job(self):
        with patch('manage.subprocess.run', side_effect=[Mock(returncode=3), Mock(returncode=0)]):
            self.assertEqual(status(), '광고 숨김: 적용됨\n자동 감지: 켜짐')
        with patch('manage.subprocess.run', side_effect=[Mock(returncode=0), Mock(returncode=1)]):
            self.assertEqual(status(), '광고 숨김: 적용 가능\n자동 감지: 꺼짐')

    def test_app_management_denial_opens_settings_without_changing_automation(self):
        for action in ('setup', 'apply', 'restore'):
            with self.subTest(action=action), patch('manage.subprocess.run', side_effect=[subprocess.CalledProcessError(77, 'patch'), Mock(returncode=0)]) as run, patch('manage.configure') as configure:
                with self.assertRaisesRegex(ValueError, '앱 관리'):
                    run_action(action)
                self.assertEqual(run.call_args.args[0], ['/usr/bin/open', 'x-apple.systempreferences:com.apple.preference.security?Privacy_AppBundles'])
                configure.assert_not_called()

    def test_cancel_does_not_change_anything(self):
        with patch.object(sys, 'argv', ['manage.py']), patch('manage.status', return_value='상태'), patch('manage.subprocess.run', return_value=Mock(stdout='\n')), patch('manage.run_action') as action:
            main()
            action.assert_not_called()


if __name__ == '__main__':
    unittest.main()
