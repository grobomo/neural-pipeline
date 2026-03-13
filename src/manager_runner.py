"""Manager runner -- entry point for manager subprocess.

Called by monitor to process a task in a specific phase. This module is invoked as:
  python -m src.manager_runner --phase why --task path/to/task.md --root /path/to/project
"""
import argparse
import json
import sys
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description="Run a Neural Pipeline phase manager")
    parser.add_argument("--phase", required=True, help="Pipeline phase")
    parser.add_argument("--task", required=True, help="Path to task file")
    parser.add_argument("--root", required=True, help="Project root path")
    parser.add_argument("--project-path", default="", help="Target project path (for per-project pipeline dirs)")
    parser.add_argument("--project-slug", default="", help="Project slug (alternative to --project-path)")
    args = parser.parse_args()

    # Ensure project root is in sys.path
    root = Path(args.root).resolve()
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))

    from src.config import Config
    from src.manager_base import ManagerBase

    config = Config()
    if args.project_slug:
        config.set_project_slug(args.project_slug)
    elif args.project_path:
        config.set_project(args.project_path)
    task_path = Path(args.task)

    if not task_path.exists():
        print(json.dumps({"error": f"Task file not found: {args.task}"}))
        sys.exit(1)

    try:
        manager = ManagerBase(
            phase=args.phase,
            task_path=task_path,
            config=config,
        )
        result = manager.run()
        print(json.dumps(result, indent=2, default=str))
    except Exception as e:
        print(json.dumps({"error": str(e), "phase": args.phase, "task": args.task}))
        sys.exit(1)


if __name__ == "__main__":
    main()
