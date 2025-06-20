# Jules Local

## Overview

Jules Local is a command-line tool that aims to simulate some of the core concepts of the experimental Google coding agent, Jules (as described at [jules.google/docs](https://jules.google/docs)), but for execution on your local Linux machine. It uses Large Language Models (LLMs) like Google Gemini for planning and can interact with your codebase within a containerized environment using a defined set of tools.

## How Jules Local Compares to Google Jules

This table provides a high-level comparison between the original Google Jules (a cloud-based experimental coding agent) and this Jules Local project, which aims to simulate some of its core concepts for local execution and experimentation.

| Feature                    | Google Jules (Cloud)                                  | Jules Local (This Project)                                                                 |
|----------------------------|-------------------------------------------------------|--------------------------------------------------------------------------------------------|
| **Core Functionality**     | AI coding agent for bug fixing, feature dev, docs.    | Local simulation of an AI coding agent; framework for LLM-driven, tool-based code tasks.    |
| **Primary Interaction**    | Natural language prompt via web UI.                   | Natural language prompt via CLI command (`jules-local task <repo> "<prompt>"`).              |
| **Code Access**            | Connects to GitHub repositories.                      | Clones local Git repositories or remote Git URLs into a temporary workspace.               |
| **Workspace Management**   | Manages code clones in its backend.                 | Creates a local temporary directory (`jules_workspaces/task_<id>/code`).                   |
| **Branching Strategy**     | Works on specified or new branches in GitHub.         | Creates a new local task-specific branch (`jules_task/<task_id>`) in the cloned workspace. |
| **Planning Mechanism**     | Sophisticated AI/LLM generates a multi-step plan.     | LLM (e.g., Gemini Pro) generates a multi-step plan based on prompt and available tools.    |
| **Execution Environment**  | Runs tasks in a Virtual Machine in the cloud.       | Runs tasks in a Docker/Podman container on the local Linux machine.                        |
| **Environment Setup**      | Supports environment setup scripts.                   | Supports a `.jules/setup.sh` script in the user's repo for container setup.                |
| **Tool Usage**             | Uses a rich set of internal tools.                    | Uses a defined set of Python tools (`tools.py`) that operate within the container.         |
| **User Review/Approval**   | User reviews and approves the generated plan.         | User reviews and approves the LLM-generated plan via CLI input (`yes/no`).                 |
| **Output/Results**         | Proposes changes (e.g., Pull Requests), logs actions. | Prints tool outputs, logs actions to console, displays a `git diff` of changes.            |
| **Underlying Intelligence**| Advanced Google AI models.                            | Configurable LLMs (e.g., Gemini Pro for planning, Gemini Flash for optional sub-tasks).    |
| **Asynchronous Work**      | Works asynchronously; user can leave and be notified. | Currently synchronous; CLI command waits for completion.                                   |
| **Notifications**          | Browser/email notifications.                          | No built-in notification system.                                                           |

## LLM Configuration

To enable features that use Large Language Models (LLMs) like Google Gemini, you need to configure an API key and optionally specify model names.

### API Key

Jules Local expects the Google Gemini API key to be available as an environment variable:

```bash
export GEMINI_API_KEY="YOUR_API_KEY_HERE"
```

Replace `YOUR_API_KEY_HERE` with your actual Gemini API key. You can obtain an API key from [Google AI Studio](https://aistudio.google.com/app/apikey).

### Model Names (Optional)

You can also specify which Gemini models to use for different purposes by setting these environment variables:

*   `MAIN_LLM_MODEL_NAME`: Used for the primary task of understanding your prompt and generating the overall plan. Defaults to a recent Gemini Pro model (e.g., `gemini-2.5-pro`).
*   `LITE_LLM_MODEL_NAME`: Used by specific tools (like `generate_text_via_llm`) for more focused, smaller generation tasks. Defaults to a recent Gemini Flash model (e.g., `gemini-2.5-flash-lite-preview-06-17`).

Example:
```bash
export MAIN_LLM_MODEL_NAME="gemini-2.5-pro"
export LITE_LLM_MODEL_NAME="gemini-2.5-flash-lite-preview-06-17"
```

If these are not set, the application will use predefined default model names. Please refer to the [Google Gemini documentation](https://ai.google.dev/gemini-api/docs/models) for the latest available model names.

## High-Level Architecture

*   **CLI (`jules_local_cli.py`):** Parses user commands and orchestrates the workflow.
*   **LLM Client (`gemini_client.py`):** Manages API key configuration and communication with Google Gemini LLMs.
*   **Workspace Manager (`workspace_manager.py`):** Manages temporary local Git clones of user repositories for tasks, including task-specific branches.
*   **Container Environment (`container_env.py`):** Handles Docker/Podman interactions, including starting persistent containers with mounted workspaces, executing commands within them, and managing their lifecycle. The default container image is `python:3.9-buster` to ensure `git` is available.
*   **Tooling System (`tools.py`):** Provides a defined set of actions (tools) that can be performed within the containerized workspace (e.g., file operations, command execution, Git operations, LLM calls for sub-tasks).
*   **Planning Module (`planning_module.py`):** Uses an LLM (e.g., Gemini Pro) to generate a multi-step plan of tool calls based on the user's prompt and the available tools.
*   **Task Orchestrator (`task_orchestrator.py`):** Manages the lifecycle of a single task: setup, planning, user approval of the plan, execution of approved tool calls, displaying a `git diff` of changes, and cleanup.

## Basic Usage

To initiate a task:

```bash
# Ensure GEMINI_API_KEY is set in your environment
export GEMINI_API_KEY="YOUR_API_KEY_HERE"

# Run a task
python3 jules_local_cli.py task <path_to_your_local_git_repo_or_url> "<your_task_prompt>"
```

Example:
```bash
python3 jules_local_cli.py task ./my-project "Create a new file named 'todo.txt' with the content 'Buy milk'."
```
Jules Local will then:
1.  Clone `./my-project` into a temporary workspace on a new task branch.
2.  Run `.jules/setup.sh` from your project in the container (if it exists).
3.  Call an LLM to generate a plan based on your prompt.
4.  Present the plan for your approval.
5.  If approved, execute the plan's tool calls in the container.
6.  Display a `git diff` of any changes made.
7.  Clean up the workspace and container.

## LLM-Powered Planning & Execution (Phase 2 & 3 Enhancements)

Jules Local uses an LLM-driven workflow for planning and executing tasks:

### LLM-Driven Planning
*   **Intelligent Plan Generation**: A configured "Main LLM" (e.g., Gemini Pro) interprets your natural language prompts and generates a multi-step plan.
*   **Tool Awareness**: The LLM is provided with specifications for available tools (e.g., `list_files`, `read_file`, `write_file`, `run_shell_command`, `git_diff`, `generate_text_via_llm`) and decides how to use them.
*   **File Tree Context**: To aid in planning, the LLM is provided with a view of the project's file and directory structure.
### Plan Approval
Before execution, the LLM-generated plan is displayed for your approval (`yes/no`). Example:
```
Please review and approve the following plan:
Proposed Plan:
  Step 1: Tool: list_files, Arguments: {'path': '.'}
  Step 2: Tool: read_file, Arguments: {'file_path': 'README.md'}
Approve plan? (yes/no):
```

### Available Tools (Examples)
The LLM planner can use tools like:
*   `list_files`, `read_file`, `write_file`: For file operations.
*   `run_shell_command`: For arbitrary shell commands in the workspace.
*   `generate_text_via_llm`: Calls a "Lite LLM" for focused text/code generation.
*   `git_diff`: Shows changes in the workspace.
*   `get_file_tree [path]`: Lists all files and directories recursively from the given path (or workspace root by default). The planner uses this output as context.
### End-of-Task Diff Display
After an approved plan executes, Jules Local automatically displays a `git diff` of all changes made to the workspace.

### Container Environment Note
The default container image is `python:3.9-buster` to ensure `git` is available. For custom images, ensure `git` is installed if needed (e.g., via `.jules/setup.sh`).

## Phase 1 Details & Conventions (Foundational Framework)

This phase established the initial structure. Key elements include:

### Workspace Setup: Git Integration
*   **Cloning Repositories**: Jules Local now uses `git clone` to set up the workspace from your specified local repository path or a remote Git URL.
*   **Task-Specific Branches**: After cloning, a new local branch named `jules_task/<task_id>` is automatically created and checked out. All tool operations occur on this branch.

### Environment Setup Script (`.jules/setup.sh`)
If your project requires specific dependencies (e.g., installing packages), create `my_project/.jules/setup.sh`. This script will be executed inside the container after workspace setup. Example:
```shell
#!/bin/sh
echo "Setting up environment..."
if [ -f "/workspace/requirements.txt" ]; then
    pip install -r /workspace/requirements.txt
fi
```

## Future Phases

Jules Local continues to evolve. Current development focuses on:
*   Refining LLM prompt engineering for more robust and versatile plan generation.
*   Expanding the toolset and their capabilities.
*   Improving mechanisms for the agent to analyze tool outputs and make dynamic adjustments to plans (e.g., conditional execution, loops, error recovery).
*   Enhancing user interaction for plan refinement and feedback.
*   Exploring state management for more complex, multi-step tasks that might require context persistence.
