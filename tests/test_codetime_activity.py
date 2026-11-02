import unittest
from unittest.mock import patch

import codetime_activity


class TestOperatingSystemDetection(unittest.TestCase):

    @patch("codetime_activity.platform.system", return_value="Linux")
    def test_detects_linux(self, mock_system):
        result = codetime_activity.get_operating_system()

        self.assertEqual(result, "ubuntu_or_linux")

    @patch("codetime_activity.platform.system", return_value="Windows")
    def test_detects_windows(self, mock_system):
        result = codetime_activity.get_operating_system()

        self.assertEqual(result, "windows")

    @patch("codetime_activity.platform.system", return_value="Darwin")
    def test_detects_unsupported_system(self, mock_system):
        result = codetime_activity.get_operating_system()

        self.assertEqual(result, "unsupported")


from unittest.mock import Mock, patch


class TestEditorDetection(unittest.TestCase):

    @patch("codetime_activity.get_operating_system", return_value="ubuntu_or_linux")
    @patch("codetime_activity.subprocess.run")
    def test_detects_vscode_on_linux(self, mock_run, mock_os):
        mock_run.return_value = Mock(stdout="code\nbash\n")

        result = codetime_activity.get_running_editors()

        self.assertEqual(result, ["code"])

    @patch("codetime_activity.get_operating_system", return_value="windows")
    @patch("codetime_activity.subprocess.run")
    def test_detects_vscode_on_windows(self, mock_run, mock_os):
        mock_run.return_value = Mock(
            stdout='"Code.exe","1234","Console","1","150,000 K"\r\n'
        )

        result = codetime_activity.get_running_editors()

        self.assertEqual(result, ["Code.exe"])

    @patch("codetime_activity.get_operating_system", return_value="ubuntu_or_linux")
    @patch("codetime_activity.subprocess.run")
    def test_returns_empty_list_when_no_editor_is_running(
        self, mock_run, mock_os
    ):
        mock_run.return_value = Mock(stdout="bash\npython\n")

        result = codetime_activity.get_running_editors()

        self.assertEqual(result, [])



if __name__ == "__main__":
    unittest.main()
