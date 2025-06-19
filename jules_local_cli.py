import argparse
import sys # For later use, e.g. sys.exit()
from task_orchestrator import run_task
import task_orchestrator # To make the lambda work directly

# Placeholder for imports from other modules we'll create later
# import task_orchestrator # This line is now effectively replaced by the one above

def main():
    parser = argparse.ArgumentParser(description="Jules Local - A local coding agent.")
    subparsers = parser.add_subparsers(dest='command', help='Available commands', required=True)

    # 'task' command
    task_parser = subparsers.add_parser('task', help='Run a new task for Jules Local.')
    task_parser.add_argument('repo_path', type=str, help='Path to the local Git repository.')
    task_parser.add_argument('prompt', type=str, help='The task prompt for Jules.')
    # Set the default function to call run_task from task_orchestrator
    task_parser.set_defaults(func=lambda args: task_orchestrator.run_task(args.repo_path, args.prompt))

    args = parser.parse_args()
    args.func(args)

# The old handle_task_command function is removed.

if __name__ == '__main__':
    main()
