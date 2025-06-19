import subprocess
import os
import time

DEFAULT_IMAGE = "python:3.9-buster"
# Alternative for testing if issues with python:3.9-slim arise, e.g. missing shell tools
# DEFAULT_IMAGE = "ubuntu:latest"

def _detect_container_runtime():
    """Detects whether Docker or Podman is available."""
    try:
        subprocess.run(["docker", "--version"], capture_output=True, check=True, text=True)
        return "docker"
    except (subprocess.CalledProcessError, FileNotFoundError):
        pass
    try:
        subprocess.run(["podman", "--version"], capture_output=True, check=True, text=True)
        return "podman"
    except (subprocess.CalledProcessError, FileNotFoundError):
        pass
    return None

CONTAINER_RUNTIME = _detect_container_runtime()

def start_persistent_container(task_id: str, workspace_code_path: str, image_name: str = DEFAULT_IMAGE) -> str | None:
    """
    Starts a persistent, detached container for a task.

    Args:
        task_id: Unique ID for the task.
        workspace_code_path: Absolute path to the task's code workspace on the host.
        image_name: The Docker/Podman image to use.

    Returns:
        The container ID/name if successful, None otherwise.
    """
    if not CONTAINER_RUNTIME:
        print("Error: No container runtime (Docker or Podman) detected.")
        return None

    container_name = f"jules_task_container_{task_id}"

    # Ensure the image is available locally, pull if not.
    # Docker/Podman usually handle this automatically on `run`, but explicit pull can give better feedback.
    try:
        print(f"Pulling image '{image_name}' if not present...")
        pull_cmd = [CONTAINER_RUNTIME, "pull", image_name]
        pull_result = subprocess.run(pull_cmd, capture_output=True, text=True, check=False)
        if pull_result.returncode != 0:
            # Some registries might return non-0 if image is already local, check stderr
            if "image is up to date" not in pull_result.stderr.lower() and \
               "already exists" not in pull_result.stderr.lower(): # Podman might say this
                print(f"Warning: Failed to explicitly pull image '{image_name}'. stdout: {pull_result.stdout}, stderr: {pull_result.stderr}")
                # Proceeding, as `run` might still succeed if image is local or error was transient.
    except Exception as e:
        print(f"Exception during image pull: {e}. Proceeding with run attempt.")


    # Command to run a detached container that sleeps indefinitely
    # Mount workspace_code_path to /workspace in the container
    # Ensure workspace_code_path is an absolute path
    abs_workspace_code_path = os.path.abspath(workspace_code_path)

    run_cmd = [
        CONTAINER_RUNTIME, "run",
        "-d",  # Detached mode
        "--name", container_name,
        "-v", f"{abs_workspace_code_path}:/workspace:rw", # Read-write mount
        image_name,
        "sleep", "infinity"  # Keep container alive
    ]

    try:
        print(f"Starting container '{container_name}' with command: {' '.join(run_cmd)}")
        result = subprocess.run(run_cmd, capture_output=True, text=True, check=True)
        container_id_or_name = result.stdout.strip()
        if not container_id_or_name: # Podman might not return ID on success for detached, name is used
             container_id_or_name = container_name
        print(f"Container '{container_id_or_name}' started successfully.")
        # Give a moment for the container to be fully up
        time.sleep(2)
        return container_id_or_name
    except subprocess.CalledProcessError as e:
        print(f"Error starting container '{container_name}': {e}")
        print(f"Stdout: {e.stdout}")
        print(f"Stderr: {e.stderr}")
        # Attempt to clean up if container was partially created with that name
        stop_and_remove_container(container_name)
        return None
    except FileNotFoundError:
        print(f"Error: {CONTAINER_RUNTIME} command not found.")
        return None


