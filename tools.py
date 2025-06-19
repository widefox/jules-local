import shlex # For escaping paths and content for shell commands
import os # For path joining, though paths are primarily handled in container

# Import functions from container_env
# Assuming container_env.py is in the same directory or accessible via PYTHONPATH
try:
    from container_env import execute_in_container
except ImportError:
    # This might happen if running this script directly without the full project context
    # For the subtask, it should be fine as files are co-located.
    print("Warning: Could not import from container_env. This is expected if running tools.py standalone for testing without full project setup.")
    # Define a mock for basic testing if needed, or rely on subtask environment
    def execute_in_container(container_id: str, command_str: str, working_dir: str = "/workspace"):
        print(f"Mock execute_in_container: CID='{container_id}', CMD='{command_str}', WD='{working_dir}'")
        if "ls" in command_str and "non_existent_dir_for_error_test" not in command_str:
            return "file1.txt\ndir1\n.hiddenfile", "", 0
        if "cat" in command_str and "non_existent_file.txt" not in command_str:
            return "File content here.", "", 0
        if "echo" in command_str and ">" in command_str: # for write_file
             return "", "", 0
        if command_str == "true": # for run_shell_command success test
            return "Shell command success", "", 0
        return "", "Mock error", 1


def list_files(container_id: str, path: str = ".", target_dir_in_container: str = "/workspace") -> list[str] | None:
    """
    Lists files and directories in a given path within the container's target directory.

    Args:
        container_id: The ID or name of the container.
        path: The path relative to target_dir_in_container (e.g., ".", "subdir", "subdir/another").
        target_dir_in_container: The base directory in the container (e.g., "/workspace").

    Returns:
        A list of file/directory names, or None on error.
    """
    # Sanitize path to prevent escaping target_dir_in_container
    # os.path.join will handle joining safely if path starts with / it uses that as root
    # but here path is relative to target_dir_in_container
    full_path_in_container = os.path.normpath(os.path.join(target_dir_in_container, path))

    # Basic check to ensure the path doesn't try to escape the main workspace too obviously
    # This isn't a perfect security measure but a deterrent.
    if not full_path_in_container.startswith(target_dir_in_container):
        print(f"Error: Path '{path}' attempts to escape target directory '{target_dir_in_container}'.")
        return None

    # Using ls -A to list all entries including hidden ones, but not . and ..
    # Using ls -1 to list one file per line for easier parsing
    command = f"ls -A1 {shlex.quote(full_path_in_container)}"
    stdout, stderr, exit_code = execute_in_container(container_id, command, working_dir=target_dir_in_container)

    if exit_code == 0:
        if stdout:
            return stdout.strip().split('\n')
        return [] # Empty directory
    else:
        print(f"Error listing files in '{full_path_in_container}' (in container '{container_id}'):")
        if stderr: print(f"Stderr: {stderr.strip()}")
        return None


def read_file(container_id: str, file_path: str, target_dir_in_container: str = "/workspace") -> str | None:
    """
    Reads the content of a file from the container's target directory.

    Args:
        container_id: The ID or name of the container.
        file_path: The path of the file relative to target_dir_in_container.
        target_dir_in_container: The base directory in the container.

    Returns:
        The file content as a string, or None if an error occurs or file not found.
    """
    full_file_path_in_container = os.path.normpath(os.path.join(target_dir_in_container, file_path))
    if not full_file_path_in_container.startswith(target_dir_in_container):
        print(f"Error: File path '{file_path}' attempts to escape target directory '{target_dir_in_container}'.")
        return None

    command = f"cat {shlex.quote(full_file_path_in_container)}"
    stdout, stderr, exit_code = execute_in_container(container_id, command, working_dir=target_dir_in_container)

    if exit_code == 0:
        return stdout
    else:
        # Don't print stderr if it's just "cat: ...: No such file or directory" for a common case
        if "No such file or directory" not in stderr:
             print(f"Error reading file '{full_file_path_in_container}' (in container '{container_id}'):")
             if stderr: print(f"Stderr: {stderr.strip()}")
        return None


