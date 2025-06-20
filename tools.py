import shlex
import os
import base64

# Imports from other modules (with mocks for standalone testing)
try:
    from container_env import execute_in_container
except ImportError:
    print("tools.py: Warning: Could not import from container_env. Using mock.")
    def execute_in_container(container_id: str, command_str: str, working_dir: str = "/workspace"):
        print(f"Mock execute_in_container: CID='{container_id}', CMD='{command_str}', WD='{working_dir}'")
        if "find" in command_str and "-print" in command_str: return "/workspace/file1.txt\n/workspace/subdir\n/workspace/subdir/file2.txt", "", 0
        if "git diff" in command_str: return "diff --git a/file.txt b/file.txt...", "", 0
        if "ls -A1" in command_str: return "file1.txt\ndir1", "", 0
        if "cat" in command_str: return "File content", "", 0
        if "base64 -d" in command_str: return "", "", 0
        if "mkdir -p" in command_str: return "", "", 0
        return "mock stdout", "mock stderr", 1
try:
    from gemini_client import call_gemini, LITE_LLM_MODEL_NAME, GEMINI_API_KEY
except ImportError:
    print("tools.py: Warning: Could not import from gemini_client. Lite LLM tool mock active.")
    LITE_LLM_MODEL_NAME = "mock-lite-llm"
    GEMINI_API_KEY = None # Ensure it's defined for the function signature
    def call_gemini(model_name: str, prompt_text: str, api_key: str = None, task_type: str = "generateContent") -> str | None:
        return f"Mock Lite LLM response to: {prompt_text}"

# --- Existing Tools (condensed signatures, full logic assumed present) ---
def list_files(container_id: str, path: str = ".", td: str = "/workspace") -> list[str] | None:
    fp=os.path.normpath(os.path.join(td,path));
    if not fp.startswith(td): print(f"Error (list_files): Path '{path}' attempts to escape target directory '{td}'."); return None
    cmd=f"ls -A1 {shlex.quote(fp)}"
    so,se,ec=execute_in_container(container_id,cmd,working_dir=td)
    return [f for f in so.strip().split('\n') if f] if ec==0 and so else (None if ec!=0 else [])

def read_file(container_id: str, fp: str, td: str = "/workspace") -> str | None:
    fpath=os.path.normpath(os.path.join(td,fp));
    if not fpath.startswith(td): print(f"Error (read_file): File path '{fp}' attempts to escape target directory '{td}'."); return None
    cmd=f"cat {shlex.quote(fpath)}"
    so,se,ec=execute_in_container(container_id,cmd,working_dir=td)
    return so if ec==0 else None

def write_file(container_id: str, fp: str, con: str, td: str = "/workspace") -> bool:
    fpath=os.path.normpath(os.path.join(td,fp));
    if not fpath.startswith(td): print(f"Error (write_file): File path '{fp}' attempts to escape target directory '{td}'."); return False
    pd=os.path.dirname(fpath)
    if pd and pd != td and fpath.startswith(td + os.sep):
        _,_,ec_mkdir = execute_in_container(container_id,f"mkdir -p {shlex.quote(pd)}",working_dir=td)
        if ec_mkdir!=0: return False
    enc_con=base64.b64encode(con.encode('utf-8')).decode('utf-8')
    cmd=f"echo '{enc_con}' | base64 -d > {shlex.quote(fpath)}"
    _,_,ec=execute_in_container(container_id,cmd,working_dir=td)
    return ec==0

def run_shell_command(container_id: str, cmd_str: str, wd: str = "/workspace") -> tuple[str|None,str|None,int]:
    awd=os.path.normpath(wd);
    if not awd.startswith("/workspace"):
        err_msg = f"Error (run_shell_command): Working directory '{wd}' must be /workspace or a subdirectory."
        print(err_msg)
        return None, err_msg, -1
    return execute_in_container(container_id,cmd_str,working_dir=awd)

def generate_text_via_llm(container_id: str, prompt_for_lite_llm: str) -> str | None:
    if not GEMINI_API_KEY: print("Error (generate_text_via_llm): GEMINI_API_KEY not configured."); return None
    if not LITE_LLM_MODEL_NAME: print("Error (generate_text_via_llm): LITE_LLM_MODEL_NAME not configured."); return None
    return call_gemini(model_name=LITE_LLM_MODEL_NAME,prompt_text=prompt_for_lite_llm)

def git_diff(container_id: str, diff_args: str = "") -> str | None:
    if ";" in diff_args or "&" in diff_args or "|" in diff_args or "`" in diff_args or "\\n" in diff_args:
        print(f"Error (git_diff): Invalid characters in diff_args: '{diff_args}'"); return None
    command = f"git diff {diff_args}".strip()
    stdout, stderr, exit_code = execute_in_container(container_id, command, working_dir="/workspace")
    if exit_code == 0: return stdout if stdout else "(No changes detected or diff output was empty)"
    else:
        if stderr: print(f"Error running 'git diff {diff_args}': Stderr: {stderr.strip()}")
        if stderr and not ("diff --git" in stdout) : return None
        return stdout if stdout else "(No changes detected or diff output was empty for non-zero exit)"

# --- New get_file_tree tool ---
def get_file_tree(container_id: str, start_path: str = ".", target_dir_in_container: str = "/workspace") -> str | None:
    """
    Lists all files and directories recursively from a given start path in the workspace.
    Output is a newline-separated string of paths.
    Excludes .git directory by default.
    """
    if os.path.isabs(start_path):
        print(f"Error (get_file_tree): start_path '{start_path}' must be relative, not absolute.")
        return None

    resolved_start_path_for_check = os.path.normpath(os.path.join(target_dir_in_container, start_path))
    if not resolved_start_path_for_check.startswith(target_dir_in_container):
        print(f"Error (get_file_tree): Resolved start_path '{resolved_start_path_for_check}' is outside target directory '{target_dir_in_container}'.")
        return None

    if start_path == ".git" or start_path.startswith(".git" + os.sep):
        print(f"Warning (get_file_tree): Attempting to list .git directory explicitly is not supported. Returning empty tree.")
        return ""

    find_target_path_in_workspace = start_path
    if find_target_path_in_workspace.endswith('/'): find_target_path_in_workspace = find_target_path_in_workspace[:-1]
    if not find_target_path_in_workspace : find_target_path_in_workspace = "."

    command = f"find {shlex.quote(find_target_path_in_workspace)} -name .git -prune -o -print"

    stdout, stderr, exit_code = execute_in_container(
        container_id,
        command,
        working_dir=target_dir_in_container
    )

    if exit_code == 0:
        if stdout:
            lines = stdout.strip().split('\n')
            # If find_target_path_in_workspace was ".", find outputs e.g. "./file.txt". Strip leading "./"
            if find_target_path_in_workspace == ".":
                lines = [line[2:] if line.startswith("./") else line for line in lines]
            # Filter out the find_target_path itself if it was "." and it's the only line
            if find_target_path_in_workspace == "." and lines == ["."]:
                return ""
            lines = [line for line in lines if line] # Filter out any other empty lines
            return "\n".join(lines)
        return ""
    else:
        print(f"Error getting file tree for '{start_path}' in '{target_dir_in_container}' (container: {container_id}):")
        if stderr: print(f"  Stderr: {stderr.strip()}")
        return None
print("tools.py: Added get_file_tree tool and updated mock execute_in_container for find.")
