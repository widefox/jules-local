import os
import shutil
import stat
import subprocess # For running git commands

BASE_WORKSPACE_DIR = "jules_workspaces"

def _run_git_command(command_parts: list[str], working_dir: str | None = None) -> tuple[bool, str, str]:
    """Helper to run Git commands."""
    try:
        process = subprocess.run(["git"] + command_parts, capture_output=True, text=True, check=False, cwd=working_dir)
        if process.returncode == 0:
            return True, process.stdout.strip(), process.stderr.strip()
        else:
            return False, process.stdout.strip(), process.stderr.strip()
    except FileNotFoundError: # git command not found
        return False, "", "Git command not found. Please ensure Git is installed and in your PATH."
    except Exception as e:
        return False, "", f"An unexpected error occurred while running git command: {e}"

def setup_workspace(original_repo_path: str, task_id: str, branch_name: str = None) -> str | None:
    """
    Sets up a new workspace for a task by cloning a Git repository.

    Args:
        original_repo_path: Path to the user's original local Git repository (can be a local path or a URL).
        task_id: A unique identifier for the task.
        branch_name: Optional specific branch to clone. If None, clones default branch.

    Returns:
        The absolute path to the cloned repository within the task's workspace,
        or None if setup fails.
    """
    task_workspace_dir = os.path.join(BASE_WORKSPACE_DIR, f"task_{task_id}")
    # Cloned repo will be directly inside task_workspace_dir, not a 'code' subdirectory like before for simplicity with git.
    # Or, we can clone into a 'code' subdir: os.path.join(task_workspace_dir, "code")
    # Let's keep the 'code' subdir for consistency with potential non-git workspaces if ever needed.
    cloned_repo_target_path = os.path.join(task_workspace_dir, "code")


    if os.path.exists(task_workspace_dir):
        print(f"Warning: Task workspace directory '{task_workspace_dir}' already exists. Removing it.")
        shutil.rmtree(task_workspace_dir, onerror=_on_rm_error)

    try:
        os.makedirs(cloned_repo_target_path, exist_ok=True)
    except Exception as e:
        print(f"Error creating workspace directory '{cloned_repo_target_path}': {e}")
        return None

    # Construct git clone command
    clone_cmd_parts = ["clone"]
    if branch_name:
        clone_cmd_parts.extend(["-b", branch_name])

    # original_repo_path can be a URL or a local path. Git handles both.
    # If it's a local path, git clone might create a copy that shares hardlinks for efficiency.
    # For true isolation, if original_repo_path is local, one might copy it to a temp location then clone from there,
    # or use `git clone --no-hardlinks file:///path/to/local/repo`
    # For now, direct clone is fine.
    clone_cmd_parts.extend([original_repo_path, cloned_repo_target_path])

    print(f"Cloning repository from '{original_repo_path}' into '{cloned_repo_target_path}'...")
    success, stdout, stderr = _run_git_command(clone_cmd_parts)

    if not success:
        print(f"Error cloning repository for task {task_id}:")
        if stdout: print(f"  Git stdout: {stdout}")
        if stderr: print(f"  Git stderr: {stderr}")
        # Attempt to clean up partially created directory
        if os.path.exists(task_workspace_dir):
            shutil.rmtree(task_workspace_dir, onerror=_on_rm_error)
        return None

    print(f"Repository cloned successfully into: {os.path.abspath(cloned_repo_target_path)}")

    # --- Stretch Goal: Create and checkout a new task-specific branch ---
    new_task_branch = f"jules_task/{task_id}"
    print(f"Attempting to create and checkout new branch '{new_task_branch}' in '{cloned_repo_target_path}'...")

    # `git checkout -b <new_branch_name>`
    checkout_b_success, co_b_stdout, co_b_stderr = _run_git_command(
        ["checkout", "-b", new_task_branch],
        working_dir=cloned_repo_target_path
    )
    if not checkout_b_success:
        print(f"Warning: Failed to create and checkout new branch '{new_task_branch}'.")
        if co_b_stdout: print(f"  Git stdout: {co_b_stdout}")
        if co_b_stderr: print(f"  Git stderr: {co_b_stderr}")
        print("Proceeding on the cloned branch.")
        # Not returning None here, as cloning itself was successful.
    else:
        print(f"Successfully created and switched to branch '{new_task_branch}'.")
    # --- End Stretch Goal ---

    return os.path.abspath(cloned_repo_target_path)


def _on_rm_error(func, path, exc_info):
    """Error handler for shutil.rmtree to make files writable if PermissionError."""
    if isinstance(exc_info[1], PermissionError):
        try:
            os.chmod(path, stat.S_IWRITE)
            func(path) # Retry the original function (e.g., os.remove)
        except Exception as e:
            print(f"Failed to make {path} writable and remove: {e}")
    else:
        print(f"Error removing {path} during rmtree: {exc_info[1]}")


def cleanup_workspace(task_id: str) -> None:
    """Removes the workspace directory for a given task_id."""
    task_workspace_dir = os.path.join(BASE_WORKSPACE_DIR, f"task_{task_id}")
    if os.path.exists(task_workspace_dir):
        try:
            # Git might create read-only files in .git/objects, so onerror is important
            shutil.rmtree(task_workspace_dir, onerror=_on_rm_error)
            print(f"Workspace for task {task_id} cleaned up from: {task_workspace_dir}")
        except Exception as e:
            print(f"Error cleaning up workspace for task {task_id} at {task_workspace_dir}: {e}")
    else:
        print(f"Workspace for task {task_id} not found at {task_workspace_dir} (already cleaned or setup failed).")