def execute_in_container(container_id_or_name: str, command_str: str, working_dir: str = "/workspace") -> tuple[str | None, str | None, int]:
    """
    Executes a shell command inside the specified running container.

    Args:
        container_id_or_name: The ID or name of the running container.
        command_str: The command string to execute (e.g., "ls -la").
        working_dir: The working directory inside the container for the command.

    Returns:
        A tuple (stdout, stderr, exit_code). stdout/stderr are None on major error.
    """
    if not CONTAINER_RUNTIME:
        print("Error: No container runtime (Docker or Podman) detected.")
        return None, "No container runtime detected.", -1

    exec_cmd = [
        CONTAINER_RUNTIME, "exec",
        "-w", working_dir,       # Set working directory
        container_id_or_name,
        "sh", "-c", command_str  # Execute command via shell
    ]

    try:
        # print(f"Executing in container '{container_id_or_name}': {' '.join(exec_cmd)}")
        result = subprocess.run(exec_cmd, capture_output=True, text=True, check=False) # check=False to get outputs even on non-zero exit
        return result.stdout, result.stderr, result.returncode
    except FileNotFoundError:
        print(f"Error: {CONTAINER_RUNTIME} command not found during exec.")
        return None, f"{CONTAINER_RUNTIME} command not found.", -1
    except Exception as e: # Catch other potential errors like container not found
        print(f"Error executing command in container '{container_id_or_name}': {e}")
        return None, str(e), -1


def stop_and_remove_container(container_id_or_name: str) -> None:
    """Stops and removes the specified container."""
    if not CONTAINER_RUNTIME:
        print("Error: No container runtime (Docker or Podman) detected for stop/remove.")
        return

    try:
        # Stop the container first
        stop_cmd = [CONTAINER_RUNTIME, "stop", container_id_or_name]
        print(f"Stopping container '{container_id_or_name}'...")
        stop_result = subprocess.run(stop_cmd, capture_output=True, text=True, check=False)
        if stop_result.returncode == 0:
            print(f"Container '{container_id_or_name}' stopped.")
        else:
            # Podman might error if already stopped, Docker might error code 1 if not found
            if "no such container" not in stop_result.stderr.lower() and \
               "already stopped" not in stop_result.stderr.lower() and \
               "does not exist" not in stop_result.stderr.lower(): # podman
                 print(f"Warning/Error stopping container '{container_id_or_name}': {stop_result.stderr}")


        # Remove the container
        rm_cmd = [CONTAINER_RUNTIME, "rm", container_id_or_name]
        print(f"Removing container '{container_id_or_name}'...")
        rm_result = subprocess.run(rm_cmd, capture_output=True, text=True, check=False)
        if rm_result.returncode == 0:
            print(f"Container '{container_id_or_name}' removed.")
        else:
            if "no such container" not in rm_result.stderr.lower() and \
               "does not exist" not in rm_result.stderr.lower(): # podman
                print(f"Warning/Error removing container '{container_id_or_name}': {rm_result.stderr}")

    except FileNotFoundError:
        print(f"Error: {CONTAINER_RUNTIME} command not found during stop/remove.")
    except Exception as e:
        print(f"An unexpected error occurred during stop/remove of container '{container_id_or_name}': {e}")


def run_env_setup_script(container_id_or_name: str, setup_script_in_container: str = "/workspace/.jules/setup.sh") -> bool:
    """
    Checks for and runs an environment setup script inside the container.
    The script path is relative to the root of the mounted workspace.
    """
    print(f"Checking for setup script at '{setup_script_in_container}' in container '{container_id_or_name}'...")

    # Check if script exists
    # Using `test -f` which is a standard shell command
    check_script_cmd = f"test -f {setup_script_in_container}"
    stdout, stderr, exit_code = execute_in_container(container_id_or_name, check_script_cmd)

    if exit_code == 0:
        print(f"Setup script found. Executing '{setup_script_in_container}'...")
        # Execute the script. Ensure it's executable or run with bash/sh.
        # Adding `set -e` to make script exit on error
        run_script_cmd = f"sh -e {setup_script_in_container}"
        script_stdout, script_stderr, script_exit_code = execute_in_container(container_id_or_name, run_script_cmd)

        print(f"--- Setup Script Output (stdout) ---")
        if script_stdout: print(script_stdout.strip())
        print(f"--- End Setup Script Output (stdout) ---")

        if script_exit_code == 0:
            print("Setup script executed successfully.")
            return True
        else:
            print(f"Error executing setup script. Exit code: {script_exit_code}")
            print(f"--- Setup Script Output (stderr) ---")
            if script_stderr: print(script_stderr.strip())
            print(f"--- End Setup Script Output (stderr) ---")
            return False
    elif exit_code == 1: # `test -f` returns 1 if file does not exist
        print("Setup script not found (or not a regular file). Skipping.")
        return True # Not an error if script doesn't exist
    else:
        print(f"Error checking for setup script. Exit code: {exit_code}. Stderr: {stderr}")
        return False


