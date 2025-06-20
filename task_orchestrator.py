import uuid
import os
import sys # For input()

# Import from other modules
from workspace_manager import setup_workspace, cleanup_workspace
from container_env import (
    start_persistent_container,
    stop_and_remove_container,
    run_env_setup_script,
    CONTAINER_RUNTIME
)
# Import the new planning module and the tools module
from planning_module import generate_plan, DEFAULT_AVAILABLE_TOOLS_SPECS # Use the specs from planner
import tools # Import the whole module to use getattr and the new get_file_tree

# Use the tool specs defined in the planning_module
ORCHESTRATOR_AVAILABLE_TOOLS_SPECS = DEFAULT_AVAILABLE_TOOLS_SPECS

def run_task(repo_path: str, prompt: str):
    """
    Orchestrates the setup, planning, execution, and cleanup for a single task.
    """
    if not CONTAINER_RUNTIME:
        print("Task Orchestrator: Cannot run task. No container runtime (Docker or Podman) detected.")
        return

    task_id = str(uuid.uuid4().hex) # Use hex for a cleaner task_id string
    print(f"Task Orchestrator: Starting task '{task_id}'...")
    print(f"  Repo Path: {repo_path}")
    print(f"  Prompt: \"{prompt}\"")

    workspace_code_path = None
    container_id_or_name = None
    plan_approved = False

    try:
        print(f"\nTask Orchestrator: Setting up workspace for task '{task_id}'...")
        workspace_code_path = setup_workspace(original_repo_path=repo_path, task_id=task_id)
        if not workspace_code_path:
            print(f"Task Orchestrator: Failed to set up workspace. Aborting task '{task_id}'.")
            return

        print(f"Task Orchestrator: Workspace created at '{workspace_code_path}'")

        print(f"\nTask Orchestrator: Starting container for task '{task_id}'...")
        container_id_or_name = start_persistent_container(task_id=task_id, workspace_code_path=workspace_code_path)
        if not container_id_or_name:
            print(f"Task Orchestrator: Failed to start container. Aborting task '{task_id}'.")
            return

        print(f"Task Orchestrator: Container '{container_id_or_name}' started.")

        print(f"\nTask Orchestrator: Checking for and running environment setup script for task '{task_id}'...")
        setup_success = run_env_setup_script(container_id_or_name=container_id_or_name)
        if not setup_success:
            print(f"Task Orchestrator: Environment setup script failed or reported an error. Task may misbehave.")
        else:
            print(f"Task Orchestrator: Environment setup script completed (or not found).")

        # --- NEW: Get file tree context ---
        print(f"\nTask Orchestrator: Retrieving file tree for context...")
        file_tree_string = tools.get_file_tree(container_id=container_id_or_name, start_path=".")
        if file_tree_string is None:
            print("Task Orchestrator: Warning: Could not retrieve file tree. Planning will proceed without it.")
            file_tree_string = "" # Ensure it's a string for the planner
        elif not file_tree_string.strip():
            print("Task Orchestrator: Workspace appears to be empty or file tree is empty.")
        else:
            print(f"Task Orchestrator: File tree retrieved (first 200 chars):\n{file_tree_string[:200]}...")
        # --- END NEW ---

        print(f"\nTask Orchestrator: Generating plan for prompt: \"{prompt}\"")
        # Pass file_tree_string to generate_plan
        plan = generate_plan(prompt, ORCHESTRATOR_AVAILABLE_TOOLS_SPECS, file_tree_context=file_tree_string)
        if not plan:
            print("Task Orchestrator: No plan generated. Terminating task.")
            return

        print(f"\nTask Orchestrator: --- Plan Review and Execution (Task ID: {task_id}) ---")
        active_plan_steps = []
        for i, step in enumerate(plan):
            tool_name = step.get("tool")
            tool_args = step.get("args", {})
            if tool_name == "request_user_approval":
                print(f"\n{tool_args.get('message', 'A plan has been generated:')}")
                active_plan_steps = plan[i+1:]
                if not active_plan_steps: print("Plan is empty after approval step."); plan_approved = False; break
                print("Proposed Plan:")
                for plan_step_idx, plan_step in enumerate(active_plan_steps):
                    print(f"  Step {plan_step_idx + 1}: Tool: {plan_step.get('tool')}, Arguments: {plan_step.get('args', {})}")
                try:
                    user_response = input("\nApprove plan? (yes/no): ")
                    if user_response.lower() == "yes": plan_approved = True; print("Plan approved by user. Starting execution...")
                    else: print("Plan rejected by user. Terminating task."); plan_approved = False # Explicitly set plan_approved to False
                except EOFError: print("No user input available. Assuming rejection."); plan_approved = False
                break
            elif tool_name == "message_user":
                print(f"Message from planner: {tool_args.get('message', 'No message.')}")
                plan_approved = False; break

        if plan_approved and active_plan_steps:
            for step_idx, step_to_execute in enumerate(active_plan_steps):
                tool_name = step_to_execute.get("tool")
                tool_args_dict = step_to_execute.get("args", {})
                print(f"\nExecuting Step {step_idx + 1}/{len(active_plan_steps)}: Tool: {tool_name}, Args: {tool_args_dict}")
                tool_function = getattr(tools, tool_name, None)
                if tool_function:
                    try:
                        result = tool_function(container_id=container_id_or_name, **tool_args_dict)
                        print(f"Tool '{tool_name}' output/result:")
                        if isinstance(result, tuple) and len(result) == 3 and isinstance(result[2], int):
                            stdout, stderr, exit_code = result
                            if stdout: print(f"  Stdout:\n{stdout.strip()}")
                            if stderr: print(f"  Stderr:\n{stderr.strip()}")
                            print(f"  Exit Code: {exit_code}")
                            if exit_code != 0: print(f"Tool '{tool_name}' error (exit code {exit_code}). Stopping."); break
                        elif isinstance(result, bool):
                            print(f"  Success: {result}")
                            if not result: print(f"Tool '{tool_name}' failed. Stopping."); break
                        elif result is None and tool_name in ["read_file", "list_files", "git_diff", "get_file_tree", "generate_text_via_llm"]:
                            print(f"  Tool '{tool_name}' failed or found nothing. Stopping."); break
                        elif isinstance(result, list): print(f"  Items: {result}")
                        else: print(f"  {result}")
                    except Exception as e: print(f"Error during tool '{tool_name}': {e}"); break
                else: print(f"Error: Tool '{tool_name}' not found. Stopping."); break
            print("\n--- Plan execution finished. ---")
        elif not active_plan_steps and not plan_approved: pass # Message already printed
        else:
            if not plan_approved and any(s.get("tool") == "request_user_approval" for s in plan): # Check if approval was even part of the plan
                 print("Plan not executed: non-approval or empty active plan.")
            elif plan_approved and not active_plan_steps : print("Plan approved, but no actionable steps found to execute.")

        # Display Diffs (after plan execution)
        if container_id_or_name:
            print(f"\nTask Orchestrator: Displaying changes in workspace for task '{task_id}'...")
            diff_output = tools.git_diff(container_id=container_id_or_name)
            if diff_output is not None:
                print("--- Git Diff ---"); print(diff_output); print("--- End Git Diff ---")
            else: print("Could not retrieve git diff or an error occurred.")

    except Exception as e:
        print(f"Task Orchestrator: An unexpected error occurred during task '{task_id}': {e}")
    finally:
        print(f"\nTask Orchestrator: Cleaning up for task '{task_id}'...")
        if container_id_or_name:
            print(f"  Stopping and removing container '{container_id_or_name}'...")
            stop_and_remove_container(container_id_or_name)
        else: print("  No container to stop/remove.")
        if workspace_code_path:
            print(f"  Cleaning up workspace for task '{task_id}'...")
            cleanup_workspace(task_id)
        else: print("  No workspace to clean up.")
        print(f"Task Orchestrator: Task '{task_id}' finished and cleaned up.")

