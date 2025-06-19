# Jules Local - MVP (Re-envisioned)

## Overview

Jules Local is a command-line tool that aims to simulate some of the core concepts of the experimental Google coding agent, Jules (as described at [jules.google/docs](https://jules.google/docs)), but for execution on your local Linux machine.

This version focuses on establishing a framework for:
*   Managing local workspaces based on user-provided Git repositories.
*   Running tasks within isolated Docker/Podman containers.
*   Providing a basic set of "tools" for interacting with the code within the container (e.g., list files, read/write files, execute shell commands).
*   A CLI to initiate tasks.

**Note:** This is a significant redesign from any previous simple script runner. It does **not** yet implement the full AI planning or complex task execution capabilities of the cloud-based Jules. It's a foundational framework.

## High-Level Architecture

*   **CLI (`jules_local_cli.py`):** Parses user commands and orchestrates the workflow.
*   **Workspace Manager (`workspace_manager.py`):** Manages temporary local copies of user repositories for tasks.
*   **Container Environment (`container_env.py`):** Handles Docker/Podman interactions, including starting persistent containers, executing commands within them, and managing their lifecycle.
*   **Tooling System (`tools.py`):** Provides a defined set of actions (tools) that can be performed within the containerized workspace (e.g., file operations, command execution).
*   **Task Orchestrator (`task_orchestrator.py`):** Manages the lifecycle of a single task, from setup to cleanup, including the (future) planning and execution phases.

## Phase 1 Details & Conventions

### Workspace Directory (`jules_workspaces`)

When you run a task, Jules Local creates a temporary workspace for it. These workspaces are located in a directory named `jules_workspaces` in the same location where you run the `jules_local_cli.py` command. Each task gets its own subdirectory, like `jules_workspaces/task_<unique_task_id>/code/`, which contains a copy of your specified repository. These workspaces are automatically cleaned up (deleted) after the task finishes or if an error occurs.

### Environment Setup Script (`.jules/setup.sh`)

If your project requires specific dependencies or setup steps to run correctly (e.g., installing packages), you can create a shell script named `setup.sh` inside a `.jules` directory at the root of your repository (i.e., `my_project/.jules/setup.sh`).

If this script exists, Jules Local will execute it within the container after setting up the workspace and before running any other tools or task logic. The script is run with `sh -e`, so it will exit immediately if any command fails. Output from this script (stdout and stderr) will be printed to your terminal.

Example `.jules/setup.sh`:
```shell
#!/bin/sh
echo "Setting up the environment..."
# Example: Install Python packages if a requirements.txt exists
if [ -f "/workspace/requirements.txt" ]; then
    pip install -r /workspace/requirements.txt
fi
echo "Environment setup complete."
```

### Available Tools (Phase 1)

In this phase, a basic set of tools has been implemented that operate within the containerized workspace (`/workspace` inside the container). These tools are used internally by the orchestrator and will be the building blocks for future planning and execution logic:

*   **`list_files(path=".")`**: Lists files and directories at the given relative path within `/workspace`.
*   **`read_file(file_path)`**: Reads the content of the specified file (relative to `/workspace`).
*   **`write_file(file_path, content)`**: Writes the given string content to the specified file (relative to `/workspace`), overwriting it if it exists.
*   **`run_shell_command(command_str)`**: Executes an arbitrary shell command string within the `/workspace` directory in the container.

The current task orchestration performs a `list_files` at the root of your project within the container as a demonstration.

## Planning and Execution (Phase 2 Initial)

Jules Local now incorporates a basic planning and execution mechanism. When you provide a task prompt, the agent attempts to generate a plan, which is a sequence of tool calls. You will be asked to approve this plan before any actions are taken within the containerized workspace.

### Simple Prompt Commands

In this initial phase, the planner understands a few simple, keyword-based commands at the beginning of your prompt:

*   **`LIST_FILES [path]`**: Generates a plan to list files and directories.
    *   Example: `LIST_FILES .`
    *   Example: `LIST_FILES ./my_subdir`
*   **`READ_FILE <filepath>`**: Generates a plan to read the content of the specified file.
    *   Example: `READ_FILE my_project/main.py`
*   **`CREATE_FILE <filepath> "<content>"`**: Generates a plan to create (or overwrite) a file with the given content.
    *   Example: `CREATE_FILE new_notes.txt "This is a new note."`
    *   *(Note: Ensure content with spaces is quoted)*
*   **`RUN_SHELL "<command_string>"`**: Generates a plan to execute the given shell command.
    *   Example: `RUN_SHELL "ls -la /workspace/data"`
    *   Example: `RUN_SHELL "python --version"`
    *   *(Note: Ensure the command string is quoted if it contains spaces or special characters)*

If the prompt does not match one of these commands, or if it's empty, a default plan will be generated (e.g., listing files in the current directory and attempting to read `README.md`).
If a recognized command has incorrect arguments (e.g., `CREATE_FILE` missing content), you'll receive a message instead of a plan for approval.

### Plan Approval

Before any tools are executed, the generated plan will be displayed, and you will be prompted to approve it by typing `yes` or `no`. This gives you control over what actions Jules Local will perform.

Example of a plan display:
```
Please review and approve the following plan:
Proposed Plan:
  Step 1: Tool: list_files, Arguments: {'path': '.'}
  Step 2: Tool: read_file, Arguments: {'file_path': 'README.md'}

Approve plan? (yes/no):
```

## Basic Usage (Phase 1)

To initiate a task:

```bash
python3 jules_local_cli.py task <path_to_your_local_git_repo> "<your_task_prompt>"
```

Example:
```bash
python3 jules_local_cli.py task ./my-project "Add a basic README.md file to this project."
```

This will (in future steps):
1. Set up a workspace by copying `./my-project`.
2. Start a container with this workspace mounted.
3. (Future) Generate and ask for approval of a plan.
4. (Future) Execute the plan using tools.
5. Clean up the workspace and container.

## Future Phases
The current simple planner is rule-based. Future development will focus on:
*   More sophisticated prompt understanding and plan generation, potentially leveraging AI/LLM capabilities if feasible in a local context or by defining more complex task decomposition strategies.
*   Support for a wider range of tools and more complex interactions.
*   Mechanisms for the agent to react to tool outputs and dynamically adjust plans.
*   Enhanced error handling and recovery.

## Current Status (End of Plan Step 1 for Phase 1)

*   Basic CLI structure for the `task` command is in place.
*   README.md updated with the new vision.
*   Core modules (`workspace_manager.py`, `container_env.py`, `tools.py`, `task_orchestrator.py`) are yet to be created.
