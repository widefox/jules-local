import uuid
import os # For path joining

# Import from other modules
from workspace_manager import setup_workspace, cleanup_workspace
from container_env import (
    start_persistent_container,
    stop_and_remove_container,
    run_env_setup_script,
    CONTAINER_RUNTIME # To inform user if no runtime
)
from tools import list_files # Only using list_files for this initial step

def run_task(repo_path: str, prompt: str):
    """
    Orchestrates the setup, (basic) execution, and cleanup for a single task.
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

    try:
        # 1. Setup workspace
        print(f"Task Orchestrator: Setting up workspace for task '{task_id}'...")
        workspace_code_path = setup_workspace(original_repo_path=repo_path, task_id=task_id)
        if not workspace_code_path:
            print(f"Task Orchestrator: Failed to set up workspace. Aborting task '{task_id}'.")
            return # No cleanup needed for workspace_manager as it handles its own partial cleanup

        print(f"Task Orchestrator: Workspace created at '{workspace_code_path}'")

        # 2. Start persistent container
        print(f"Task Orchestrator: Starting container for task '{task_id}'...")
        container_id_or_name = start_persistent_container(task_id=task_id, workspace_code_path=workspace_code_path)
        if not container_id_or_name:
            print(f"Task Orchestrator: Failed to start container. Aborting task '{task_id}'.")
            return # Workspace cleanup will be handled in finally

        print(f"Task Orchestrator: Container '{container_id_or_name}' started.")

        # 3. Run environment setup script
        print(f"Task Orchestrator: Checking for and running environment setup script for task '{task_id}'...")
        # Assuming default path /workspace/.jules/setup.sh
        setup_success = run_env_setup_script(container_id_or_name=container_id_or_name)
        if not setup_success:
            print(f"Task Orchestrator: Environment setup script failed or reported an error. Continuing task, but it may misbehave.")
        else:
            print(f"Task Orchestrator: Environment setup script completed (or not found).")

        # 4. Placeholder for Planning & Execution
        print(f"\nTask Orchestrator: --- Placeholder for Planning & Execution (Task ID: {task_id}) ---")
        print(f"  Container ID/Name: {container_id_or_name}")

        print(f"  Listing files in workspace root ('/workspace') using 'tools.list_files':")
        files_in_workspace = list_files(container_id=container_id_or_name, path=".") # path="." relative to /workspace
        if files_in_workspace is not None:
            if files_in_workspace:
                for item in files_in_workspace:
                    print(f"    - {item}")
            else:
                print("    (Workspace root is empty)")
        else:
            print("    Error listing files in workspace.")

        print("\n  Planning & Full Execution with other tools is not yet implemented in Phase 1.")
        print(f"Task Orchestrator: --- End of Placeholder ---")

    except Exception as e:
        print(f"Task Orchestrator: An unexpected error occurred during task '{task_id}': {e}")
    finally:
        print(f"\nTask Orchestrator: Cleaning up for task '{task_id}'...")
        if container_id_or_name:
            print(f"  Stopping and removing container '{container_id_or_name}'...")
            stop_and_remove_container(container_id_or_name)
        else:
            print("  No container to stop/remove.")

        if workspace_code_path: # workspace_code_path is path to .../code, cleanup needs task_id
            print(f"  Cleaning up workspace for task '{task_id}'...")
            cleanup_workspace(task_id) # cleanup_workspace constructs path from task_id
        else:
            print("  No workspace to clean up (or setup failed before workspace path was set).")

        print(f"Task Orchestrator: Task '{task_id}' finished and cleaned up.")

if __name__ == '__main__':
    print("\n--- Running manual test for task_orchestrator ---")
    # Create a dummy repo for orchestrator to use
    TEST_ORCH_REPO = "./temp_orch_repo"
    if not os.path.exists(TEST_ORCH_REPO):
        os.makedirs(TEST_ORCH_REPO)
    with open(os.path.join(TEST_ORCH_REPO, "main.py"), "w") as f:
        f.write("print('Hello from main.py')")

    # Create a dummy setup script
    dummy_setup_dir = os.path.join(TEST_ORCH_REPO, ".jules")
    if not os.path.exists(dummy_setup_dir):
        os.makedirs(dummy_setup_dir)
    with open(os.path.join(dummy_setup_dir, "setup.sh"), "w") as f:
        f.write("#!/bin/sh\necho 'Orchestrator dummy setup.sh running'\n")

    if CONTAINER_RUNTIME: # Only run if docker/podman is available
        run_task(TEST_ORCH_REPO, "Test prompt for orchestrator")
    else:
        print("Skipping orchestrator test as no container runtime is detected.")

    # Clean up dummy repo (workspace manager should clean its own copies)
    if os.path.exists(TEST_ORCH_REPO):
        import shutil
        # shutil.rmtree(TEST_ORCH_REPO) # workspace_manager has its own cleanup error handler
        # For this test, workspace_manager's _on_rm_error might not be available if not imported fully
        # For simplicity, just remove. If this fails, it's not critical for subtask.
        try:
            shutil.rmtree(TEST_ORCH_REPO)
        except Exception:
            print(f"Note: Manual cleanup of {TEST_ORCH_REPO} might have failed in test block.")
    print("--- Manual task_orchestrator test finished ---")
