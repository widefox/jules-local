import unittest
from unittest import mock
import json
import os

# Adjust import path
try:
    from .. import planning_module
    from .. import gemini_client # To mock its constants if needed, and its call_gemini
except ImportError:
    import sys
    sys.path.append(os.path.join(os.path.dirname(__file__), '..'))
    import planning_module
    import gemini_client


# Define a sample DEFAULT_AVAILABLE_TOOLS_SPECS for use in tests,
# mirroring what the planning_module would expect.
SAMPLE_TOOLS_SPECS = [
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
    # Not including request_user_approval or message_user here as LLM isn't supposed to plan them.
]


class TestPlanningModule(unittest.TestCase):

    def setUp(self):
        # Save and override MAIN_LLM_MODEL_NAME from gemini_client for predictability in tests
        # if the planning_module imports it directly.
        self.original_main_model_name = gemini_client.MAIN_LLM_MODEL_NAME
        gemini_client.MAIN_LLM_MODEL_NAME = "test-main-llm-for-planning"

        # The planning_module itself might also have AVAILABLE_TOOLS as a global.
        # If tests need to modify this, it should be handled carefully (e.g. patching).
        # For now, we pass available_tools_specs directly to generate_plan.
        self.maxDiff = None # Show full diff on assertion failure


    def tearDown(self):
        gemini_client.MAIN_LLM_MODEL_NAME = self.original_main_model_name
        # No need to reload planning_module if it doesn't use MAIN_LLM_MODEL_NAME at import time
        # but reloads gemini_client if other tests depend on its original state.
        import importlib
        importlib.reload(gemini_client)


    @mock.patch('planning_module.call_gemini') # Patch where it's used
    def test_generate_plan_successful_llm_response(self, mock_call_gemini):
        user_prompt = "Create a file 'output.txt' with content 'hello'."
        llm_planned_steps = [
            {"tool": "write_file", "args": {"file_path": "output.txt", "content": "hello"}}
        ]
        mock_call_gemini.return_value = json.dumps(llm_planned_steps)

        generated_plan = planning_module.generate_plan(user_prompt, SAMPLE_TOOLS_SPECS)

        mock_call_gemini.assert_called_once()
        # We can inspect the prompt passed to the LLM if needed:
        # llm_prompt_arg = mock_call_gemini.call_args[0][1] # Second arg to call_gemini
        # self.assertIn(user_prompt, llm_prompt_arg)
        # for tool_spec in SAMPLE_TOOLS_SPECS:
        #     self.assertIn(tool_spec['name'], llm_prompt_arg)
        #     self.assertIn(tool_spec['description'], llm_prompt_arg)

        expected_plan = [
            {"tool": "request_user_approval", "args": {"message": mock.ANY}}, # Message can vary slightly
            {"tool": "write_file", "args": {"file_path": "output.txt", "content": "hello"}}
        ]
        # Compare step-by-step, ignoring the exact approval message
        self.assertEqual(len(generated_plan), len(expected_plan))
        self.assertEqual(generated_plan[0]['tool'], expected_plan[0]['tool'])
        self.assertEqual(generated_plan[1], expected_plan[1])


    @mock.patch('planning_module.call_gemini')
    def test_generate_plan_llm_returns_invalid_json(self, mock_call_gemini):
        user_prompt = "Do something complex."
        mock_call_gemini.return_value = "This is not JSON { definitely not"

        generated_plan = planning_module.generate_plan(user_prompt, SAMPLE_TOOLS_SPECS)

        self.assertEqual(len(generated_plan), 1)
        self.assertEqual(generated_plan[0]['tool'], "message_user")
        self.assertIn("Failed to parse plan from LLM", generated_plan[0]['args']['message'])

    @mock.patch('planning_module.call_gemini')
    def test_generate_plan_llm_returns_malformed_plan_structure(self, mock_call_gemini):
        user_prompt = "Another task."
        # Valid JSON, but not the expected list of dicts structure
        mock_call_gemini.return_value = json.dumps({"plan": "should_be_list"})

        generated_plan = planning_module.generate_plan(user_prompt, SAMPLE_TOOLS_SPECS)
        self.assertEqual(len(generated_plan), 1)
        self.assertEqual(generated_plan[0]['tool'], "message_user")
        self.assertIn("LLM response is not a JSON list", generated_plan[0]['args']['message'])

        # Valid list, but step is not a dict
        mock_call_gemini.return_value = json.dumps(["not_a_dict_step"])
        generated_plan = planning_module.generate_plan(user_prompt, SAMPLE_TOOLS_SPECS)
        self.assertEqual(len(generated_plan), 1)
        self.assertEqual(generated_plan[0]['tool'], "message_user")
        self.assertIn("Invalid step structure", generated_plan[0]['args']['message'])

        # Step is dict, but missing 'tool' or 'args'
        mock_call_gemini.return_value = json.dumps([{"args": {}}]) # Missing 'tool'
        generated_plan = planning_module.generate_plan(user_prompt, SAMPLE_TOOLS_SPECS)
        self.assertEqual(len(generated_plan), 1)
        self.assertEqual(generated_plan[0]['tool'], "message_user")
        self.assertIn("Invalid step structure", generated_plan[0]['args']['message'])

        # Args not a dict
        mock_call_gemini.return_value = json.dumps([{"tool": "list_files", "args": "not_a_dict"}])
        generated_plan = planning_module.generate_plan(user_prompt, SAMPLE_TOOLS_SPECS)
        self.assertEqual(len(generated_plan), 1)
        self.assertEqual(generated_plan[0]['tool'], "message_user")
        self.assertIn("Args for tool list_files must be a dictionary/object", generated_plan[0]['args']['message'])


    @mock.patch('planning_module.call_gemini')
    def test_generate_plan_llm_uses_unknown_tool(self, mock_call_gemini):
        user_prompt = "Use a magic wand."
        llm_plan_with_unknown_tool = [{"tool": "magic_wand", "args": {"spell": "abracadabra"}}]
        mock_call_gemini.return_value = json.dumps(llm_plan_with_unknown_tool)

        generated_plan = planning_module.generate_plan(user_prompt, SAMPLE_TOOLS_SPECS)
        self.assertEqual(len(generated_plan), 1)
        self.assertEqual(generated_plan[0]['tool'], "message_user")
        self.assertIn("LLM planned to use an unknown tool: magic_wand", generated_plan[0]['args']['message'])

    @mock.patch('planning_module.call_gemini')
    def test_generate_plan_llm_call_fails_returns_none(self, mock_call_gemini):
        user_prompt = "A prompt."
        mock_call_gemini.return_value = None # Simulate gemini_client.call_gemini failure

        generated_plan = planning_module.generate_plan(user_prompt, SAMPLE_TOOLS_SPECS)
        self.assertEqual(len(generated_plan), 1)
        self.assertEqual(generated_plan[0]['tool'], "message_user")
        self.assertIn("LLM call failed", generated_plan[0]['args']['message'])

    @mock.patch('planning_module.call_gemini')
    def test_generate_plan_llm_cannot_fulfill_request(self, mock_call_gemini):
        user_prompt = "Solve global peace."
        llm_cannot_fulfill_plan = [{"tool": "cannot_fulfill_request", "args": {"reason": "This is too complex."}}]
        mock_call_gemini.return_value = json.dumps(llm_cannot_fulfill_plan)

        generated_plan = planning_module.generate_plan(user_prompt, SAMPLE_TOOLS_SPECS)
        self.assertEqual(len(generated_plan), 1)
        self.assertEqual(generated_plan[0]['tool'], "message_user")
        self.assertIn("Planner: This is too complex.", generated_plan[0]['args']['message'])

    @mock.patch('planning_module.call_gemini')
    def test_generate_plan_llm_empty_plan_response(self, mock_call_gemini):
        user_prompt = "Do nothing."
        mock_call_gemini.return_value = json.dumps([]) # Empty list from LLM

        generated_plan = planning_module.generate_plan(user_prompt, SAMPLE_TOOLS_SPECS)
        self.assertEqual(len(generated_plan), 1)
        self.assertEqual(generated_plan[0]['tool'], "message_user")
        self.assertIn("LLM returned an empty plan.", generated_plan[0]['args']['message'])

    @mock.patch('planning_module.call_gemini')
    def test_prompt_construction_for_llm(self, mock_call_gemini):
        user_prompt = "List files in src and read main.py."
        mock_call_gemini.return_value = json.dumps([
            {"tool": "list_files", "args": {"path": "src"}},
            {"tool": "read_file", "args": {"file_path": "src/main.py"}}
        ])

        planning_module.generate_plan(user_prompt, SAMPLE_TOOLS_SPECS)

        mock_call_gemini.assert_called_once()
        llm_prompt_arg = mock_call_gemini.call_args[0][1] # Second argument to call_gemini is the prompt string

        self.assertIn(f'The user\'s request is: "{user_prompt}"', llm_prompt_arg)
        for tool_spec in SAMPLE_TOOLS_SPECS:
            self.assertIn(f"Tool: {tool_spec['name']}", llm_prompt_arg)
            self.assertIn(f"Description: {tool_spec['description']}", llm_prompt_arg)
            self.assertIn(f"Arguments (JSON schema-like): {json.dumps(tool_spec['args_schema'])}", llm_prompt_arg)
        self.assertIn("generate a plan consisting of a sequence of tool calls.", llm_prompt_arg)
        self.assertIn("The plan should be a JSON array of objects", llm_prompt_arg)

    def test_generate_plan_with_empty_tool_specs(self):
        # This test doesn't mock call_gemini because the prompt construction itself should be tested.
        # The actual call_gemini will use its internal mock for standalone module testing.
        user_prompt = "List files."
        # The LLM should be told no tools are available.
        # The mock call_gemini in this file's header will then return a 'cannot fulfill' or similar.

        # This relies on the mock defined in planning_module.py when gemini_client is not found
        # That mock returns: json.dumps([{"tool": "message_user", "args": {"message": "Mock LLM could not determine a plan for this prompt."}}])
        generated_plan = planning_module.generate_plan(user_prompt, [])

        self.assertEqual(len(generated_plan), 1)
        self.assertEqual(generated_plan[0]['tool'], "message_user")
        # Check if the message indicates inability or failure due to no tools
        # This path is taken if the real gemini_client.call_gemini is called and returns None (e.g. no API KEY)
        self.assertIn("LLM call failed", generated_plan[0]['args']['message'],
                      "If toolspecs are empty, it's expected that the LLM call might fail or be skipped, leading to this message.")


    @mock.patch('planning_module.call_gemini')
    def test_markdown_stripping_from_llm_response(self, mock_call_gemini):
        user_prompt = "Test markdown stripping"
        llm_planned_steps = [{"tool": "list_files", "args": {}}]

        # Test with ```json ... ```
        mock_call_gemini.return_value = f"```json\n{json.dumps(llm_planned_steps)}\n```"
        generated_plan = planning_module.generate_plan(user_prompt, SAMPLE_TOOLS_SPECS)
        self.assertEqual(len(generated_plan), 2) # Approval + 1 step
        self.assertEqual(generated_plan[1], llm_planned_steps[0]) # Check second step after approval

        # Test with ``` ... ```
        mock_call_gemini.return_value = f"```\n{json.dumps(llm_planned_steps)}\n```"
        generated_plan = planning_module.generate_plan(user_prompt, SAMPLE_TOOLS_SPECS)
        self.assertEqual(len(generated_plan), 2) # Approval + 1 step
        self.assertEqual(generated_plan[1], llm_planned_steps[0])


if __name__ == '__main__':
    unittest.main(argv=['first-arg-is-ignored'], exit=False)
