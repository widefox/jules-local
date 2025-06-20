import unittest
from unittest import mock
import json
import os
import sys # Ensure sys is imported for sys.path manipulation

# Adjust import path
try:
    from .. import planning_module
    from .. import gemini_client
except ImportError:
    # Fallback for subtask execution if path isn't set up as package
    # This block might need adjustment based on actual execution environment of subtask
    # For now, assume subtask runs from project root where `tests` is a subdir.
    # If run_tests.py is used, it handles paths correctly.
    # If this specific subtask runs this file directly, sys.path manipulation is needed.
    current_dir = os.path.dirname(__file__)
    project_root = os.path.abspath(os.path.join(current_dir, '..'))
    if project_root not in sys.path:
        sys.path.insert(0, project_root)
    import planning_module
    import gemini_client

# Updated SAMPLE_TOOLS_SPECS to include get_file_tree
SAMPLE_TOOLS_SPECS_WITH_GET_FILE_TREE = [
    {
        "name": "list_files",
        "description": "Lists files and directories.",
        "args_schema": {"path": "string (optional, default: '.')"}
    },
    {
        "name": "read_file",
        "description": "Reads a file.",
        "args_schema": {"file_path": "string (required)"}
    },
    {
        "name": "write_file",
        "description": "Writes to a file.",
        "args_schema": {"file_path": "string (required)", "content": "string (required)"}
    },
    {
        "name": "run_shell_command",
        "description": "Runs a shell command.",
        "args_schema": {"command_str": "string (required)"}
    },
    {
        "name": "generate_text_via_llm",
        "description": "Generates text using a Lite LLM.",
        "args_schema": {"prompt_for_lite_llm": "string (required)"}
    },
    {
        "name": "git_diff",
        "description": "Shows git differences.",
        "args_schema": {"diff_args": "string (optional)"}
    },
    {
        "name": "get_file_tree",
        "description": "Lists all files and directories recursively.",
        "args_schema": {"start_path": "string (optional, default: '.')"}
    }
]


class TestPlanningModule(unittest.TestCase):

    def setUp(self):
        self.original_main_model_name = gemini_client.MAIN_LLM_MODEL_NAME
        gemini_client.MAIN_LLM_MODEL_NAME = "test-main-llm-for-planning"
        self.maxDiff = None
        # Use the updated tool specs for all tests in this class
        self.test_tool_specs = SAMPLE_TOOLS_SPECS_WITH_GET_FILE_TREE

    def tearDown(self):
        gemini_client.MAIN_LLM_MODEL_NAME = self.original_main_model_name
        import importlib
        importlib.reload(gemini_client)

    @mock.patch('planning_module.call_gemini')
    def test_generate_plan_successful_llm_response_with_file_tree(self, mock_call_gemini):
        user_prompt = "Create a file 'output.txt' with content 'hello'."
        sample_file_tree = "file1.txt\nsubdir/file2.txt"
        llm_planned_steps = [{"tool": "write_file", "args": {"file_path": "output.txt", "content": "hello"}}]
        mock_call_gemini.return_value = json.dumps(llm_planned_steps)

        generated_plan = planning_module.generate_plan(user_prompt, self.test_tool_specs, file_tree_context=sample_file_tree)

        mock_call_gemini.assert_called_once()
        llm_prompt_arg = mock_call_gemini.call_args[0][1]
        self.assertIn(user_prompt, llm_prompt_arg)
        self.assertIn("<file_tree>\n" + sample_file_tree + "\n</file_tree>", llm_prompt_arg)
        for tool_spec in self.test_tool_specs:
            self.assertIn(tool_spec['name'], llm_prompt_arg)

        expected_plan_start = [{"tool": "request_user_approval", "args": {"message": mock.ANY}}]
        self.assertEqual(generated_plan[:1], expected_plan_start)
        self.assertEqual(generated_plan[1:], llm_planned_steps)

    @mock.patch('planning_module.call_gemini')
    def test_generate_plan_no_file_tree_context(self, mock_call_gemini):
        user_prompt = "List files."
        llm_planned_steps = [{"tool": "list_files", "args": {"path": "."}}]
        mock_call_gemini.return_value = json.dumps(llm_planned_steps)

        generated_plan = planning_module.generate_plan(user_prompt, self.test_tool_specs, file_tree_context=None)

        llm_prompt_arg = mock_call_gemini.call_args[0][1]
        self.assertIn("No file tree context was provided", llm_prompt_arg)
        self.assertNotIn("<file_tree>", llm_prompt_arg)

        expected_plan_start = [{"tool": "request_user_approval", "args": {"message": mock.ANY}}]
        self.assertEqual(generated_plan[:1], expected_plan_start)
        self.assertEqual(generated_plan[1:], llm_planned_steps)

    @mock.patch('planning_module.call_gemini')
    def test_generate_plan_llm_returns_invalid_json(self, mock_call_gemini):
        user_prompt = "Do something complex."
        mock_call_gemini.return_value = "This is not JSON { definitely not"
        generated_plan = planning_module.generate_plan(user_prompt, self.test_tool_specs, file_tree_context=None)
        self.assertEqual(len(generated_plan),1)
        self.assertEqual(generated_plan[0]['tool'], "message_user")
        self.assertIn("Failed to parse plan from LLM", generated_plan[0]['args']['message'])

    @mock.patch('planning_module.call_gemini')
    def test_prompt_construction_includes_all_tools(self, mock_call_gemini):
        user_prompt = "Test prompt"
        mock_call_gemini.return_value = json.dumps([{"tool": "list_files", "args": {}}])

        planning_module.generate_plan(user_prompt, self.test_tool_specs, file_tree_context="dummy_tree")

        llm_prompt_arg = mock_call_gemini.call_args[0][1]
        for tool_spec in self.test_tool_specs:
             self.assertIn(f"Tool: {tool_spec['name']}", llm_prompt_arg)
             self.assertIn(f"Description: {tool_spec['description']}", llm_prompt_arg)
             self.assertIn(f"Arguments (JSON schema-like): {json.dumps(tool_spec['args_schema'])}", llm_prompt_arg)


if __name__ == '__main__':
    unittest.main(argv=['first-arg-is-ignored'], exit=False)