if __name__ == '__main__':
    print("Running manual tests for workspace_manager.py (Git-aware)...")

    # --- Setup for creating a temporary bare repository to clone from ---
    # This is more robust for testing git clone than relying on an external repo.
    test_source_repo_path = os.path.abspath("./temp_source_git_repo")
    test_bare_repo_path = os.path.abspath("./temp_source_git_repo.git") # Path for bare repo

    def setup_local_bare_repo():
        if os.path.exists(test_source_repo_path):
            shutil.rmtree(test_source_repo_path, onerror=_on_rm_error)
        if os.path.exists(test_bare_repo_path):
            shutil.rmtree(test_bare_repo_path, onerror=_on_rm_error)

        os.makedirs(test_source_repo_path, exist_ok=True)
        _run_git_command(["init"], working_dir=test_source_repo_path)
        with open(os.path.join(test_source_repo_path, "README.md"), "w") as f:
            f.write("Test repo for cloning.")
        _run_git_command(["add", "README.md"], working_dir=test_source_repo_path)
        _run_git_command(["commit", "-m", "Initial commit"], working_dir=test_source_repo_path)

        # Create another branch for testing branch cloning
        _run_git_command(["branch", "feature-branch"], working_dir=test_source_repo_path)
        _run_git_command(["checkout", "feature-branch"], working_dir=test_source_repo_path)
        with open(os.path.join(test_source_repo_path, "feature.txt"), "w") as f:
            f.write("This is on the feature branch.")
        _run_git_command(["add", "feature.txt"], working_dir=test_source_repo_path)
        _run_git_command(["commit", "-m", "Add feature file"], working_dir=test_source_repo_path)
        _run_git_command(["checkout", "main"], working_dir=test_source_repo_path) # Switch back to main/master

        # Create a bare clone to act as the "remote"
        _run_git_command(["clone", "--bare", test_source_repo_path, test_bare_repo_path])
        print(f"Temporary bare repository created at {test_bare_repo_path}")

    def cleanup_local_bare_repo():
        if os.path.exists(test_source_repo_path):
            shutil.rmtree(test_source_repo_path, onerror=_on_rm_error)
        if os.path.exists(test_bare_repo_path):
            shutil.rmtree(test_bare_repo_path, onerror=_on_rm_error)
        print("Cleaned up temporary bare repository and source.")

    # Check if git is available before running tests that depend on it
    git_available, _, _ = _run_git_command(["--version"])
    if not git_available:
        print("Git command not found. Skipping Git-dependent tests in workspace_manager.")
    else:
        setup_local_bare_repo()

        TEST_TASK_ID_GIT = "git_test_001"
        print(f"\n--- Test 1: Cloning default branch from '{test_bare_repo_path}' ---")
        ws_path_default = setup_workspace(test_bare_repo_path, TEST_TASK_ID_GIT)
        assert ws_path_default is not None, "Workspace setup (default branch) failed"
        assert os.path.exists(os.path.join(ws_path_default, "README.md")), "README.md not found in default branch clone"
        assert not os.path.exists(os.path.join(ws_path_default, "feature.txt")), "feature.txt should not be in default branch clone"
        # Check if new branch was created
        _, current_branch_stdout, _ = _run_git_command(["rev-parse", "--abbrev-ref", "HEAD"], working_dir=ws_path_default)
        assert f"jules_task/{TEST_TASK_ID_GIT}" == current_branch_stdout, f"Not on task branch. Current: {current_branch_stdout}"

        print(f"Default branch clone successful. Current branch in workspace: {current_branch_stdout}")
        cleanup_workspace(TEST_TASK_ID_GIT)

        TEST_TASK_ID_GIT_BRANCH = "git_test_002"
        print(f"\n--- Test 2: Cloning specific branch 'feature-branch' from '{test_bare_repo_path}' ---")
        ws_path_feature = setup_workspace(test_bare_repo_path, TEST_TASK_ID_GIT_BRANCH, branch_name="feature-branch")
        assert ws_path_feature is not None, "Workspace setup (feature branch) failed"
        assert os.path.exists(os.path.join(ws_path_feature, "README.md")), "README.md not found in feature branch clone" # Assuming feature branch also has README.md
        assert os.path.exists(os.path.join(ws_path_feature, "feature.txt")), "feature.txt not found in feature branch clone"
        _, current_branch_feature_stdout, _ = _run_git_command(["rev-parse", "--abbrev-ref", "HEAD"], working_dir=ws_path_feature)
        assert f"jules_task/{TEST_TASK_ID_GIT_BRANCH}" == current_branch_feature_stdout, f"Not on task branch for feature clone. Current: {current_branch_feature_stdout}"

        print(f"Feature branch clone successful. Current branch in workspace: {current_branch_feature_stdout}")
        cleanup_workspace(TEST_TASK_ID_GIT_BRANCH)

        cleanup_local_bare_repo()

    print("\nManual tests for workspace_manager.py (Git-aware) finished.")
