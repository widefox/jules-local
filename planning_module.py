import json

# Assuming gemini_client.py is in the same directory or accessible via PYTHONPATH
try:
    from gemini_client import call_gemini, MAIN_LLM_MODEL_NAME
except ImportError:
    print("planning_module.py: Warning: Could not import from gemini_client. Using mock for standalone testing.")
    MAIN_LLM_MODEL_NAME = "mock-main-llm"
    def call_gemini(model_name: str, prompt_text: str, api_key: str = None, task_type: str = "generateContent") -> str | None:
        print(f"Mock call_gemini: Model='{model_name}', Prompt='{prompt_text[:100]}...'")
        # Simulate LLM returning a JSON plan string for specific test prompts
        if "list all python files" in prompt_text.lower():
            return json.dumps([
                {"tool": "run_shell_command", "args": {"command_str": "find . -name '*.py'"}}
            ])
        elif "create a file named 'test.txt'" in prompt_text.lower():
            return json.dumps([
                {"tool": "write_file", "args": {"file_path": "test.txt", "content": "Hello from LLM plan."}}
            ])
        elif "invalid json output" in prompt_text.lower():
            return "This is not valid JSON."
        # Default mock response for other prompts (e.g., if LLM can't make a plan)
        return json.dumps([
            {"tool": "message_user", "args": {"message": "Mock LLM could not determine a plan for this prompt."}}
        ])

# This list would be dynamically passed or imported from a central definition in a real system.
# For now, it's part of what would be passed to generate_plan.
DEFAULT_AVAILABLE_TOOLS_SPECS = [
    {
        "name": "list_files",
        "description": "Lists files and directories in a given path within the workspace.",
        "args_schema": {"path": "string (optional, default: '.') - The relative path to list."}
    },
    {
        "name": "read_file",
        "description": "Reads the content of a specified file from the workspace.",
        "args_schema": {"file_path": "string (required) - The relative path to the file."}
    },
    {
        "name": "write_file",
        "description": "Writes content to a specified file in the workspace, creating it or overwriting it.",
        "args_schema": {
            "file_path": "string (required) - The relative path to the file.",
            "content": "string (required) - The content to write."
        }
    },
    {
        "name": "run_shell_command",
        "description": "Executes an arbitrary shell command in the workspace root. Use with caution.",
        "args_schema": {"command_str": "string (required) - The shell command to execute."}
    },
    {
        "name": "git_diff",
        "description": "Shows the differences (git diff) in the workspace. Useful for seeing changes made by other tools. Accepts optional arguments for git diff.",
        "args_schema": {"diff_args": "string (optional) - Arguments to pass to 'git diff' (e.g., '--staged', 'HEAD~1')."}
    }
    # message_user and request_user_approval are special tools handled by orchestrator,
    # but planner might need to know about message_user if it wants to directly tell user something.
    # For LLM planning, usually it generates tool steps, not direct user messages.
]


