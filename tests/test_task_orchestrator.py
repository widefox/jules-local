import unittest
from unittest import mock
import os
import uuid # For predictable task_id in some tests if needed, or just allow it to generate

# Adjust import path
try:
    from .. import task_orchestrator
    from .. import workspace_manager # To mock its functions
    from .. import container_env   # To mock its functions
    from .. import planning_module # To mock its functions
    from .. import tools           # To mock its functions
except ImportError:
    import sys
    sys.path.append(os.path.join(os.path.dirname(__file__), '..'))
    import task_orchestrator
    import workspace_manager
    import container_env
    import planning_module
    import tools

# Define a dummy task_id that can be used if we want to assert it's passed around.
DUMMY_TASK_ID = "dummy-test-task-id-123"
# Convert to a mock UUID object that has a 'hex' attribute
DUMMY_UUID_OBJ = mock.Mock()
DUMMY_UUID_OBJ.hex = DUMMY_TASK_ID # Keep this for compatibility if uuid.uuid4().hex was used
# However, task_orchestrator.py uses str(uuid.uuid4()), so we need to mock uuid.uuid4() to return an object
# whose str() representation is DUMMY_TASK_ID.
# For task_id = str(uuid.uuid4().hex)
mock_uuid_call_return_object = mock.Mock()
mock_uuid_call_return_object.hex = DUMMY_TASK_ID