def write_file(container_id: str, file_path: str, content: str, target_dir_in_container: str = "/workspace") -> bool:
    """
    Writes content to a file in the container's target directory.
    This will overwrite the file if it exists, or create it if it doesn't.

    Args:
        container_id: The ID or name of the container.
        file_path: The path of the file relative to target_dir_in_container.
        content: The string content to write to the file.
        target_dir_in_container: The base directory in the container.

    Returns:
        True on success, False on error.
    """
    full_file_path_in_container = os.path.normpath(os.path.join(target_dir_in_container, file_path))
    if not full_file_path_in_container.startswith(target_dir_in_container):
        print(f"Error: File path '{file_path}' attempts to escape target directory '{target_dir_in_container}'.")
        return False

    # Create directory if it doesn't exist.
    # dirname_cmd = f"mkdir -p {shlex.quote(os.path.dirname(full_file_path_in_container))}"
    # _, _, mkdir_exit_code = execute_in_container(container_id, dirname_cmd, working_dir=target_dir_in_container)
    # if mkdir_exit_code != 0:
    #     print(f"Error creating directory for file '{full_file_path_in_container}' (in container '{container_id}')")
    #     return False
    # The above mkdir logic is good, but for a tool, the user of the tool should ensure the path exists or use a different tool to create dirs.
    # Let's keep write_file focused on writing. If the dir doesn't exist, the shell redirect will fail.

    # Using sh -c 'echo "$CONTENT" > "$FILEPATH"'
    # Need to be careful with escaping content and filepath for the shell.
    # shlex.quote is good for single arguments. For content within echo, it's more complex.
    # A more robust way is to pass content via stdin to `tee` or `dd`.
    # Example with tee: sh -c 'cat > "$1"' -- "$FILEPATH" (and pass content via stdin to subprocess)
    # For simplicity in this MVP using execute_in_container which takes a command string:
    # Base64 encoding content can help avoid most shell interpretation issues.
    import base64
    encoded_content = base64.b64encode(content.encode('utf-8')).decode('utf-8')
    command = f"echo '{encoded_content}' | base64 -d > {shlex.quote(full_file_path_in_container)}"

    # Alternative: using printf for more robust echo-like behavior
    # command = f"printf '%s' {shlex.quote(content)} > {shlex.quote(full_file_path_in_container)}"
    # However, content itself can break this if it contains shell metacharacters not handled by one shlex.quote.

    _, stderr, exit_code = execute_in_container(container_id, command, working_dir=target_dir_in_container)

    if exit_code == 0:
        return True
    else:
        print(f"Error writing file '{full_file_path_in_container}' (in container '{container_id}'):")
        if stderr: print(f"Stderr: {stderr.strip()}")
        return False


def run_shell_command(container_id: str, command_str: str, working_dir_in_container: str = "/workspace") -> tuple[str | None, str | None, int]:
    """
    Runs an arbitrary shell command in the container's working directory.

    Args:
        container_id: The ID or name of the container.
        command_str: The shell command to execute.
        working_dir_in_container: The working directory inside the container for this command.

    Returns:
        A tuple (stdout, stderr, exit_code). stdout/stderr are None on major error.
    """
    # Ensure working_dir_in_container is within /workspace or is /workspace itself
    # This is a basic safety check.
    abs_working_dir = os.path.normpath(working_dir_in_container)
    if not abs_working_dir.startswith("/workspace"):
        print(f"Error: Shell command working directory '{working_dir_in_container}' is outside '/workspace'. Denying.")
        return None, "Working directory must be /workspace or a subdirectory.", -1

    return execute_in_container(container_id, command_str, working_dir=abs_working_dir)


