"""Worker runner -- entry point for worker subprocess.

Called by managers to execute a single step. This module is invoked as:
  python -m src.worker_runner --phase why --step path/to/step.md --root /path/to/project
"""
import argparse
import json
import sys
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description="Run a Neural Pipeline worker")
    parser.add_argument("--phase", required=True, help="Pipeline phase")
    parser.add_argument("--step", required=True, help="Path to step file")
    parser.add_argument("--root", required=True, help="Project root path")
    args = parser.parse_args()

    # Ensure project root is in sys.path
    root = Path(args.root).resolve()
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))

    from src.config import Config
    from src.worker_base import WorkerBase

    config = Config()
    step_path = Path(args.step)

    if not step_path.exists():
        print(json.dumps({"error": f"Step file not found: {args.step}"}))
        sys.exit(1)

    try:
        worker = WorkerBase(
            phase=args.phase,
            step_path=step_path,
            config=config,
        )
        result = worker.run()
        print(json.dumps(result, default=str))
    except Exception as e:
        print(json.dumps({"error": str(e), "phase": args.phase, "step": args.step}))
        sys.exit(1)


if __name__ == "__main__":
    main()
