import unittest
from unittest import mock
import os
import base64
import importlib

# Adjust import path
try:
    from .. import tools
    from .. import gemini_client
except ImportError:
    import sys
    sys.path.append(os.path.join(os.path.dirname(__file__), '..'))
    import tools
    import gemini_client


class TestTools(unittest.TestCase):
    def setUp(self):
        self.mock_container_id = "test_container_001"
        # Store original gemini_client attributes for potential restoration.
        self.original_gemini_api_key = gemini_client.GEMINI_API_KEY
        self.original_lite_llm_name = gemini_client.LITE_LLM_MODEL_NAME

        # Ensure a clean state for tools module regarding its imports from gemini_client
        # This ensures that 'tools.GEMINI_API_KEY' etc. are reset to whatever gemini_client has.
        importlib.reload(gemini_client)
        importlib.reload(tools)

    def tearDown(self):
        # Restore gemini_client attributes to their original state before this test class ran
        gemini_client.GEMINI_API_KEY = self.original_gemini_api_key
        gemini_client.LITE_LLM_MODEL_NAME = self.original_lite_llm_name
        importlib.reload(gemini_client)
        importlib.reload(tools)

    @mock.patch('tools.execute_in_container')
    def test_list_files_success(self, mock_exec):
        mock_exec.return_value = ("file1.txt\ndir1\n.hidden", "", 0)
        result = tools.list_files(self.mock_container_id, path="test_dir")
        self.assertEqual(result, ["file1.txt", "dir1", ".hidden"])
        mock_exec.assert_called_once_with(
            self.mock_container_id,
            "ls -A1 /workspace/test_dir",
            working_dir="/workspace"
        )

    @mock.patch('tools.execute_in_container')
    def test_list_files_empty(self, mock_exec):
        mock_exec.return_value = ("", "", 0) # Empty stdout
        result = tools.list_files(self.mock_container_id, path="empty_dir")
        self.assertEqual(result, [])

    @mock.patch('tools.execute_in_container')
    def test_list_files_error(self, mock_exec):
        mock_exec.return_value = ("", "ls: cannot access: No such file or directory", 1)
        result = tools.list_files(self.mock_container_id, path="nonexistent_dir")
        self.assertIsNone(result)

    def test_list_files_path_escape_attempt(self):
        result = tools.list_files(self.mock_container_id, path="../outside")
        self.assertIsNone(result)

    @mock.patch('tools.execute_in_container')
    def test_read_file_success(self, mock_exec):
        mock_exec.return_value = ("file content here", "", 0)
        result = tools.read_file(self.mock_container_id, "file.txt")
        self.assertEqual(result, "file content here")
        mock_exec.assert_called_once_with(
            self.mock_container_id,
            "cat /workspace/file.txt",
            working_dir="/workspace"
        )

    @mock.patch('tools.execute_in_container')
    def test_read_file_not_found(self, mock_exec):
        mock_exec.return_value = ("", "cat: /workspace/notfound.txt: No such file or directory", 1)
        result = tools.read_file(self.mock_container_id, "notfound.txt")
        self.assertIsNone(result)

    def test_read_file_path_escape_attempt(self):
        result = tools.read_file(self.mock_container_id, "../secrets.txt")
        self.assertIsNone(result)

    @mock.patch('tools.execute_in_container')
    def test_write_file_success(self, mock_exec):
        mock_exec.side_effect = [("", "", 0), ("", "", 0)]
        file_content = "Hello World!"
        encoded_content = base64.b64encode(file_content.encode('utf-8')).decode('utf-8')
        result = tools.write_file(self.mock_container_id, "new/file.txt", file_content)
        self.assertTrue(result)
        expected_calls = [
            mock.call(self.mock_container_id, "mkdir -p /workspace/new", working_dir="/workspace"),
            mock.call(self.mock_container_id, f"echo '{encoded_content}' | base64 -d > /workspace/new/file.txt", working_dir="/workspace")
        ]
        self.assertEqual(mock_exec.call_args_list, expected_calls)

    @mock.patch('tools.execute_in_container')
    def test_write_file_mkdir_fails(self, mock_exec):
        mock_exec.return_value = ("", "mkdir error", 1)
        result = tools.write_file(self.mock_container_id, "new_dir/file.txt", "content")
        self.assertFalse(result)
        mock_exec.assert_called_once_with(self.mock_container_id, "mkdir -p /workspace/new_dir", working_dir="/workspace")


    @mock.patch('tools.execute_in_container')
    def test_write_file_echo_fails(self, mock_exec):
        mock_exec.side_effect = [("", "", 0), ("", "echo error", 1)]
        result = tools.write_file(self.mock_container_id, "another/file.txt", "content")
        self.assertFalse(result)

    def test_write_file_path_escape_attempt(self):
        result = tools.write_file(self.mock_container_id, "../badfile.txt", "content")
        self.assertFalse(result)

    @mock.patch('tools.execute_in_container')
    def test_run_shell_command_success(self, mock_exec):
        mock_exec.return_value = ("command output", "", 0)
        stdout, stderr, exit_code = tools.run_shell_command(self.mock_container_id, "echo 'hello'")
        self.assertEqual(stdout, "command output")
        self.assertEqual(stderr, "")
        self.assertEqual(exit_code, 0)

    @mock.patch('tools.execute_in_container')
    def test_run_shell_command_failure(self, mock_exec):
        mock_exec.return_value = ("", "error output", 1)
        _, stderr, exit_code = tools.run_shell_command(self.mock_container_id, "failing_command")
        self.assertEqual(stderr, "error output")
        self.assertEqual(exit_code, 1)

    def test_run_shell_command_bad_working_dir(self):
        _, stderr, exit_code = tools.run_shell_command(self.mock_container_id, "pwd", wd="/etc")
        expected_stderr = "Error (run_shell_command): Working directory '/etc' must be /workspace or a subdirectory."
        self.assertEqual(stderr, expected_stderr)
        self.assertEqual(exit_code, -1)

    @mock.patch('tools.execute_in_container')
    def test_git_diff_success(self, mock_exec):
        mock_exec.return_value = ("--- a/file.txt\n+++ b/file.txt\n-old\n+new", "", 0)
        result = tools.git_diff(self.mock_container_id, diff_args="--staged")
        self.assertIn("--- a/file.txt", result)

    @mock.patch('tools.execute_in_container')
    def test_git_diff_no_changes(self, mock_exec):
        mock_exec.return_value = ("", "", 0)
        result = tools.git_diff(self.mock_container_id)
        self.assertEqual(result, "(No changes detected or diff output was empty)")

    @mock.patch('tools.execute_in_container')
    def test_git_diff_error(self, mock_exec):
        mock_exec.return_value = ("", "fatal: not a git repository", 128)
        result = tools.git_diff(self.mock_container_id)
        self.assertIsNone(result)

    def test_git_diff_invalid_args(self):
        result = tools.git_diff(self.mock_container_id, diff_args="; rm -rf /")
        self.assertIsNone(result)

    @mock.patch('tools.call_gemini')
    def test_generate_text_via_llm_success(self, mock_call_gemini_in_tools_module):
        with mock.patch.object(tools, 'GEMINI_API_KEY', 'fake_key_for_test_success'), \
             mock.patch.object(tools, 'LITE_LLM_MODEL_NAME', 'test-lite-model-success'):

            mock_call_gemini_in_tools_module.return_value = "LLM generated text."
            prompt = "Write a poem."
            result = tools.generate_text_via_llm(self.mock_container_id, prompt)

            self.assertEqual(result, "LLM generated text.")
            mock_call_gemini_in_tools_module.assert_called_once_with(
                model_name='test-lite-model-success',
                prompt_text=prompt
            )

    @mock.patch('tools.call_gemini')
    def test_generate_text_via_llm_api_call_fails(self, mock_call_gemini_in_tools_module):
        with mock.patch.object(tools, 'GEMINI_API_KEY', 'fake_key_for_test_apifail'), \
             mock.patch.object(tools, 'LITE_LLM_MODEL_NAME', 'test-lite-model-apifail'):

            mock_call_gemini_in_tools_module.return_value = None # LLM call fails
            result = tools.generate_text_via_llm(self.mock_container_id, "A prompt.")
            self.assertIsNone(result)
            mock_call_gemini_in_tools_module.assert_called_once()

    @mock.patch('tools.call_gemini')
    def test_generate_text_via_llm_no_api_key(self, mock_call_gemini_in_tools_module):
        with mock.patch.object(tools, 'GEMINI_API_KEY', None), \
             mock.patch.object(tools, 'LITE_LLM_MODEL_NAME', 'test-lite-model-noapikey'):

            result = tools.generate_text_via_llm(self.mock_container_id, "A prompt.")
            self.assertIsNone(result)
            mock_call_gemini_in_tools_module.assert_not_called()

    @mock.patch('tools.call_gemini')
    def test_generate_text_via_llm_no_lite_model_name(self, mock_call_gemini_in_tools_module):
        with mock.patch.object(tools, 'GEMINI_API_KEY', 'fake_key_for_test_nomodel'), \
             mock.patch.object(tools, 'LITE_LLM_MODEL_NAME', ''): # Empty model name

            result = tools.generate_text_via_llm(self.mock_container_id, "A prompt.")
            self.assertIsNone(result)
            mock_call_gemini_in_tools_module.assert_not_called()


    @mock.patch('tools.execute_in_container')
    def test_get_file_tree_success_default_path(self, mock_exec):
        # Mock find . -name .git -prune -o -print (from /workspace)
        mock_exec.return_value = ("./file1.txt\n./subdir\n./subdir/file2.txt\n./.hiddenfile", "", 0)
        result = tools.get_file_tree(self.mock_container_id) # Defaults to start_path="."
        expected_output = "file1.txt\nsubdir\nsubdir/file2.txt\n.hiddenfile" # Leading "./" stripped
        self.assertEqual(result, expected_output)
        mock_exec.assert_called_once_with(
            self.mock_container_id,
            "find . -name .git -prune -o -print", # Corrected: shlex.quote('.') is '.'
            working_dir="/workspace"
        )

    @mock.patch('tools.execute_in_container')
    def test_get_file_tree_success_specific_subdir(self, mock_exec):
        # Mock find src -name .git -prune -o -print (from /workspace)
        # Output from find will be like "src/file.py", "src/another/data.txt"
        mock_exec.return_value = ("src/main.py\nsrc/utils\nsrc/utils/helper.py", "", 0)
        result = tools.get_file_tree(self.mock_container_id, start_path="src")
        # Output should be as is, since paths are already relative to /workspace and start with 'src/'
        expected_output = "src/main.py\nsrc/utils\nsrc/utils/helper.py"
        self.assertEqual(result, expected_output)
        mock_exec.assert_called_once_with(
            self.mock_container_id,
            "find src -name .git -prune -o -print", # Corrected: shlex.quote('src') is 'src'
            working_dir="/workspace"
        )

    @mock.patch('tools.execute_in_container')
    def test_get_file_tree_empty_directory(self, mock_exec):
        # Test case 1: find returns only the directory itself (and it's not ".")
        mock_exec.return_value = ("empty_subdir", "", 0)
        result = tools.get_file_tree(self.mock_container_id, start_path="empty_subdir")
        self.assertEqual(result, "empty_subdir")

        # Test case 2: find returns nothing (truly empty or error handled by find itself as empty)
        mock_exec.reset_mock() # Reset for next call
        mock_exec.return_value = ("", "", 0)
        result = tools.get_file_tree(self.mock_container_id, start_path="truly_empty")
        self.assertEqual(result, "")

        # Test case 3: find returns just "." when start_path is "." and dir is empty
        mock_exec.reset_mock()
        mock_exec.return_value = (".", "", 0)
        result = tools.get_file_tree(self.mock_container_id, start_path=".")
        self.assertEqual(result, "") # Should be empty after processing


    @mock.patch('tools.execute_in_container')
    def test_get_file_tree_find_fails(self, mock_exec):
        mock_exec.return_value = ("", "find: some error", 1)
        result = tools.get_file_tree(self.mock_container_id, start_path="any_path")
        self.assertIsNone(result)

    def test_get_file_tree_path_escape_absolute(self):
        result = tools.get_file_tree(self.mock_container_id, start_path="/etc") # Absolute path
        self.assertIsNone(result) # Should be caught by safety check

    def test_get_file_tree_path_escape_relative(self):
        result = tools.get_file_tree(self.mock_container_id, start_path="../outside_workspace")
        self.assertIsNone(result) # Should be caught by safety check

    def test_get_file_tree_on_git_dir(self):
        # Test trying to list .git explicitly
        result = tools.get_file_tree(self.mock_container_id, start_path=".git")
        self.assertEqual(result, "") # Should return empty as per current logic

if __name__ == '__main__':
    unittest.main(argv=['first-arg-is-ignored'], exit=False)
