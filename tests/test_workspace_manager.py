import unittest
from unittest import mock
import os
import shutil
import tempfile # For creating temporary directories for tests
import subprocess # For the test setup's git commands

# Assuming workspace_manager.py is one level up from the tests directory
# This relative import works when tests are run by a test runner from the project root
try:
    from .. import workspace_manager
except ImportError:
    # Fallback for direct execution or if structure is different in subtask env
    import sys
    sys.path.append(os.path.join(os.path.dirname(__file__), '..'))
    import workspace_manager


class TestWorkspaceManager(unittest.TestCase):

    def setUp(self):
        # Create a temporary directory to act as the main test area
        self.test_main_dir = tempfile.mkdtemp()
        # Inside this, create a mock original repo and where workspaces will be made
        self.mock_original_repo_path = os.path.join(self.test_main_dir, "original_repo")
        os.makedirs(self.mock_original_repo_path, exist_ok=True)

        # Override BASE_WORKSPACE_DIR for testing to keep workspaces within test_main_dir
        self.original_base_workspace_dir = workspace_manager.BASE_WORKSPACE_DIR
        workspace_manager.BASE_WORKSPACE_DIR = os.path.join(self.test_main_dir, "jules_workspaces_test")
        os.makedirs(workspace_manager.BASE_WORKSPACE_DIR, exist_ok=True)

        # Create a dummy file in the mock original repo
        with open(os.path.join(self.mock_original_repo_path, "test_file.txt"), "w") as f:
            f.write("Initial content.")
        # Initialize it as a git repo for clone tests
        # Check if git is available before attempting to use it in setUp
        try:
            subprocess.run(["git", "--version"], check=True, capture_output=True)
            self.git_available = True
            self._git_init_and_commit(self.mock_original_repo_path, "Initial commit with test_file.txt")
            self._git_create_branch(self.mock_original_repo_path, "feature-branch", "feature_file.txt", "Feature content")
        except (subprocess.CalledProcessError, FileNotFoundError):
            self.git_available = False
            print("WARNING: Git not found or usable in test setUp. Some tests might be skipped or behave differently if they rely on real git setup.")


    def tearDown(self):
        # Restore original BASE_WORKSPACE_DIR
        workspace_manager.BASE_WORKSPACE_DIR = self.original_base_workspace_dir
        # Clean up the temporary directory
        shutil.rmtree(self.test_main_dir)

    def _git_init_and_commit(self, repo_path, message):
        # Helper to initialize a repo and make a commit (uses real git for setup)
        subprocess.run(["git", "init", "-b", "main"], cwd=repo_path, check=True, capture_output=True, text=True)
        subprocess.run(["git", "add", "."], cwd=repo_path, check=True, capture_output=True, text=True)
        subprocess.run(["git", "commit", "-m", message], cwd=repo_path, check=True, capture_output=True, text=True)

    def _git_create_branch(self, repo_path, branch_name, file_name, file_content):
        subprocess.run(["git", "checkout", "-b", branch_name], cwd=repo_path, check=True, capture_output=True, text=True)
        with open(os.path.join(repo_path, file_name), "w") as f:
            f.write(file_content)
        subprocess.run(["git", "add", file_name], cwd=repo_path, check=True, capture_output=True, text=True)
        subprocess.run(["git", "commit", "-m", f"Add {file_name} on {branch_name}"], cwd=repo_path, check=True, capture_output=True, text=True)
        subprocess.run(["git", "checkout", "main"], cwd=repo_path, check=True, capture_output=True, text=True)

    @mock.patch('workspace_manager._run_git_command') # Mock the helper within workspace_manager
    def test_setup_workspace_default_branch(self, mock_run_git_command):
        if not self.git_available:
            self.skipTest("Git not available, skipping git-dependent test setup.")

        task_id = "task_default_branch"

        # Configure mock for git operations
        # 1. Mock for 'git clone <repo> <target>'
        # 2. Mock for 'git checkout -b jules_task/...'
        def side_effect_git_commands(*args, **kwargs):
            command_parts = args[0] # _run_git_command takes command_parts as first arg
            # print(f"Mocked _run_git_command called with: {command_parts}") # Debugging
            if command_parts[0] == "clone" and self.mock_original_repo_path in command_parts:
                # Simulate successful clone by creating the target dir (done by setup_workspace itself now)
                # and then the mock should indicate success.
                # The target path is command_parts[-1]
                cloned_repo_target_path = command_parts[-1]
                os.makedirs(os.path.join(cloned_repo_target_path, ".git"), exist_ok=True) # Simulate .git dir
                with open(os.path.join(cloned_repo_target_path, "test_file.txt"), "w") as f: # Simulate cloned file
                    f.write("Cloned content.")
                return True, "Cloned.", "" # success, stdout, stderr
            elif command_parts[0] == "checkout" and command_parts[1] == "-b" and f"jules_task/{task_id}" in command_parts[2]:
                return True, f"Switched to a new branch 'jules_task/{task_id}'", ""
            return False, "", "Unexpected git command in mock"

        mock_run_git_command.side_effect = side_effect_git_commands

        workspace_path = workspace_manager.setup_workspace(self.mock_original_repo_path, task_id)

        self.assertIsNotNone(workspace_path)
        self.assertTrue(os.path.exists(workspace_path))
        self.assertTrue(os.path.exists(os.path.join(workspace_path, ".git")))
        self.assertTrue(os.path.exists(os.path.join(workspace_path, "test_file.txt")))

        self.assertEqual(mock_run_git_command.call_count, 2)
        clone_call_args = mock_run_git_command.call_args_list[0][0][0]
        checkout_call_args = mock_run_git_command.call_args_list[1][0][0]

        self.assertIn("clone", clone_call_args)
        self.assertIn(self.mock_original_repo_path, clone_call_args)

        self.assertIn("checkout", checkout_call_args)
        self.assertIn("-b", checkout_call_args)
        self.assertIn(f"jules_task/{task_id}", checkout_call_args[2])


    @mock.patch('workspace_manager._run_git_command')
    def test_setup_workspace_specific_branch(self, mock_run_git_command):
        if not self.git_available:
            self.skipTest("Git not available, skipping git-dependent test setup.")

        task_id = "task_specific_branch"
        branch_to_clone = "feature-branch"

        def side_effect_git_commands_specific(*args, **kwargs):
            command_parts = args[0]
            if command_parts[0] == "clone" and branch_to_clone in command_parts and self.mock_original_repo_path in command_parts:
                cloned_repo_target_path = command_parts[-1]
                os.makedirs(os.path.join(cloned_repo_target_path, ".git"), exist_ok=True)
                with open(os.path.join(cloned_repo_target_path, "feature_file.txt"), "w") as f:
                    f.write("Cloned feature content.")
                return True, "Cloned specific branch.", ""
            elif command_parts[0] == "checkout" and command_parts[1] == "-b" and f"jules_task/{task_id}" in command_parts[2]:
                return True, f"Switched to a new branch 'jules_task/{task_id}'", ""
            return False, "", "Unexpected git command in mock for specific branch"

        mock_run_git_command.side_effect = side_effect_git_commands_specific

        workspace_path = workspace_manager.setup_workspace(self.mock_original_repo_path, task_id, branch_name=branch_to_clone)

        self.assertIsNotNone(workspace_path)
        self.assertTrue(os.path.exists(os.path.join(workspace_path, "feature_file.txt")))

        self.assertEqual(mock_run_git_command.call_count, 2)
        clone_call_args = mock_run_git_command.call_args_list[0][0][0]
        self.assertIn("-b", clone_call_args)
        self.assertIn(branch_to_clone, clone_call_args)


    @mock.patch('workspace_manager._run_git_command')
    def test_setup_workspace_clone_fails(self, mock_run_git_command):
        if not self.git_available: # This test is still valid as it tests behavior ON git call failure
            pass # Allow to run, as the mock simulates the failure

        task_id = "task_clone_fails"
        # Simulate failure of the 'git clone' command
        mock_run_git_command.return_value = (False, "", "Git clone critical error") # success, stdout, stderr

        workspace_path = workspace_manager.setup_workspace(self.mock_original_repo_path, task_id)
        self.assertIsNone(workspace_path)
        expected_task_workspace_dir = os.path.join(workspace_manager.BASE_WORKSPACE_DIR, f"task_{task_id}")
        self.assertFalse(os.path.exists(expected_task_workspace_dir), "Workspace directory should be cleaned up on clone failure.")
        mock_run_git_command.assert_called_once() # Only clone should be attempted


    def test_setup_workspace_bad_original_path(self):
        task_id = "task_bad_path"
        bad_path = os.path.join(self.test_main_dir, "non_existent_repo") # Does not exist
        workspace_path = workspace_manager.setup_workspace(bad_path, task_id)
        self.assertIsNone(workspace_path)


    @mock.patch('shutil.rmtree')
    def test_cleanup_workspace(self, mock_rmtree):
        task_id = "task_for_cleanup"
        simulated_workspace_dir = os.path.join(workspace_manager.BASE_WORKSPACE_DIR, f"task_{task_id}")

        # To test the actual call to rmtree, the directory must exist.
        # The mock_rmtree will prevent actual deletion.
        os.makedirs(simulated_workspace_dir, exist_ok=True)

        workspace_manager.cleanup_workspace(task_id)
        mock_rmtree.assert_called_once_with(simulated_workspace_dir, onerror=workspace_manager._on_rm_error)

        # Test cleanup when directory doesn't exist
        mock_rmtree.reset_mock()
        # workspace_manager.cleanup_workspace("task_non_existent") # This would print "not found"
        # To test that rmtree is NOT called, we need to ensure os.path.exists(dir) is False
        # So, we call cleanup on a task_id for which we haven't created a dir
        workspace_manager.cleanup_workspace("task_truly_non_existent")
        mock_rmtree.assert_not_called()


if __name__ == '__main__':
    unittest.main(argv=['first-arg-is-ignored'], exit=False)
