import ctypes
import os
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))


@unittest.skipUnless(os.name=='nt','Windows native ABI only')
class WindowsPickerBridgeTest(unittest.TestCase):
    def test_unicode_display_buffer_and_cancel_cleanup(self):
        from highsc.windows import choose_folder
        shell=SimpleNamespace(SHBrowseForFolderW=Mock(return_value=0),SHGetPathFromIDListW=Mock())
        ole=SimpleNamespace(CoInitializeEx=Mock(return_value=0),CoTaskMemFree=Mock(),CoUninitialize=Mock())
        user=SimpleNamespace(SendMessageW=Mock(),SetForegroundWindow=Mock())
        with patch.object(ctypes,'windll',SimpleNamespace(shell32=shell,ole32=ole,user32=user)):
            # Constructs the real ctypes structure, including its Unicode
            # output pointer: this is where the reported TypeError occurred.
            self.assertIsNone(choose_folder('C:\\'))
        shell.SHBrowseForFolderW.assert_called_once();ole.CoUninitialize.assert_called_once();ole.CoTaskMemFree.assert_not_called()

    def test_selected_unicode_path_and_pidl_cleanup(self):
        from highsc.windows import choose_folder
        selected='C:\\Users\\Public\\中文 文件夹'
        def extract(pidl,buffer):buffer.value=selected;return True
        shell=SimpleNamespace(SHBrowseForFolderW=Mock(return_value=123),SHGetPathFromIDListW=Mock(side_effect=extract))
        ole=SimpleNamespace(CoInitializeEx=Mock(return_value=0),CoTaskMemFree=Mock(),CoUninitialize=Mock())
        user=SimpleNamespace(SendMessageW=Mock(),SetForegroundWindow=Mock())
        with patch.object(ctypes,'windll',SimpleNamespace(shell32=shell,ole32=ole,user32=user)):
            self.assertEqual(choose_folder('C:\\'),selected)
        ole.CoTaskMemFree.assert_called_once_with(123);ole.CoUninitialize.assert_called_once()

    def test_native_failure_has_actionable_message(self):
        from highsc.output import choose_folder
        with patch('highsc.windows.choose_folder',side_effect=TypeError('native argument failed')),self.assertLogs('highsc.output',level='ERROR'):
            with self.assertRaisesRegex(ValueError,'手动填写完整路径'):choose_folder('C:\\')