class TestTaskOrchestrator(unittest.TestCase):

    def setUp(self):
        # This will mock all functions from the specified modules for all tests in this class.
        # We can then customize their return_values or side_effects per test method.
        self.mock_setup_workspace = mock.patch('task_orchestrator.setup_workspace').start()
        self.mock_cleanup_workspace = mock.patch('task_orchestrator.cleanup_workspace').start()

        self.mock_start_container = mock.patch('task_orchestrator.start_persistent_container').start()
        self.mock_stop_container = mock.patch('task_orchestrator.stop_and_remove_container').start()
        self.mock_run_setup_script = mock.patch('task_orchestrator.run_env_setup_script').start()

        self.mock_generate_plan = mock.patch('task_orchestrator.generate_plan').start()

        self.mock_tool_list_files = mock.patch('task_orchestrator.tools.list_files').start()
        self.mock_tool_read_file = mock.patch('task_orchestrator.tools.read_file').start()
        self.mock_tool_write_file = mock.patch('task_orchestrator.tools.write_file').start()
        self.mock_tool_run_shell = mock.patch('task_orchestrator.tools.run_shell_command').start()
        self.mock_tool_git_diff = mock.patch('task_orchestrator.tools.git_diff').start()
        self.mock_tool_generate_text = mock.patch('task_orchestrator.tools.generate_text_via_llm').start()
        self.mock_tool_get_file_tree = mock.patch('task_orchestrator.tools.get_file_tree').start() # Added

        self.mock_input = mock.patch('builtins.input').start()

        # Default return values for successful operations
        self.mock_setup_workspace.return_value = "/mock/workspace/code"
        self.mock_start_container.return_value = "mock_container_123"
        self.mock_run_setup_script.return_value = True
        self.mock_tool_git_diff.return_value = "mocked git diff output"
        self.mock_tool_get_file_tree.return_value = 'mocked_file_tree_output' # Added

        # Ensure CONTAINER_RUNTIME is True for tests to run past the initial check
        self.mock_container_runtime_check = mock.patch('task_orchestrator.CONTAINER_RUNTIME', True).start()


    def tearDown(self):
        mock.patch.stopall() # Stops all patches started with start()

    @mock.patch('task_orchestrator.uuid.uuid4', return_value=mock_uuid_call_return_object)
    def test_full_successful_run_plan_approved(self, mock_uuid_call_obj): # Updated mock name
        # Arrange
        test_plan = [
            {"tool": "request_user_approval", "args": {"message": "Approve?"}},
            {"tool": "list_files", "args": {"path": "."}},
            {"tool": "write_file", "args": {"file_path": "out.txt", "content": "text"}}
        ]
        self.mock_generate_plan.return_value = test_plan
        self.mock_input.return_value = "yes" # User approves
        self.mock_tool_list_files.return_value = ["file1.txt"]
        self.mock_tool_write_file.return_value = True

        # Act
        task_orchestrator.run_task("mock_repo_path", "mock_prompt")

        # Assert
        self.mock_setup_workspace.assert_called_once_with(original_repo_path="mock_repo_path", task_id=DUMMY_TASK_ID)
        self.mock_start_container.assert_called_once_with(task_id=DUMMY_TASK_ID, workspace_code_path="/mock/workspace/code")
        self.mock_run_setup_script.assert_called_once_with(container_id_or_name="mock_container_123")

        self.mock_tool_get_file_tree.assert_called_once_with(container_id='mock_container_123', start_path='.') # Added
        self.mock_generate_plan.assert_called_once_with( # Updated
            "mock_prompt",
            task_orchestrator.ORCHESTRATOR_AVAILABLE_TOOLS_SPECS,
            file_tree_context='mocked_file_tree_output'
        )
        self.mock_input.assert_called_once_with("\nApprove plan? (yes/no): ")

        self.mock_tool_list_files.assert_called_once_with(container_id="mock_container_123", path=".")
        self.mock_tool_write_file.assert_called_once_with(container_id="mock_container_123", file_path="out.txt", content="text")

        self.mock_tool_git_diff.assert_called_once_with(container_id="mock_container_123")

        self.mock_stop_container.assert_called_once_with("mock_container_123")
        self.mock_cleanup_workspace.assert_called_once_with(DUMMY_TASK_ID)


    def test_user_rejects_plan(self):
        test_plan = [
            {"tool": "request_user_approval", "args": {"message": "Approve?"}},
            {"tool": "list_files", "args": {"path": "."}}
        ]
        self.mock_generate_plan.return_value = test_plan
        self.mock_input.return_value = "no" # User rejects

        task_orchestrator.run_task("mock_repo_path", "mock_prompt")

        self.mock_tool_list_files.assert_not_called()
        self.mock_tool_git_diff.assert_called_once() # Should be called if container ran
        self.mock_stop_container.assert_called_once()
        self.mock_cleanup_workspace.assert_called_once()


    def test_workspace_setup_fails(self):
        self.mock_setup_workspace.return_value = None

        task_orchestrator.run_task("mock_repo_path", "mock_prompt")

        self.mock_start_container.assert_not_called()
        self.mock_generate_plan.assert_not_called()
        self.mock_cleanup_workspace.assert_not_called()
        self.mock_stop_container.assert_not_called()


    def test_container_start_fails(self):
        self.mock_start_container.return_value = None

        task_orchestrator.run_task("mock_repo_path", "mock_prompt")

        self.mock_generate_plan.assert_not_called()
        self.mock_stop_container.assert_not_called()
        self.mock_cleanup_workspace.assert_called_once()


    def test_setup_script_fails(self):
        self.mock_run_setup_script.return_value = False
        test_plan = [{"tool": "request_user_approval", "args": {}}, {"tool": "list_files", "args": {}}]
        self.mock_generate_plan.return_value = test_plan
        self.mock_input.return_value = "yes"

        task_orchestrator.run_task("mock_repo_path", "mock_prompt")

        self.mock_tool_list_files.assert_called_once()
        self.mock_stop_container.assert_called_once()
        self.mock_cleanup_workspace.assert_called_once()


    def test_plan_generation_returns_message_user_plan(self):
        message_plan = [{"tool": "message_user", "args": {"message": "Planner error"}}]
        self.mock_generate_plan.return_value = message_plan

        task_orchestrator.run_task("mock_repo_path", "mock_prompt")

        self.mock_input.assert_not_called()
        self.mock_tool_list_files.assert_not_called()
        self.mock_tool_git_diff.assert_called_once() # Should be called if container ran
        self.mock_stop_container.assert_called_once()
        self.mock_cleanup_workspace.assert_called_once()

    def test_tool_execution_fails(self):
        test_plan = [
            {"tool": "request_user_approval", "args": {}},
            {"tool": "list_files", "args": {}},
            {"tool": "write_file", "args": {"file_path": "f.txt", "content": "c"}}
        ]
        self.mock_generate_plan.return_value = test_plan
        self.mock_input.return_value = "yes"
        self.mock_tool_list_files.return_value = ["ok"]
        self.mock_tool_write_file.return_value = False

        task_orchestrator.run_task("mock_repo_path", "mock_prompt")

        self.mock_tool_list_files.assert_called_once()
        self.mock_tool_write_file.assert_called_once()
        self.mock_tool_git_diff.assert_called_once()
        self.mock_stop_container.assert_called_once()
        self.mock_cleanup_workspace.assert_called_once()

    def test_exception_during_tool_execution_triggers_cleanup(self):
        test_plan = [
            {"tool": "request_user_approval", "args": {}},
            {"tool": "run_shell_command", "args": {"command_str": "explode!"}}
        ]
        self.mock_generate_plan.return_value = test_plan
        self.mock_input.return_value = "yes"
        self.mock_tool_run_shell.side_effect = Exception("Boom!")

        task_orchestrator.run_task("mock_repo_path", "mock_prompt")

        self.mock_tool_run_shell.assert_called_once()
        self.mock_tool_git_diff.assert_called_once() # Git diff should be called if plan was approved
        self.mock_stop_container.assert_called_once()
        self.mock_cleanup_workspace.assert_called_once()

    def test_no_container_runtime(self):
        with mock.patch('task_orchestrator.CONTAINER_RUNTIME', None):
            task_orchestrator.run_task("mock_repo_path", "mock_prompt")
            self.mock_setup_workspace.assert_not_called()


if __name__ == '__main__':
    unittest.main(argv=['first-arg-is-ignored'], exit=False)