if __name__ == '__main__':
    print("Running manual tests for container_env.py...")
    if not CONTAINER_RUNTIME:
        print("Cannot run tests: No Docker or Podman detected.")
        exit(1)

    TEST_TASK_ID_CONT = "cont_test_001"

    # Create a dummy workspace for testing
    # This would normally be handled by workspace_manager.py
    dummy_workspace_path = os.path.abspath(f"./jules_workspaces/task_{TEST_TASK_ID_CONT}/code")
    dummy_setup_script_dir = os.path.join(dummy_workspace_path, ".jules")
    dummy_setup_script_path = os.path.join(dummy_setup_script_dir, "setup.sh")

    os.makedirs(dummy_setup_script_dir, exist_ok=True)
    with open(os.path.join(dummy_workspace_path, "testfile.txt"), "w") as f:
        f.write("Hello from host workspace!")
    with open(dummy_setup_script_path, "w") as f:
        f.write("#!/bin/sh\n")
        f.write("echo 'Inside setup.sh: Running setup...'\n")
        f.write("echo 'Setup script ENV_VAR_TEST=success' > /workspace/setup_output.txt\n")
        f.write("echo 'Setup script finished.'\n")
        f.write("exit 0\n")
    os.chmod(dummy_setup_script_path, 0o755) # Make it executable

    print(f"Dummy workspace created at: {dummy_workspace_path}")
    print(f"Dummy setup script at: {dummy_setup_script_path}")

    container_name = None
    try:
        print(f"--- Test: Starting container for task {TEST_TASK_ID_CONT} ---")
        container_name = start_persistent_container(TEST_TASK_ID_CONT, dummy_workspace_path)
        assert container_name is not None, "Failed to start container"
        print(f"Container '{container_name}' started for testing.")

        print(f"--- Test: Executing 'ls -la /workspace' in container ---")
        stdout, stderr, exit_code = execute_in_container(container_name, "ls -la /workspace")
        assert exit_code == 0, f"Command failed: {stderr}"
        print("ls -la /workspace stdout:")
        print(stdout)
        assert "testfile.txt" in stdout, "testfile.txt not found in workspace listing"
        assert ".jules" in stdout, ".jules directory not found in workspace listing"

        print(f"--- Test: Running environment setup script ---")
        success = run_env_setup_script(container_name)
        assert success, "Environment setup script failed or reported error"

        print(f"--- Test: Verifying setup script effect (cat /workspace/setup_output.txt) ---")
        stdout_cat, _, exit_code_cat = execute_in_container(container_name, "cat /workspace/setup_output.txt")
        assert exit_code_cat == 0, "Failed to cat setup_output.txt"
        print(f"Content of setup_output.txt: {stdout_cat.strip()}")
        assert "ENV_VAR_TEST=success" in stdout_cat, "Setup script marker not found"

        print(f"--- Test: Executing command that fails ---")
        _, stderr_fail, exit_code_fail = execute_in_container(container_name, "cat /nonexistentfile")
        assert exit_code_fail != 0, "Command should have failed but reported success"
        print(f"Stderr from failed command: {stderr_fail.strip()}")


    finally:
        if container_name:
            print(f"--- Test: Stopping and removing container '{container_name}' ---")
            stop_and_remove_container(container_name)

        # Clean up dummy workspace
        print(f"--- Test: Cleaning up dummy workspace '{os.path.dirname(dummy_workspace_path)}' ---")
        # Use shutil.rmtree to remove the parent jules_workspaces/task_cont_test_001
        if os.path.exists(os.path.dirname(dummy_workspace_path)): # Path is .../task_XYZ/code, so dirname is .../task_XYZ
             shutil.rmtree(os.path.dirname(dummy_workspace_path))

    print("Manual tests for container_env.py finished.")
