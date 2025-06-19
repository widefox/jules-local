import shlex
import os
import base64

# Imports from other modules (with mocks for standalone testing)
try:
    from container_env import execute_in_container, DEFAULT_IMAGE
except ImportError:
    print("tools.py: Warning: Could not import from container_env. Using mock.")
    DEFAULT_IMAGE = "mock_image_for_tools_py"
    def execute_in_container(container_id: str, command_str: str, working_dir: str = "/workspace"):
        print(f"Mock execute_in_container: CID='{container_id}', CMD='{command_str}', WD='{working_dir}'")
        if "git diff" in command_str: return "diff --git a/file.txt b/file.txt\n--- a/file.txt\n+++ b/file.txt\n@@ -1 +1 @@\n-old content\n+new content", "", 0
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
    GEMINI_API_KEY = None
    def call_gemini(model_name: str, prompt_text: str, api_key: str = None, task_type: str = "generateContent") -> str | None:
        return f"Mock Lite LLM response to: {prompt_text}"

# Existing tools (condensed, assuming they are fine)
def list_files(container_id: str, path: str = ".", td: str = "/workspace") -> list[str] | None:
    fp=os.path.normpath(os.path.join(td,path)); # assert fp.startswith(td); # Basic check, not foolproof security
    if not fp.startswith(td): print(f"Warning: list_files path {fp} may be outside {td}"); return None
    cmd=f"ls -A1 {shlex.quote(fp)}"
    so,se,ec=execute_in_container(container_id,cmd,working_dir=td)
    return [f for f in so.strip().split('\n') if f] if ec==0 and so else (None if ec!=0 else [])
def read_file(container_id: str, fp: str, td: str = "/workspace") -> str | None:
    fpath=os.path.normpath(os.path.join(td,fp)); # assert fpath.startswith(td);
    if not fpath.startswith(td): print(f"Warning: read_file path {fpath} may be outside {td}"); return None
    cmd=f"cat {shlex.quote(fpath)}"
    so,se,ec=execute_in_container(container_id,cmd,working_dir=td)
    return so if ec==0 else None
def write_file(container_id: str, fp: str, con: str, td: str = "/workspace") -> bool:
    fpath=os.path.normpath(os.path.join(td,fp)); # assert fpath.startswith(td);
    if not fpath.startswith(td): print(f"Warning: write_file path {fpath} may be outside {td}"); return False
    pd=os.path.dirname(fpath)
    if pd and pd != td and fpath.startswith(td + os.sep): # Check if parent_dir is not the target_dir itself and is actually a subdirectory
        _,_,ec_mkdir = execute_in_container(container_id,f"mkdir -p {shlex.quote(pd)}",working_dir=td)
        if ec_mkdir!=0: return False
    enc_con=base64.b64encode(con.encode('utf-8')).decode('utf-8')
    cmd=f"echo '{enc_con}' | base64 -d > {shlex.quote(fpath)}"
    _,_,ec=execute_in_container(container_id,cmd,working_dir=td)
    return ec==0
def run_shell_command(container_id: str, cmd_str: str, wd: str = "/workspace") -> tuple[str|None,str|None,int]:
    awd=os.path.normpath(wd); # assert awd.startswith("/workspace")
    if not awd.startswith("/workspace"): print(f"Warning: run_shell_command wd {awd} not in /workspace"); return None, "Working dir error", -1
    return execute_in_container(container_id,cmd_str,working_dir=awd)
def generate_text_via_llm(cid: str, p: str) -> str | None: # Renamed args for condensation
    if not GEMINI_API_KEY or not LITE_LLM_MODEL_NAME: return None
    return call_gemini(model_name=LITE_LLM_MODEL_NAME,prompt_text=p)

# New git_diff tool
def git_diff(container_id: str, diff_args: str = "") -> str | None:
    """Runs 'git diff' in the container's workspace and returns the output."""
    if ";" in diff_args or "&" in diff_args or "|" in diff_args or "`" in diff_args or "\n" in diff_args: # Basic safety
        print(f"Error (git_diff): Invalid characters in diff_args: '{diff_args}'")
        return None
    command = f"git diff {diff_args}".strip()
    stdout, stderr, exit_code = execute_in_container(container_id, command, working_dir="/workspace")
    if exit_code == 0:
        return stdout if stdout else "(No changes detected or diff output was empty)"
    else:
        if stderr: print(f"Error running 'git diff {diff_args}': Stderr: {stderr.strip()}")
        # If git diff exits with 1 (changes found when using --exit-code) but no actual error in stderr,
        # it's still valid output.
        if stderr and not ("diff --git" in stdout) : return None # If actual error in stderr and no diff output
        return stdout if stdout else "(No changes detected or diff output was empty for non-zero exit)"
