import uuid
import os
import sys # For input()

# Import from other modules
from workspace_manager import setup_workspace, cleanup_workspace
from container_env import (
    start_persistent_container,
    stop_and_remove_container,
    run_env_setup_script,
    CONTAINER_RUNTIME,
    execute_in_container # Needed for message_user if it's to be container-interactive
)
# Import the new planning module and the tools module
from planning_module import generate_plan, DEFAULT_AVAILABLE_TOOLS_SPECS as PLANNER_DEFAULT_TOOLS_SPECS
import tools # Import the whole module to use getattr

# The available tools specs will be passed directly to the planner.
# ORCHESTRATOR_AVAILABLE_TOOLS_SPECS = PLANNER_DEFAULT_TOOLS_SPECS # This line becomes redundant if used directly

def run_task(repo_path: str, prompt: str):
    """
    Orchestrates the setup, planning, execution, and cleanup for a single task.
    """
    if not CONTAINER_RUNTIME:
        print("Task Orchestrator: Cannot run task. No container runtime (Docker or Podman) detected.")
        return

    task_id = str(uuid.uuid4())
    print(f"Task Orchestrator: Starting task '{task_id}'...")
    print(f"  Repo Path: {repo_path}")
    print(f"  Prompt: \"{prompt}\"")

    workspace_code_path = None
    container_id_or_name = None
    plan_approved = False # Initialize plan_approved

    try:
        # 1. Setup workspace
        print(f"\nTask Orchestrator: Setting up workspace for task '{task_id}'...")
        workspace_code_path = setup_workspace(original_repo_path=repo_path, task_id=task_id)
        if not workspace_code_path:
            print(f"Task Orchestrator: Failed to set up workspace. Aborting task '{task_id}'.")
            return

        print(f"Task Orchestrator: Workspace created at '{workspace_code_path}'")

        # 2. Start persistent container
        print(f"\nTask Orchestrator: Starting container for task '{task_id}'...")
        container_id_or_name = start_persistent_container(task_id=task_id, workspace_code_path=workspace_code_path)
        if not container_id_or_name:
            print(f"Task Orchestrator: Failed to start container. Aborting task '{task_id}'.")
            return

        print(f"Task Orchestrator: Container '{container_id_or_name}' started.")

        # 3. Run environment setup script
        print(f"\nTask Orchestrator: Checking for and running environment setup script for task '{task_id}'...")
        setup_success = run_env_setup_script(container_id_or_name=container_id_or_name)
        if not setup_success:
            print(f"Task Orchestrator: Environment setup script failed or reported an error. Task may misbehave.")
        else:
            print(f"Task Orchestrator: Environment setup script completed (or not found).")

        # 4. Generate Plan
        print(f"\nTask Orchestrator: Generating plan for prompt: \"{prompt}\"")
        # Pass the tool specifications to the planner
        plan = generate_plan(prompt, PLANNER_DEFAULT_TOOLS_SPECS)
        if not plan:
            print("Task Orchestrator: No plan generated. Terminating task.")
            return

        # 5. Plan Approval & Execution
        print(f"\nTask Orchestrator: --- Plan Review and Execution (Task ID: {task_id}) ---")

        active_plan_steps = [] # Steps to execute after approval

        for i, step in enumerate(plan):
            tool_name = step.get("tool")
            tool_args = step.get("args", {})

            if tool_name == "request_user_approval":
                print(f"\n{tool_args.get('message', 'A plan has been generated:')}")
                # Store the rest of the plan for display
                active_plan_steps = plan[i+1:]
                if not active_plan_steps:
                    print("Plan is empty after approval step.")
                    plan_approved = False # No steps to execute
                    break

                print("Proposed Plan:")
                for plan_step_idx, plan_step in enumerate(active_plan_steps):
                    print(f"  Step {plan_step_idx + 1}: Tool: {plan_step.get('tool')}, Arguments: {plan_step.get('args', {})}")

                try:
                    user_response = input("\nApprove plan? (yes/no): ")
                    if user_response.lower() == "yes":
                        plan_approved = True
                        print("Plan approved by user. Starting execution...")
                    else:
                        print("Plan rejected by user. Terminating task.")
                        # No need to break, loop for approval step will end, and subsequent steps won't run as plan_approved is False
                except EOFError: # Handle cases where input might not be available (e.g. CI)
                    print("No user input available to approve plan. Assuming rejection.")
                    plan_approved = False
                break # Approval step processed, exit this loop to proceed based on plan_approved

            elif tool_name == "message_user": # Handle message_user directly if it's the only thing in a plan
                print(f"Message from planner: {tool_args.get('message', 'No message.')}")
                # This typically means an error in parsing or no actionable plan, so no further execution.
                plan_approved = False # Ensure no further steps are run
                break


        if plan_approved and active_plan_steps:
            for step_idx, step_to_execute in enumerate(active_plan_steps):
                tool_name = step_to_execute.get("tool")
                tool_args_dict = step_to_execute.get("args", {})

                print(f"\nExecuting Step {step_idx + 1}/{len(active_plan_steps)}: Tool: {tool_name}, Args: {tool_args_dict}")

                tool_function = getattr(tools, tool_name, None)

                if tool_function:
                    try:
                        # Pass container_id and unpack tool_args_dict
                        result = tool_function(container_id=container_id_or_name, **tool_args_dict)

                        print(f"Tool '{tool_name}' output/result:")
                        if isinstance(result, tuple) and len(result) == 3 and isinstance(result[2], int): # run_shell_command like
                            stdout, stderr, exit_code = result
                            if stdout: print(f"  Stdout:\n{stdout.strip()}")
                            if stderr: print(f"  Stderr:\n{stderr.strip()}")
                            print(f"  Exit Code: {exit_code}")
                            if exit_code != 0:
                                print(f"Tool '{tool_name}' reported an error (exit code {exit_code}). Stopping plan execution.")
                                break
                        elif isinstance(result, bool): # write_file like
                            print(f"  Success: {result}")
                            if not result:
                                print(f"Tool '{tool_name}' reported failure. Stopping plan execution.")
                                break
                        elif result is None and tool_name in ["read_file", "list_files"]: # read_file or list_files error
                            print(f"  Tool '{tool_name}' failed or found nothing (returned None). Stopping plan execution.")
                            break
                        elif isinstance(result, list): # list_files success
                             print(f"  Files: {result}")
                        else: # read_file success or other types
                            print(f"  {result}")

                    except Exception as e:
                        print(f"Error during execution of tool '{tool_name}': {e}")
                        break # Stop plan execution on tool error
                else:
                    print(f"Error: Tool '{tool_name}' not found in tools module. Stopping plan execution.")
                    break # Unknown tool
            print("\n--- Plan execution finished. ---")
        elif not active_plan_steps and not plan_approved : # Covers cases where plan was empty or only message_user
             pass # Message already printed by message_user or "Plan is empty"
        else: # Not approved or no active steps after approval request
            if not plan_approved: # Explicitly check if it was due to rejection or no approval step
                if any(s.get("tool") == "request_user_approval" for s in plan): # if approval was requested
                     print("Plan not executed due to non-approval or empty active plan.")
                # else: message_user handled it or "No plan generated"
            else: # Approved but active_plan_steps was empty
                 print("Plan approved, but no actionable steps found to execute.")


    except Exception as e:
        print(f"Task Orchestrator: An unexpected error occurred during task '{task_id}': {e}")
    finally:
        # 6. Display Diffs
        if plan_approved and container_id_or_name:  # Only show diff if plan was approved and ran
            print(f"\nTask Orchestrator: Displaying changes in workspace for task '{task_id}'...")
            diff_output = tools.git_diff(container_id=container_id_or_name) # Using tools.git_diff
            if diff_output is not None:
                print("--- Git Diff ---")
                print(diff_output)
                print("--- End Git Diff ---")
            else:
                print("Could not retrieve git diff or an error occurred displaying diff.")

        print(f"\nTask Orchestrator: Cleaning up for task '{task_id}'...")
        if container_id_or_name:
            print(f"  Stopping and removing container '{container_id_or_name}'...")
            stop_and_remove_container(container_id_or_name)
        else:
            print("  No container to stop/remove.")

        if workspace_code_path:
            print(f"  Cleaning up workspace for task '{task_id}'...")
            cleanup_workspace(task_id)
        else:
            print("  No workspace to clean up (or setup failed before workspace path was set).")

        print(f"Task Orchestrator: Task '{task_id}' finished and cleaned up.")

