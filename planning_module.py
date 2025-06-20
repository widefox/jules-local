import json
import shlex # Keep shlex if any part of it might be revived for other parsing, though not used by LLM path

# Assuming gemini_client.py is in the same directory or accessible via PYTHONPATH
try:
    from gemini_client import call_gemini, MAIN_LLM_MODEL_NAME
except ImportError:
    print("planning_module.py: Warning: Could not import from gemini_client. Using mock for standalone testing/definition.")
    MAIN_LLM_MODEL_NAME = "mock-main-llm-for-planning"
    def call_gemini(model_name: str, prompt_text: str, api_key: str = None, task_type: str = "generateContent") -> str | None:
        print(f"Mock call_gemini: Model='{model_name}', Prompt='{prompt_text[:100]}...'")
        # Default mock for this context
        return json.dumps([{"tool": "message_user", "args": {"message": "Mock LLM default plan for testing."}}])

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
        "name": "generate_text_via_llm",
        "description": "Generates text (e.g., code snippets, documentation, suggestions) using a configured Lite LLM based on a given prompt.",
        "args_schema": {"prompt_for_lite_llm": "string (required) - The specific prompt for the Lite LLM."}
    },
    {
        "name": "git_diff",
        "description": "Shows the differences (git diff) in the workspace. Useful for seeing changes made by other tools. Accepts optional arguments for git diff.",
        "args_schema": {"diff_args": "string (optional) - Arguments to pass to 'git diff' (e.g., '--staged', 'HEAD~1')."}
    },
    {
        "name": "get_file_tree",
        "description": "Lists all files and directories recursively from a given start path in the workspace, providing a project file tree overview. Excludes .git directory by default.",
        "args_schema": {"start_path": "string (optional, default: '.') - The relative path from which to start listing the tree."}
    }
    # The comment about get_file_tree being pre-context might be outdated if we now want the LLM to be able to call it.
    # For this subtask, we are adding it to the list of tools the LLM knows about.
]


