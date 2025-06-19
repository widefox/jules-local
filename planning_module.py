import shlex # For parsing command-like prompts

AVAILABLE_TOOLS = ['list_files', 'read_file', 'write_file', 'run_shell_command', 'request_user_approval', 'message_user']

def generate_plan(prompt: str, available_tools: list[str]) -> list[dict]:
    """
    Generates a very simple plan based on the prompt.
    In this MVP, it looks for specific keywords at the start of the prompt.
    """
    plan = []
    parsed_successfully = False

    # Ensure tools used in hardcoded plans are available
    def check_tool_availability(tool_name):
        if tool_name not in available_tools:
            print(f"Warning: Tool '{tool_name}' for planned step is not in available_tools list. Will be skipped.")
            return False
        return True

    try:
        parts = shlex.split(prompt) # Use shlex to handle simple quoted arguments
        command = ""
        if parts:
            command = parts[0].upper() # Command is case-insensitive

        if command == "CREATE_FILE":
            if len(parts) == 3:
                file_path = parts[1]
                content = parts[2]
                if check_tool_availability("write_file"):
                    plan.append({"tool": "write_file", "args": {"file_path": file_path, "content": content}})
                parsed_successfully = True
            else:
                if check_tool_availability("message_user"):
                    plan.append({"tool": "message_user", "args": {"message": "Error: CREATE_FILE format is: CREATE_FILE <filepath> <content_string>"}})
                return plan

        elif command == "LIST_FILES":
            path_to_list = "." # Default to current directory
            if len(parts) > 1:
                path_to_list = parts[1]
            if check_tool_availability("list_files"):
                plan.append({"tool": "list_files", "args": {"path": path_to_list}})
            parsed_successfully = True

        elif command == "READ_FILE":
            if len(parts) == 2:
                file_path = parts[1]
                if check_tool_availability("read_file"):
                    plan.append({"tool": "read_file", "args": {"file_path": file_path}})
                parsed_successfully = True
            else:
                if check_tool_availability("message_user"):
                    plan.append({"tool": "message_user", "args": {"message": "Error: READ_FILE format is: READ_FILE <filepath>"}})
                return plan

        elif command == "RUN_SHELL":
            if len(parts) > 1:
                command_string = " ".join(parts[1:]) # Re-join the rest as the command string
                if check_tool_availability("run_shell_command"):
                    plan.append({"tool": "run_shell_command", "args": {"command_str": command_string}})
                parsed_successfully = True
            else:
                if check_tool_availability("message_user"):
                    plan.append({"tool": "message_user", "args": {"message": "Error: RUN_SHELL format is: RUN_SHELL <command_string>"}})
                return plan

    except Exception as e:
        print(f"Error parsing prompt: {e}")
        if check_tool_availability("message_user"):
            plan.append({"tool": "message_user", "args": {"message": f"Error parsing prompt: {e}"}})
        return plan

    if not parsed_successfully:
        print(f"Prompt not understood or no specific command found. Generating default plan.")
        # Default plan: List files, then try to read README.md
        if check_tool_availability("list_files"):
            plan.append({"tool": "list_files", "args": {"path": "."}})
        if check_tool_availability("read_file"):
            plan.append({"tool": "read_file", "args": {"file_path": "README.md"}})

    if not plan:
        if check_tool_availability("message_user"):
            plan.append({"tool": "message_user", "args": {"message": "Could not generate any plan based on the prompt or defaults, or required tools are unavailable."}})
        return plan

    is_message_only_plan = all(p.get("tool") == "message_user" for p in plan)

    if not is_message_only_plan and check_tool_availability("request_user_approval"):
        approval_step = {"tool": "request_user_approval", "args": {"message": "Please review and approve the following plan:"}}
        final_plan = [approval_step] + plan
        return final_plan
    else:
        return plan


if __name__ == '__main__':
    print("Running manual tests for planning_module.py...")

    # Test cases
    prompts_and_expected_tools = [
        ("CREATE_FILE /tmp/test.txt \"Hello world\"", ["request_user_approval", "write_file"]),
        ("LIST_FILES subdir", ["request_user_approval", "list_files"]),
        ("LIST_FILES", ["request_user_approval", "list_files"]),
        ("READ_FILE /etc/hosts", ["request_user_approval", "read_file"]),
        ("RUN_SHELL ls -la /tmp", ["request_user_approval", "run_shell_command"]),
        ("RUN_SHELL echo 'Hello World'", ["request_user_approval", "run_shell_command"]),
        ("UNKNOWN_COMMAND", ["request_user_approval", "list_files", "read_file"]),
        ("", ["request_user_approval", "list_files", "read_file"]),
        ("CREATE_FILE /tmp/test.txt", ["message_user"]),
        ("READ_FILE", ["message_user"]),
        ("RUN_SHELL", ["message_user"]),
    ]

    for p, expected_tools_in_plan in prompts_and_expected_tools:
        print(f"--- Prompt: \"{p}\" ---")
        generated_plan = generate_plan(p, AVAILABLE_TOOLS)
        print("Generated Plan:")
        actual_tools_in_plan = []
        for i, step in enumerate(generated_plan):
            print(f"  Step {i+1}: Tool: {step['tool']}, Args: {step['args']}")
            actual_tools_in_plan.append(step['tool'])

        assert actual_tools_in_plan == expected_tools_in_plan, f"Test failed for prompt '{p}'. Expected tools {expected_tools_in_plan}, got {actual_tools_in_plan}"
        print("Test passed for this prompt.")
        print("-" * 20)

    print("Testing with a tool missing from available_tools list:")
    limited_tools = ['read_file', 'request_user_approval', 'message_user'] # list_files and write_file are missing

    plan_missing_tool_specific = generate_plan("LIST_FILES .", limited_tools)
    print("Plan for 'LIST_FILES .' when 'list_files' tool is unavailable:")
    # Expected: default plan because the specific command's tool is missing.
    # Default plan is list_files (skip) then read_file.
    for i, step in enumerate(plan_missing_tool_specific):
        print(f"  Step {i+1}: Tool: {step['tool']}, Args: {step['args']}")
    actual_tools_missing_specific = [step['tool'] for step in plan_missing_tool_specific]
    assert actual_tools_missing_specific == ['request_user_approval', 'read_file'], \
        f"Expected plan with missing specific tool to be ['request_user_approval', 'read_file'], got {actual_tools_missing_specific}"

    plan_default_missing_tool = generate_plan("UNKNOWN PROMPT", limited_tools)
    print("Plan for 'UNKNOWN PROMPT' when 'list_files' is unavailable:")
    # Expected: approval + read_file for README.md
    actual_tools_default_missing = [step['tool'] for step in plan_default_missing_tool]
    assert actual_tools_default_missing == ['request_user_approval', 'read_file'], \
        f"Expected default plan with missing tool to be ['request_user_approval', 'read_file'], got {actual_tools_default_missing}"

    print("All planning_module.py manual tests finished.")
