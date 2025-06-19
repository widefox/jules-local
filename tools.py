import shlex
import os
import base64

# Attempt to import from container_env for context, but provide mocks for standalone execution
try:
    from container_env import execute_in_container
except ImportError:
    print("tools.py: Warning: Could not import from container_env. Using mock for standalone review.")
    def execute_in_container(container_id: str, command_str: str, working_dir: str = "/workspace"):
        print(f"Mock execute_in_container: CID='{container_id}', CMD='{command_str}', WD='{working_dir}'")
        if "ls -A1" in command_str: return "file1.txt\ndir1", "", 0
        if "cat" in command_str: return "File content", "", 0
        if "base64 -d" in command_str: return "", "", 0 # write_file
        if "mkdir -p" in command_str: return "", "", 0 # mkdir for write_file
        return "mock stdout", "mock stderr", 1 # Default mock for other commands

# --- list_files ---
def list_files(container_id: str, path: str = ".", target_dir_in_container: str = "/workspace") -> list[str] | None:
    """Lists files in a given path within the container's target directory."""
    full_path_in_container = os.path.normpath(os.path.join(target_dir_in_container, path))
    if not full_path_in_container.startswith(target_dir_in_container):
        print(f"Error (list_files): Path '{path}' attempts to escape target directory '{target_dir_in_container}'.")
        return None

    command = f"ls -A1 {shlex.quote(full_path_in_container)}"
    # working_dir for ls should be where the path is relative to, or use absolute paths.
    # Here, full_path_in_container is absolute, so working_dir can be root or target_dir_in_container.
    stdout, stderr, exit_code = execute_in_container(container_id, command, working_dir=target_dir_in_container)

    if exit_code == 0:
        return [f for f in stdout.strip().split('\n') if f] if stdout else []
    else:
        print(f"Error listing files in '{full_path_in_container}' (container: {container_id}):\nStderr: {stderr.strip()}")
        return None

# --- read_file ---
def read_file(container_id: str, file_path: str, target_dir_in_container: str = "/workspace") -> str | None:
    """Reads content of a file from the container's target directory."""
    full_file_path_in_container = os.path.normpath(os.path.join(target_dir_in_container, file_path))
    if not full_file_path_in_container.startswith(target_dir_in_container):
        print(f"Error (read_file): File path '{file_path}' attempts to escape target directory '{target_dir_in_container}'.")
        return None

    command = f"cat {shlex.quote(full_file_path_in_container)}"
    stdout, stderr, exit_code = execute_in_container(container_id, command, working_dir=target_dir_in_container)

    if exit_code == 0:
        return stdout
    else:
        # Quieter for "No such file or directory"
        if "No such file or directory" not in stderr and "No such file or directory" not in stdout : # check both
             print(f"Error reading file '{full_file_path_in_container}' (container: {container_id}):\nStderr: {stderr.strip()}")
        return None

# --- write_file ---
def write_file(container_id: str, file_path: str, content: str, target_dir_in_container: str = "/workspace") -> bool:
    """Writes content to a file in the container's target directory."""
    full_file_path_in_container = os.path.normpath(os.path.join(target_dir_in_container, file_path))
    if not full_file_path_in_container.startswith(target_dir_in_container):
        print(f"Error (write_file): File path '{file_path}' attempts to escape target directory '{target_dir_in_container}'.")
        return False

    # Ensure parent directory exists. This is a common expectation for a "write_file" tool.
    # This command will create parent directories if they don't exist.
    parent_dir = os.path.dirname(full_file_path_in_container)
    if parent_dir and parent_dir != target_dir_in_container and not parent_dir.startswith(target_dir_in_container + "/"):
        # Check if parent_dir is not the target_dir itself and is actually a subdirectory
        # Pathological case: file_path="." -> parent_dir="." -> full_file_path_in_container="/workspace" -> parent_dir="/workspace"
        # We only want to run mkdir if parent_dir is a genuine subdirectory or a deeper path.
        # A simpler check: if parent_dir is not equal to target_dir_in_container and is not empty.
        # And ensure it's still within the target_dir_in_container for safety.
         if parent_dir.startswith(target_dir_in_container): # Ensure mkdir is also within bounds
            mkdir_cmd = f"mkdir -p {shlex.quote(parent_dir)}"
            _, mkdir_stderr, mkdir_exit_code = execute_in_container(container_id, mkdir_cmd, working_dir=target_dir_in_container)
            if mkdir_exit_code != 0:
                print(f"Error creating directory '{parent_dir}' for file '{full_file_path_in_container}' (container: {container_id}):\nStderr: {mkdir_stderr.strip()}")
                return False

    encoded_content = base64.b64encode(content.encode('utf-8')).decode('utf-8')
    # POSIX sh: `echo "$data" | base64 -d > "$filepath"` is robust
    command = f"echo '{encoded_content}' | base64 -d > {shlex.quote(full_file_path_in_container)}"
    _, stderr, exit_code = execute_in_container(container_id, command, working_dir=target_dir_in_container)

    if exit_code == 0:
        return True
    else:
        print(f"Error writing file '{full_file_path_in_container}' (container: {container_id}):\nStderr: {stderr.strip()}")
        return False

# --- run_shell_command ---
def run_shell_command(container_id: str, command_str: str, working_dir_in_container: str = "/workspace") -> tuple[str | None, str | None, int]:
    """Runs an arbitrary shell command in the container."""
    abs_working_dir = os.path.normpath(working_dir_in_container)
    if not abs_working_dir.startswith("/workspace"): # Safety check
        err_msg = f"Error (run_shell_command): Working directory '{working_dir_in_container}' must be /workspace or a subdirectory."
        print(err_msg)
        return None, err_msg, -1

    return execute_in_container(container_id, command_str, working_dir=abs_working_dir)

if __name__ == '__main__':
    print("\n--- Running basic stand-alone signature checks for tools.py ---")
    mock_container_id = "mock_container_001"

    print("\nTesting list_files...")
    list_files_args = {"path": "test_dir"}
    print(f"Calling list_files(container_id='{mock_container_id}', **{list_files_args})")
    list_files(container_id=mock_container_id, **list_files_args)

    print("\nTesting read_file...")
    read_file_args = {"file_path": "test_file.txt"}
    print(f"Calling read_file(container_id='{mock_container_id}', **{read_file_args})")
    read_file(container_id=mock_container_id, **read_file_args)

    print("\nTesting write_file...")
    write_file_args = {"file_path": "output.txt", "content": "This is a test."}
    # Simulate mkdir -p call within write_file's mock interaction if needed
    print(f"Calling write_file(container_id='{mock_container_id}', **{write_file_args})")
    write_file(container_id=mock_container_id, **write_file_args)

    write_file_args_subdir = {"file_path": "sub/output.txt", "content": "This is a test in subdir."}
    print(f"Calling write_file(container_id='{mock_container_id}', **{write_file_args_subdir})")
    write_file(container_id=mock_container_id, **write_file_args_subdir)

    print("\nTesting run_shell_command...")
    run_shell_args = {"command_str": "echo 'Hello from shell'"}
    print(f"Calling run_shell_command(container_id='{mock_container_id}', **{run_shell_args})")
    run_shell_command(container_id=mock_container_id, **run_shell_args)

    run_shell_args_custom_wd = {"command_str": "pwd", "working_dir_in_container": "/workspace/custom_dir"}
    print(f"Calling run_shell_command(container_id='{mock_container_id}', **{run_shell_args_custom_wd})")
    run_shell_command(container_id=mock_container_id, **run_shell_args_custom_wd)

    print("\n--- Stand-alone signature checks finished ---")