# No changes needed to jules_local_cli.py as it already calls run_task.
# The main test block for task_orchestrator.py should be updated or run manually with new prompts.

if __name__ == '__main__':
    print("\n--- Running manual test for task_orchestrator (Phase 2) ---")
    # Create a dummy repo for orchestrator to use
    TEST_ORCH_REPO_P2 = "./temp_orch_repo_p2"
    if os.path.exists(TEST_ORCH_REPO_P2):
        import shutil
        shutil.rmtree(TEST_ORCH_REPO_P2) # Clear previous test
    os.makedirs(TEST_ORCH_REPO_P2)
    with open(os.path.join(TEST_ORCH_REPO_P2, "initial_readme.txt"), "w") as f:
        f.write("This is a test readme for Phase 2 orchestrator.")

    dummy_setup_dir_p2 = os.path.join(TEST_ORCH_REPO_P2, ".jules")
    os.makedirs(dummy_setup_dir_p2, exist_ok=True)
    with open(os.path.join(dummy_setup_dir_p2, "setup.sh"), "w") as f:
        f.write("#!/bin/sh\necho 'Orchestrator Phase 2 dummy setup.sh running'\n")

    if CONTAINER_RUNTIME:
        print("\n--- Test 1: Default plan (prompt: 'Show me the files') ---")
        print("EXPECT to be asked for approval. Type 'yes'.")
        run_task(TEST_ORCH_REPO_P2, "Show me the files")

        print("\n--- Test 2: Specific command (prompt: 'CREATE_FILE new_doc.txt \"Sample content for new doc\"') ---")
        print("EXPECT to be asked for approval. Type 'yes'.")
        run_task(TEST_ORCH_REPO_P2, "CREATE_FILE new_doc.txt \"Sample content for new doc\"")

        print("\n--- Test 3: Read the created file (prompt: 'READ_FILE new_doc.txt') ---")
        print("EXPECT to be asked for approval. Type 'yes'.")
        run_task(TEST_ORCH_REPO_P2, "READ_FILE new_doc.txt")

        print("\n--- Test 4: Plan rejection (prompt: 'LIST_FILES .') ---")
        print("EXPECT to be asked for approval. Type 'no'.")
        run_task(TEST_ORCH_REPO_P2, "LIST_FILES .")

        print("\n--- Test 5: Invalid command format (prompt: 'CREATE_FILE oops_only_one_arg') ---")
        # This should result in a message_user plan, no approval needed.
        run_task(TEST_ORCH_REPO_P2, "CREATE_FILE oops_only_one_arg")

    else:
        print("Skipping orchestrator Phase 2 tests as no container runtime is detected.")

    if os.path.exists(TEST_ORCH_REPO_P2):
        import shutil
        try:
            shutil.rmtree(TEST_ORCH_REPO_P2)
        except Exception as e:
            print(f"Note: Manual cleanup of {TEST_ORCH_REPO_P2} failed in test: {e}")
    print("--- Manual task_orchestrator (Phase 2) test finished ---")