if __name__ == '__main__':
    # Need to import shutil and subprocess for the test setup here
    import shutil
    import subprocess
    print("\n--- Running manual test for task_orchestrator (with get_file_tree integration) ---")
    TEST_ORCH_REPO_P4_1 = "./temp_orch_repo_p4_1"
    if os.path.exists(TEST_ORCH_REPO_P4_1): shutil.rmtree(TEST_ORCH_REPO_P4_1)
    os.makedirs(TEST_ORCH_REPO_P4_1)
    with open(os.path.join(TEST_ORCH_REPO_P4_1, "main.py"), "w") as f: f.write("print('Hello')")
    with open(os.path.join(TEST_ORCH_REPO_P4_1, "README.md"), "w") as f: f.write("# Test Readme")

    # Initialize as git repo for workspace_manager to clone
    subprocess.run(["git", "init"], cwd=TEST_ORCH_REPO_P4_1, capture_output=True, text=True)
    subprocess.run(["git", "add", "."], cwd=TEST_ORCH_REPO_P4_1, capture_output=True, text=True)
    subprocess.run(["git", "commit", "-m", "initial"], cwd=TEST_ORCH_REPO_P4_1, capture_output=True, text=True)

    if CONTAINER_RUNTIME:
        print("\n--- Test: Prompt that might use file tree context ---")
        print("EXPECT to be asked for approval. Type 'yes'. (Note: Test may hang if input not mocked/provided)")
        # This test will use the mock LLM from planning_module.py's header if gemini_client isn't fully configured
        run_task(TEST_ORCH_REPO_P4_1, "Based on the file tree, suggest a new Python file to add.")
    else:
        print("Skipping orchestrator test as no container runtime is detected.")

    if os.path.exists(TEST_ORCH_REPO_P4_1): shutil.rmtree(TEST_ORCH_REPO_P4_1)
    print("--- Manual task_orchestrator (with get_file_tree) test finished ---")