def generate_plan(user_prompt: str, available_tools_specs: list[dict], file_tree_context: str | None = None) -> list[dict]: # Added file_tree_context
    """
    Generates a plan by calling an LLM, using the provided tools specifications and optional file tree context.
    """
    plan = []

    tools_description_for_llm = "\n".join([
        f"- Tool: {tool['name']}\n  Description: {tool['description']}\n  Arguments (JSON schema-like): {json.dumps(tool['args_schema'])}"
        for tool in available_tools_specs if tool['name'] not in ['request_user_approval', 'message_user']
    ])

    file_context_prompt_segment = ""
    if file_tree_context and file_tree_context.strip():
        file_context_prompt_segment = f"""
The current project has the following file structure (paths are relative to the workspace root):
<file_tree>
{file_tree_context.strip()}
</file_tree>
"""
    else:
        file_context_prompt_segment = "No file tree context was provided for the current workspace."


    llm_prompt = f"""
You are an expert coding assistant. Your task is to generate a plan to fulfill the user's request.
The user's request is: "{user_prompt}"

{file_context_prompt_segment}

You have the following tools available to you. For each tool, the name, description, and a schema for its arguments are provided.
{tools_description_for_llm}

Based on the user's request and the provided context (if any), generate a plan consisting of a sequence of tool calls.
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
        if llm_response_str.strip().startswith("```json"):
            llm_response_str = llm_response_str.strip()[7:]
            if llm_response_str.strip().endswith("```"):
                 llm_response_str = llm_response_str.strip()[:-3]
        elif llm_response_str.strip().startswith("```"):
             llm_response_str = llm_response_str.strip()[3:]
             if llm_response_str.strip().endswith("```"):
                 llm_response_str = llm_response_str.strip()[:-3]
        parsed_llm_plan = json.loads(llm_response_str.strip())

        if not isinstance(parsed_llm_plan, list):
            raise ValueError("LLM response is not a JSON list.")
        for step in parsed_llm_plan:
            if not isinstance(step, dict) or "tool" not in step or "args" not in step:
                raise ValueError("Invalid step structure in LLM plan.")
            if not isinstance(step["args"], dict):
                 raise ValueError(f"Args for tool {step['tool']} must be a dictionary/object.")
            if step["tool"] != "cannot_fulfill_request" and step["tool"] not in [t["name"] for t in available_tools_specs]:
                raise ValueError(f"LLM planned to use an unknown tool: {step['tool']}")
            plan.append(step)

        if plan and plan[0]["tool"] == "cannot_fulfill_request":
            reason = plan[0]["args"].get("reason", "LLM indicated it cannot fulfill the request.")
            print(f"LLM determined it cannot fulfill the request: {reason}")
            return [{"tool": "message_user", "args": {"message": f"Planner: {reason}"}}]
    except json.JSONDecodeError as e:
        print(f"Error: Failed to parse LLM response as JSON: {e}\nLLM Response was: {llm_response_str}")
        plan = [{"tool": "message_user", "args": {"message": "Failed to parse plan from LLM."}}]
        return plan
    except ValueError as e:
        print(f"Error: Invalid plan structure from LLM: {e}\nLLM Response was: {llm_response_str}")
        plan = [{"tool": "message_user", "args": {"message": f"Invalid plan structure from LLM: {e}"}}]
        return plan

    if not plan:
        plan.append({"tool": "message_user", "args": {"message": "LLM returned an empty plan."}})
        return plan

    approval_step = {"tool": "request_user_approval", "args": {"message": "LLM has generated the following plan. Please review and approve:"}}
    return [approval_step] + plan


if __name__ == '__main__': # Updated test block
    print("Running manual tests for LLM-driven planning_module.py (with file_tree_context)...")

    # Sample tool specs for testing generate_plan directly
    test_tool_specs = DEFAULT_AVAILABLE_TOOLS_SPECS

    sample_file_tree = "file1.txt\nsubdir/\nsubdir/file2.txt\n.gitignore"

    test_prompts_with_context = [
        ("list all python files based on the tree", sample_file_tree),
        ("create a file named 'test.txt' with content 'hello there'", None), # Test without tree
        ("Summarize the project based on the file tree.", sample_file_tree),
    ]

    # Mock call_gemini for these direct tests
    original_call_gemini = call_gemini
    def mock_generate_plan_call_gemini(model_name, prompt_text, api_key=None, task_type="generateContent"):
        print(f"--- Mocked LLM Call ---")
        print(f"Model: {model_name}")
        print(f"Prompt (first 200 chars):\n{prompt_text[:200]}...")
        if "file1.txt" in prompt_text and "list all python files" in prompt_text: # Check context was in prompt
            return json.dumps([{"tool": "run_shell_command", "args": {"command_str": "find . -name '*.py'"}}])
        elif "create a file" in prompt_text:
             return json.dumps([{"tool": "write_file", "args": {"file_path": "test.txt", "content": "hello there from test"}}])
        return json.dumps([{"tool": "message_user", "args": {"message": "Mock unable to plan for this specific test prompt."}}])

    globals()['call_gemini'] = mock_generate_plan_call_gemini

    for user_prompt, tree_ctx in test_prompts_with_context:
        print(f"--- User Prompt: \"{user_prompt}\" ---")
        if tree_ctx: print(f"--- Providing File Tree Context ---\n{tree_ctx}\n-----------------------------")

        generated_plan = generate_plan(user_prompt, test_tool_specs, file_tree_context=tree_ctx)

        print("Generated Plan:")
        for i, step in enumerate(generated_plan):
            print(f"  Step {i+1}: Tool: {step['tool']}, Args: {step.get('args', {})}")
        print("-" * 20)

    globals()['call_gemini'] = original_call_gemini # Restore
    print("All planning_module.py (with file_tree_context) manual tests finished.")
