import plistlib
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'Scripts'))
from automation import LABEL, configure


class AutomationTests(unittest.TestCase):
    def test_install_and_remove_preserves_backups(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(Path, 'home', return_value=Path(directory)), patch('automation.subprocess.run') as run:
            configure('install')
            root = Path(directory) / 'Library/Application Support/NoAdTalk'
            plist = Path(directory) / 'Library/LaunchAgents' / (LABEL + '.plist')
            payload = plistlib.loads(plist.read_bytes())
            self.assertEqual(payload['StartInterval'], 300)
            self.assertEqual(payload['ProgramArguments'], ['/bin/bash', str(root / 'Agent/Scripts/watch.sh')])
            self.assertNotIn('UserName', payload)
            self.assertTrue((root / 'Agent/Scripts/nib.py').is_file())
            self.assertTrue((root / 'Agent/Scripts/manage.py').is_file())
            self.assertTrue((root / 'Agent/NoAdTalk.command').is_file())
            (root / 'Agent/Apply.command').write_text('old')
            backup = root / '27.1.0-3000'
            backup.mkdir()
            (backup / 'FSMainViewController.nib').write_bytes(b'original')
            configure('install')
            self.assertFalse((root / 'Agent/Apply.command').exists())
            configure('remove')
            self.assertFalse(plist.exists())
            self.assertFalse((root / 'Agent').exists())
            self.assertEqual((backup / 'FSMainViewController.nib').read_bytes(), b'original')
            self.assertTrue(any(call.args[0][1] == 'bootstrap' for call in run.call_args_list))

    def test_symlink_rejected(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(Path, 'home', return_value=Path(directory)), patch('automation.subprocess.run'):
            root = Path(directory) / 'Library/Application Support'
            root.mkdir(parents=True)
            (root / 'NoAdTalk').symlink_to(directory)
            with self.assertRaises(ValueError):
                configure('install')


if __name__ == '__main__':
    unittest.main()