if __name__ == '__main__':
    # This test block assumes a running container and the `execute_in_container` function.
    # For local testing, you'd need to manually set up a container or use a mock `execute_in_container`.
    # The subtask environment will actually run this against the real `container_env.py`.

    print("Running manual tests for tools.py (using mocked execute_in_container)...")
    TEST_CONTAINER_ID = "test_tools_container_001"

    print("\n--- Test: list_files (success) ---")
    files = list_files(TEST_CONTAINER_ID, path=".")
    assert files == ["file1.txt", "dir1", ".hiddenfile"], f"Expected specific files, got {files}"
    print(f"list_files output: {files}")

    print("\n--- Test: list_files (empty dir or error) ---")
    # Mock execute_in_container for this specific path to simulate empty or error
    original_execute = execute_in_container
    def mock_execute_empty_ls(cid, cmd, wd):
        if "ls -A1 /workspace/empty_dir" in cmd: return "", "", 0
        if "ls -A1 /workspace/non_existent_dir_for_error_test" in cmd: return "", "ls: cannot access '/workspace/non_existent_dir_for_error_test': No such file or directory", 2 # typical ls error code
        return original_execute(cid, cmd, wd)
    globals()['execute_in_container'] = mock_execute_empty_ls

    files_empty = list_files(TEST_CONTAINER_ID, path="empty_dir")
    assert files_empty == [], f"Expected empty list for empty_dir, got {files_empty}"
    print(f"list_files for empty_dir: {files_empty}")

    files_error = list_files(TEST_CONTAINER_ID, path="non_existent_dir_for_error_test")
    assert files_error is None, f"Expected None for error case, got {files_error}"
    print(f"list_files for non_existent_dir_for_error_test: {files_error}")
    globals()['execute_in_container'] = original_execute # Restore

    print("\n--- Test: read_file (success) ---")
    content = read_file(TEST_CONTAINER_ID, "some_file.txt")
    assert content == "File content here.", f"Expected 'File content here.', got '{content}'"
    print(f"read_file output: '{content}'")

    print("\n--- Test: read_file (file not found) ---")
    content_not_found = read_file(TEST_CONTAINER_ID, "non_existent_file.txt")
    assert content_not_found is None, f"Expected None for non_existent_file.txt, got '{content_not_found}'"
    print(f"read_file for non_existent_file.txt: {content_not_found}")

    print("\n--- Test: write_file (success) ---")
    success = write_file(TEST_CONTAINER_ID, "new_file.txt", "Hello, Jules!")
    assert success, "write_file should have returned True"
    print(f"write_file result: {success}")

    print("\n--- Test: write_file (path escaping attempt) ---")
    success_escape = write_file(TEST_CONTAINER_ID, "../outside_workspace.txt", "Attempted escape")
    assert not success_escape, "write_file should have failed for path escape attempt"
    print(f"write_file escape attempt result: {success_escape}")


    print("\n--- Test: run_shell_command (success) ---")
    stdout, stderr, exit_code = run_shell_command(TEST_CONTAINER_ID, "true") # 'true' is a command that does nothing and exits 0
    assert exit_code == 0, f"run_shell_command 'true' failed. Stderr: {stderr}"
    assert stdout == "Shell command success" # From mock
    print(f"run_shell_command 'true': stdout='{stdout}', stderr='{stderr}', exit_code={exit_code}")

    print("\n--- Test: run_shell_command (failure) ---")
    stdout_fail, stderr_fail, exit_code_fail = run_shell_command(TEST_CONTAINER_ID, "false") # 'false' exits 1
    assert exit_code_fail != 0, "run_shell_command 'false' should have failed"
    assert stderr_fail == "Mock error" # From mock
    print(f"run_shell_command 'false': stdout='{stdout_fail}', stderr='{stderr_fail}', exit_code={exit_code_fail}")

    print("\n--- Test: run_shell_command (restricted working directory) ---")
    _, stderr_wd, exit_code_wd = run_shell_command(TEST_CONTAINER_ID, "pwd", working_dir_in_container="/etc")
    assert exit_code_wd == -1, "run_shell_command should fail for non-/workspace working_dir"
    assert "Working directory must be /workspace or a subdirectory." in stderr_wd
    print(f"run_shell_command with bad working_dir: stderr='{stderr_wd}', exit_code={exit_code_wd}")


    print("\nAll tools.py manual tests finished (using mocks).")
