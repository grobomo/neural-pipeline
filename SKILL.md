# Neural Pipeline

Brain-inspired agent pipeline where tasks flow through specialized phases
like neural signals. Manages itself via prediction error learning.

## Commands

- `neural new <request>` -- Create a new task
- `neural status` -- Show pipeline status and happiness
- `neural review <task-id>` -- Review a completed task
- `neural approve <task-id>` -- Approve a task result
- `neural reject <task-id> [-- reason]` -- Reject a task result
- `neural start` -- Start the monitor daemon
- `neural stop` -- Stop the monitor daemon

## How It Works

1. You tell me what you want
2. I call the ego (the system's brain) via `python -m src.ego`
3. The ego creates a task that flows: why -> scope -> plan -> execute -> verify
4. Each phase has a manager that learns from prediction errors
5. When done, the ego presents results for your review

## Keywords

neural, pipeline, task, ego, brain, agent, create task, check status, review task,
approve, reject, start pipeline, stop pipeline