def generate_plan(user_prompt: str, available_tools_specs: list[dict]) -> list[dict]:
    """
    Generates a plan by calling an LLM, using the provided tools specifications.
    """
    plan = []

    # Construct the prompt for the LLM
    # This is a critical part - prompt engineering is key.
    tools_description_for_llm = "\n".join([
        f"- Tool: {tool['name']}\n  Description: {tool['description']}\n  Arguments (JSON schema-like): {json.dumps(tool['args_schema'])}"
        for tool in available_tools_specs if tool['name'] not in ['request_user_approval', 'message_user'] # LLM shouldn't plan these itself
    ])

    llm_prompt = f"""
You are an expert coding assistant. Your task is to generate a plan to fulfill the user's request.
The user's request is: "{user_prompt}"

You have the following tools available to you. For each tool, the name, description, and a schema for its arguments are provided.
{tools_description_for_llm}

Based on the user's request, generate a plan consisting of a sequence of tool calls.
The plan should be a JSON array of objects, where each object represents a tool call and has two keys:
1. "tool": The name of the tool to call (must be one of the available tools).
2. "args": An object where keys are argument names and values are the corresponding values for that tool call, matching the tool's argument schema.

Example of a valid JSON plan:
[
  {{"tool": "list_files", "args": {{"path": "./src"}}}},
  {{"tool": "read_file", "args": {{"file_path": "./src/main.py"}}}}
]

If the user's request cannot be achieved with the available tools, or if it's ambiguous or unsafe, return a JSON array containing a single step using a conceptual 'cannot_fulfill_request' tool with a 'reason' argument.
Example: [{{"tool": "cannot_fulfill_request", "args": {{"reason": "The request is too vague."}}}}]

Now, generate the JSON plan for the user's request: "{user_prompt}"
"""

    llm_response_str = call_gemini(MAIN_LLM_MODEL_NAME, llm_prompt)

    if llm_response_str is None:
        print("Error: LLM call failed or returned no response.")
        plan.append({"tool": "message_user", "args": {"message": "LLM call failed. Cannot generate plan."}})
        return plan

    try:
        # Attempt to strip markdown code block delimiters if present
        if llm_response_str.strip().startswith("```json"):
            llm_response_str = llm_response_str.strip()[7:] # Remove ```json

            if llm_response_str.strip().endswith("```"):
                 llm_response_str = llm_response_str.strip()[:-3] # Remove ```
        elif llm_response_str.strip().startswith("```"): # For plain ```
             llm_response_str = llm_response_str.strip()[3:]
             if llm_response_str.strip().endswith("```"):
                 llm_response_str = llm_response_str.strip()[:-3]

        parsed_llm_plan = json.loads(llm_response_str.strip())

        if not isinstance(parsed_llm_plan, list):
            raise ValueError("LLM response is not a JSON list.")

        # Validate the structure of the parsed plan
        for step in parsed_llm_plan:
            if not isinstance(step, dict) or "tool" not in step or "args" not in step:
                raise ValueError("Invalid step structure in LLM plan.")
            if not isinstance(step["args"], dict):
                 raise ValueError(f"Args for tool {step['tool']} must be a dictionary/object.")
            # Check if tool is known (excluding conceptual 'cannot_fulfill_request')
            if step["tool"] != "cannot_fulfill_request" and step["tool"] not in [t["name"] for t in available_tools_specs]:
                raise ValueError(f"LLM planned to use an unknown tool: {step['tool']}")
            plan.append(step)

        # Handle the conceptual 'cannot_fulfill_request' tool
        if plan and plan[0]["tool"] == "cannot_fulfill_request":
            reason = plan[0]["args"].get("reason", "LLM indicated it cannot fulfill the request.")
            print(f"LLM determined it cannot fulfill the request: {reason}")
            return [{"tool": "message_user", "args": {"message": f"Planner: {reason}"}}]


    except json.JSONDecodeError as e:
        print(f"Error: Failed to parse LLM response as JSON: {e}")
        print(f"LLM Response was: {llm_response_str}")
        plan = [{"tool": "message_user", "args": {"message": "Failed to parse plan from LLM."}}]
        return plan
    except ValueError as e: # Custom validation errors
        print(f"Error: Invalid plan structure from LLM: {e}")
        print(f"LLM Response was: {llm_response_str}")
        plan = [{"tool": "message_user", "args": {"message": f"Invalid plan structure from LLM: {e}"}}]
        return plan


    if not plan:
        plan.append({"tool": "message_user", "args": {"message": "LLM returned an empty plan."}})
        return plan # No approval needed

    # Prepend approval step
    approval_step = {"tool": "request_user_approval", "args": {"message": "LLM has generated the following plan. Please review and approve:"}}
    return [approval_step] + plan


if __name__ == '__main__':
    print("Running manual tests for LLM-driven planning_module.py...")

    # Test cases
    test_prompts = [
        "list all python files in the current directory",
        "create a file named 'test.txt' with content 'hello there'",
        "This is an ambiguous prompt that the LLM should ideally not be able to plan for.",
        "invalid json output test" # This prompt is set up in the mock to return invalid JSON
    ]

    for user_prompt in test_prompts:
        print(f"--- User Prompt: \"{user_prompt}\" ---")
        # Use the default tool specs for testing
        generated_plan = generate_plan(user_prompt, DEFAULT_AVAILABLE_TOOLS_SPECS)

        print("Generated Plan:")
        for i, step in enumerate(generated_plan):
            print(f"  Step {i+1}: Tool: {step['tool']}, Args: {step.get('args', {})}")
        print("-" * 20)

    print("\nTesting with empty tools list (should result in error message from LLM or planner):")
    empty_tools_plan = generate_plan("List files", [])
    print("Plan with empty tools list:")
    for i, step in enumerate(empty_tools_plan):
            print(f"  Step {i+1}: Tool: {step['tool']}, Args: {step.get('args', {})}")
    print("-" * 20)

    # Verify that if LLM returns a plan with an unknown tool, it's caught
    def mock_call_gemini_unknown_tool(model_name, prompt_text, api_key=None, task_type="generateContent"):
        return json.dumps([{"tool": "unknown_tool_xyz", "args": {}}]) # LLM hallucinates a tool

    original_call_gemini = call_gemini # Save original
    globals()['call_gemini'] = mock_call_gemini_unknown_tool # Monkeypatch

    print("Testing with LLM returning an unknown tool:")
    unknown_tool_plan = generate_plan("Use an unknown tool", DEFAULT_AVAILABLE_TOOLS_SPECS)
    print("Plan with unknown tool from LLM:")
    for i, step in enumerate(unknown_tool_plan):
            print(f"  Step {i+1}: Tool: {step['tool']}, Args: {step.get('args', {})}")
    assert unknown_tool_plan[0]["tool"] == "message_user", "Should be a message_user plan for unknown tool"
    globals()['call_gemini'] = original_call_gemini # Restore

    print("All planning_module.py (LLM-driven) manual tests finished.")
