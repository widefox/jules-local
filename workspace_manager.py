import os
import shutil
import stat # For making files writable if needed during cleanup

# Define a base directory for all workspaces
BASE_WORKSPACE_DIR = "jules_workspaces"

def setup_workspace(original_repo_path: str, task_id: str) -> str | None:
    """
    Sets up a new workspace for a task.

    Args:
        original_repo_path: Path to the user's original local Git repository.
        task_id: A unique identifier for the task.

    Returns:
        The absolute path to the 'code' subdirectory within the task's workspace,
        or None if setup fails.
    """
    if not os.path.isdir(original_repo_path):
        print(f"Error: Original repository path '{original_repo_path}' not found or not a directory.")
        return None

    task_workspace_dir = os.path.join(BASE_WORKSPACE_DIR, f"task_{task_id}")
    task_code_dir = os.path.join(task_workspace_dir, "code")

    try:
        if os.path.exists(task_workspace_dir):
            print(f"Warning: Task workspace directory '{task_workspace_dir}' already exists. Removing it.")
            # Attempt to remove it robustly
            shutil.rmtree(task_workspace_dir, onerror=_on_rm_error)

        os.makedirs(task_code_dir, exist_ok=True) # exist_ok=True handles race conditions if dir was just created

        # Copy the entire content of the original repo to the task_code_dir
        # shutil.copytree by default does not copy metadata like .git directory content if it's treated as metadata
        # We need to ensure .git and other hidden files are copied if they exist.
        # Using ignore=None should copy everything.
        shutil.copytree(original_repo_path, task_code_dir, dirs_exist_ok=True, ignore=None)

        print(f"Workspace setup complete. Code copied to: {os.path.abspath(task_code_dir)}")
        return os.path.abspath(task_code_dir)

    except Exception as e:
        print(f"Error setting up workspace for task {task_id}: {e}")
        # Attempt to clean up partially created directory
        if os.path.exists(task_workspace_dir):
            try:
                shutil.rmtree(task_workspace_dir, onerror=_on_rm_error)
            except Exception as cleanup_e:
                print(f"Error during cleanup of failed workspace setup: {cleanup_e}")
        return None

def _on_rm_error(func, path, exc_info):
    """
    Error handler for shutil.rmtree.
    If the error is due to readonly files, try to make them writable and retry.
    """
    # exc_info[1] is the exception object
    if isinstance(exc_info[1], PermissionError):
        try:
            # Try to make the file writable
            os.chmod(path, stat.S_IWRITE)
            # Retry the function that failed (e.g., os.remove)
            func(path)
        except Exception as e:
            print(f"Failed to make {path} writable and remove: {e}")
    else:
        print(f"Error removing {path}: {exc_info[1]}")


def cleanup_workspace(task_id: str) -> None:
    """
    Removes the workspace directory for a given task_id.

    Args:
        task_id: The unique identifier for the task.
    """
    task_workspace_dir = os.path.join(BASE_WORKSPACE_DIR, f"task_{task_id}")

    if os.path.exists(task_workspace_dir):
        try:
            shutil.rmtree(task_workspace_dir, onerror=_on_rm_error)
            print(f"Workspace for task {task_id} cleaned up from: {task_workspace_dir}")
        except Exception as e:
            print(f"Error cleaning up workspace for task {task_id} at {task_workspace_dir}: {e}")
            print("You might need to remove it manually.")
    else:
        print(f"Workspace directory for task {task_id} not found at {task_workspace_dir}. No cleanup needed or already cleaned up.")

if __name__ == '__main__':
    # Quick test (manual)
    print("Running a quick manual test for workspace_manager.py...")
    TEST_TASK_ID = "test_001"
    TEST_REPO_PATH = "./temp_test_repo" # Create this directory manually with some files for testing

    # Create a dummy repo for testing
    if os.path.exists(TEST_REPO_PATH):
        shutil.rmtree(TEST_REPO_PATH, onerror=_on_rm_error)
    os.makedirs(os.path.join(TEST_REPO_PATH, ".git")) # Simulate .git dir
    os.makedirs(os.path.join(TEST_REPO_PATH, "subdir"))
    with open(os.path.join(TEST_REPO_PATH, "file1.txt"), "w") as f:
        f.write("hello")
    with open(os.path.join(TEST_REPO_PATH, ".hiddenfile"), "w") as f:
        f.write("hidden")
    with open(os.path.join(TEST_REPO_PATH, "subdir", "file2.txt"), "w") as f:
        f.write("world")

    print(f"Attempting to set up workspace for task '{TEST_TASK_ID}' using repo '{TEST_REPO_PATH}'...")
    workspace_path = setup_workspace(TEST_REPO_PATH, TEST_TASK_ID)

    if workspace_path:
        print(f"Workspace successfully created at: {workspace_path}")
        print("Contents of workspace:")
        for root, dirs, files in os.walk(workspace_path):
            for name in files:
                print(os.path.join(root, name))
            for name in dirs:
                print(os.path.join(root, name) + "/")

        print(f"Listing contents of base workspace dir '{BASE_WORKSPACE_DIR}':")
        if os.path.exists(BASE_WORKSPACE_DIR):
            for item in os.listdir(BASE_WORKSPACE_DIR):
                print(os.path.join(BASE_WORKSPACE_DIR, item))
        else:
            print(f"Base directory {BASE_WORKSPACE_DIR} not found.")


        print(f"Attempting to clean up workspace for task '{TEST_TASK_ID}'...")
        cleanup_workspace(TEST_TASK_ID)

        print(f"Checking if task workspace dir '{os.path.join(BASE_WORKSPACE_DIR, f"task_{TEST_TASK_ID}")}' exists after cleanup: {os.path.exists(os.path.join(BASE_WORKSPACE_DIR, f"task_{TEST_TASK_ID}"))}")

    else:
        print("Workspace setup failed.")

    # Clean up the dummy repo
    if os.path.exists(TEST_REPO_PATH):
        shutil.rmtree(TEST_REPO_PATH, onerror=_on_rm_error)
    print("Manual test finished.")
