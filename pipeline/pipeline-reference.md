# Pipeline Reference

## How the Neural Pipeline Works

This is the global reference document. Humans and the ego read this.
Managers read their own phase reference.md instead.

## Architecture

```
User <-> Claude Code <-> Ego <-> { Managers, Monitor }
                                   Managers <-> Workers
```

- **Claude Code**: Terminal (mouth + ears). NOT part of the system.
- **Ego**: SDK-based Python CLI agent. Sole interface to the system.
- **Monitor**: Watchdog-based Python daemon. Autonomic nervous system.
- **Managers**: Per-phase persistent agents with journals, rules, predictions.
- **Workers**: Ephemeral single-step agents with JSONL logging.

## Task Flow

1. User tells Claude Code what they want
2. Claude Code calls: `python -m src.ego "user request"`
3. Ego creates task file in pipeline/input/
4. Monitor detects task arrival, spawns why-phase manager
5. Why manager processes task, moves to scope/
6. Monitor detects, spawns scope manager... and so on
7. Task reaches output/, ego reviews, presents to user
8. User approves -> completed/ or rejects -> failed/

## Prediction Error Model

Managers predict output BEFORE workers execute. After execution:
- Output exceeds prediction: +3 dopamine (revise expectations upward)
- Output meets prediction: +1 dopamine (well calibrated)
- Output falls short (worker's fault): -2 cortisol
- Output falls short (manager's fault): -1 cortisol (log lesson)

## Memory Tiers

Each phase has independent memory:
- **short-term/**: Recent, frequently accessed
- **long-term/**: Proven useful at least once
- **lost/**: Archived, system cannot access

Files are NEVER deleted, only moved between tiers.

## Rule System

Rules have YAML frontmatter with keywords and effectiveness scores (-5 to +5).
Loaded into agent context only when keywords match the current task.
Scored during reflection cron based on prediction error correlation.
