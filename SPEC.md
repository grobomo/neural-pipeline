# Neural Agent Pipeline -- System Specification

## Overview

A brain-inspired agent pipeline where tasks flow through specialized phases
like neural signals through brain regions. Each phase has a manager agent
(persistent, learns over time) and ephemeral worker agents.

**Claude Code is NOT part of the system.** It is the user's terminal --
nothing more. The user types into Claude Code, Claude Code calls the ego,
the ego runs the system. Just like the only way to interface with a human
is by talking to them, the only way to interface with this system is by
talking to the ego. Claude Code is the mouth and ears. The ego is the mind.

The ego is the sole interface to the entire system. It receives all
external input, creates all tasks, presents all results, and makes all
high-level decisions. No other agent communicates outside the system.

A separate monitor daemon handles autonomic functions: watching for
filesystem events (via watchdog), waking managers, running cron jobs,
and flagging issues to the ego.

The organizational model draws from both neuroscience and corporate
structure -- which are the same pattern at different scales. Departments
are organs, managers are nerve clusters, workers are muscle fibers, the
ego is the prefrontal cortex, the monitor is the autonomic nervous system,
and the signals flowing between them are the system's "personality."

This is a research project. Cost is not a constraint. Speed is secondary
to correctness and learning.

## Design Philosophy

**Unix-style: each agent does one thing and does it well.** Workers
execute a single step and return output. Managers coordinate and evaluate.
The ego makes decisions and communicates. The monitor keeps the plumbing
running. No agent tries to do everything.

**File-based communication only.** No shared conversations, no message
passing, no orchestrator routing. Files on disk are the sole communication
channel. This makes the system fully auditable, crash-recoverable, and
debuggable by reading folders.

**Dopamine/cortisol scoring model.** Rules and memories are scored on a
simple scale inspired by neurochemistry. Good outcomes release "dopamine"
(positive score adjustments). Bad outcomes release "cortisol" (negative
score adjustments). Scores drive the ego's optimization behavior.

**Prediction error as the core learning signal.** Inspired by how the
brain actually learns: the difference between what you predicted and what
actually happened drives dopamine/cortisol release. Managers predict what
good output looks like BEFORE workers execute. After execution, the manager
compares prediction to reality. The gap -- prediction error -- determines
the strength of the dopamine/cortisol signal and drives the manager's own
calibration over time.

## Core Concepts

### Pipeline as Neural Circuit

Tasks flow through ordered phases like signals through neurons. Each phase
is a gate with a manager and workers. The task file accumulates notes from
each phase as it moves through the pipeline. The file's folder location IS
its status -- no redundant status fields needed.

**Step files are local to a phase.** They never move between phases. The
task file is the only artifact that crosses phase boundaries. Plan-phase
workers produce a plan document that the manager writes into the task file.
Execute-phase managers read that plan from the task file and create their
own step files for execute-workers.

### Managers vs Workers

**Managers** are persistent across tasks. They maintain journals, accumulate
rules, and learn from experience. They do not execute work -- they break
tasks into steps, define success criteria, write predictions, delegate to
workers, and review results. Managers read their own phase reference.md,
relevant keyword-matched rules, recent journal entries, and phase memories
before processing each task. Managers do NOT read pipeline-reference.md
on every run -- that's for humans and the ego.

Manager responsibilities:
- Break work into step files with clear success criteria
- Write a prediction to a separate file (manager/predictions/step-NNNN-NN.md) not shown to workers
- Consult phase memory for relevant warnings AND successes
- Delegate steps to workers via pending/ folder
- Review completed steps: compare output to prediction, evaluate against success criteria, review worker logs
- Score based on prediction error (see Prediction Error section)
- Adjust own calibration when predictions are consistently wrong
- Flag pain signals to ego when blocked
- Synthesize worker output into the task file
- Move the task file to the next phase folder when done (Python shutil.move)
- Investigate issues when the ego delegates an investigation request

**Workers** are ephemeral. They pick up a step file, do the work, write
output, and are done. Fresh context every time. No memory, no journal, no
continuity. Workers do NOT self-evaluate -- they execute and log. All tools
available (read, write, edit, shell, web search, grep, glob). No tool
restrictions per phase -- the step file instructions constrain behavior.
If a worker misbehaves, the manager adds a rule.

Workers log their entire conversation (all API calls and tool results) to
a JSONL log file, similar to how Claude Code logs sessions. This gives
managers full visibility into worker activity for review and scoring.

### Task Intake

The ego is the sole entry point for task creation. Tasks come from:
- **User requests:** User tells Claude Code, Claude Code calls ego, ego creates task file.
- **Ego-generated:** Ego identifies improvement opportunities during review.
- **Pain signals:** Monitor or managers flag issues, ego decides whether to create a task.

The ego assigns task IDs from an atomic counter at `system/next-task-id`.
Since only the ego creates tasks, there is no concurrency issue.

Task files include a `## References` section listing paths to any external
files the task depends on (e.g., SPEC.md, source code files). Downstream
workers read these paths for context.

### The Ego (Prefrontal Cortex)

The sole interface to the system. An SDK-based Python agent that is called
by Claude Code. The ego is NOT a long-running daemon -- it is invoked per
interaction, but maintains state through its filesystem artifacts (journal,
state.yaml, logs).

Claude Code calls the ego via CLI:
- `python ego.py "build me a web scraper"` -- new request
- `python ego.py "review task 0003"` -- check on a task
- `python ego.py "status"` -- what's going on?
- `python ego.py "approve task 0003"` -- user accepts result
- `python ego.py "reject task 0003 -- the tests don't pass"` -- user rejects

The ego:
- Receives all external input (user requests arrive ONLY through the ego)
- Creates task files in input/ (sole task creator)
- Reviews completed task results in output/
- Writes notifications to `ego/notifications/` for Claude Code hooks to pick up
- Makes high-level decisions (send task back, move to blocked, approve/reject)
- Delegates investigations to phase managers (writes investigation requests)
- Reads pain signals from managers and monitor
- Adjusts rules across all phases
- Manages the happiness metric
- Tracks prediction accuracy as a manager health metric
- Logs all activity to ego/logs/ as timestamped JSONL

The ego does NOT:
- Watch folders (that's the monitor)
- Run cron jobs (that's the monitor)
- Execute pipeline work (that's managers/workers)
- Route tasks between phases (managers do that autonomously)
- Investigate issues directly (delegates to the relevant phase manager)

When the ego receives a pain signal about a stuck task, it does NOT
investigate itself. It writes an investigation request to the relevant
phase manager, like a CEO asking a middle manager to look into a problem.
The manager investigates and writes a report. The ego reads the report
and decides what to do.

### Notifications to Claude Code

The ego writes notification files to `ego/notifications/` when it has
something to tell the user:
- Task ready for review
- Task blocked and needs user input
- Pain signal requiring user attention
- Improvement suggestions from low-happiness mode

A Claude Code hook checks `ego/notifications/` on each prompt and injects
any pending notifications into the user's context. After injection, the
notification file is moved to `ego/notifications/archive/`.

This is the ONLY channel from the system to Claude Code. The ego is the
sole author of notifications. No other agent writes to this folder.

### The Monitor (Autonomic Nervous System)

A background Python daemon that handles everything that should happen
without conscious thought. Uses `watchdog` library for filesystem event
detection -- no polling.

The monitor is NOT conversational -- it never talks to the user and never
talks to Claude Code. It communicates only with managers (wake signals)
and the ego (pain signals).

Monitor responsibilities:
- Watch phase folders for filesystem events (task file arrives via watchdog)
- Wake the appropriate phase manager when a task enters its folder
- Run reflection cron at end of session
- Run sleep cron after reflection
- Health checks: detect stuck tasks, dead managers, disk usage
- Flag anomalies to the ego via ego/pain-signals/
- Execute scheduled maintenance (log pruning, archive rotation)
- Log all activity to monitor/logs/ as timestamped JSONL

Monitor does NOT:
- Create tasks (only ego does that)
- Make decisions about task quality (only managers/ego do that)
- Modify rules (only ego does that)
- Talk to the user or Claude Code (only ego does that)
- Write notifications (only ego does that)

How the monitor wakes a manager: when watchdog detects a task file
arriving in a phase folder, the monitor spawns the manager as a
subprocess (`python manager.py --phase why --task task-0001.md`).
The manager processes the task and exits. The monitor does not need
to track the manager process beyond detecting if it hangs.

### Prediction Error

The core learning mechanism, borrowed directly from neuroscience. The
brain's dopamine system doesn't respond to absolute outcomes -- it
responds to the DIFFERENCE between what was expected and what happened.
Expected reward and got it = small signal. Got more than expected = big
dopamine. Got less = dopamine dip.

Managers implement this by writing predictions before workers execute:

**Worker meets expectations:** Output matches prediction and criteria.
Small positive signal (+1 dopamine). Manager's model is well-calibrated.

**Worker exceeds expectations:** Output is better than predicted. Big
positive signal (+3 dopamine). Manager should revise its expectations
upward for similar tasks -- it was underestimating what's possible.

**Worker falls short:** Output doesn't meet criteria. Negative signal.
But the manager must diagnose WHY by reviewing worker logs:
- Worker failed despite clear instructions = worker execution issue (-2 cortisol to loaded rules)
- Instructions were ambiguous or criteria unreasonable = manager calibration issue (no rule score change, manager logs lesson about own criteria quality)

Over time, a well-calibrated manager's predictions closely match reality.
A poorly calibrated manager is consistently surprised. The ego tracks
prediction accuracy as a manager health metric:
- Consistently exceeded = bar set too low, manager is underestimating
- Consistently falling short = bar too high OR worker instructions unclear
- Accurately predicted = well-calibrated manager, healthy phase

### Warnings and Successes as Manager Habits

There is no dedicated warning phase. Every manager, as part of its normal
processing, consults its phase memory for both warnings (past failures,
risks) and successes (approaches that worked well). This is like how
caution and confidence are not separate brain regions -- they are behaviors
that every region exhibits based on past experience.

Each manager's reference.md instructs it to:
1. Check memory for past failures relevant to this task (avoid repeating)
2. Check memory for past successes relevant to this task (replicate)
3. Include both warnings and recommended approaches in worker step files
4. Record which memories were consulted and whether they proved useful

### Happiness Metric

- Starts at a baseline (e.g., 70/100)
- Pleasure signals increase it (task success, user approval, efficiency gains)
- Pain signals decrease it (user corrections, failures, blockers, resource waste)
- Decays slowly over time regardless of signals (hedonic adaptation)
- Below a threshold, ego enters "improvement seeking" mode
- The ego's goal is to maximize user happiness, tracked as a proxy metric

### Memory System

Three-tier memory inspired by human memory consolidation. Each phase has
its own independent memory -- memories do not cross phases.

**Short-term:** Recent, frequently accessed. Active working memories.
**Long-term:** Proven useful at least once. Accessed less often.
**Lost:** Archived. System cannot access these. User can manually restore.

Memory importance is scored AFTER task completion (during review/reflection),
not at read time. Like humans, you don't know if advice was useful until
after you've tried it.

- Memory read + action taken based on it = importance UP
- Memory read + not implemented = importance DOWN
- Below threshold = move to long-term
- In long-term ~1 year with no implementation = move to lost
- Read from long-term and implemented = promote back to short-term
- Files are NEVER deleted, only moved between tiers

### Dynamic Rules

Each phase has separate rule books for managers and workers. Rules are
loaded into agent context via keyword matching against the current task
(same pattern as the existing rule-book system). Rules not relevant to
the current task are not loaded, keeping agent context lean.

Each rule file carries its own effectiveness score in frontmatter, using
a dopamine/cortisol model scaled from -5 to +5.

Rule effectiveness is monitored during reflection cron jobs. The ego can
add, edit, or remove rules in any phase's rule folders.

### Worker Logging

Every worker logs its complete API conversation to a JSONL file in the
phase's log folder. This includes all prompts, responses, and tool calls.
Managers use these logs to review worker activity and score results.

Log naming: `YYYY-MM-DDTHH-MM-SS-step-NNN.jsonl` (datetime + step number)

Log lifecycle:
- Worker writes log during execution to logs/active/
- After manager reviews, log moves to logs/archive/
- Archive pruned by time-based rotation (default: 2 weeks)

### Manager Logging

Every manager also logs its API conversations to JSONL files in its own
log folder. Same naming convention as workers.

Log naming: `YYYY-MM-DDTHH-MM-SS-task-NNNN.jsonl` (datetime + task ID)

Stored in: `[phase]/manager/logs/active/` and `[phase]/manager/logs/archive/`

### Ego Logging

The ego logs all conversations (with Claude Code and with the system) to:
`ego/logs/YYYY-MM-DDTHH-MM-SS.jsonl`

This captures the full interaction history plus ego's internal reasoning
about task creation, result presentation, and interventions.

### Monitor Logging

The monitor logs all activity to:
`monitor/logs/YYYY-MM-DDTHH-MM-SS.jsonl`

This captures filesystem events, manager wake-ups, cron executions,
health check results, and pain signals sent to the ego.

### Crash Recovery

The system is fully recoverable from filesystem state alone. No in-memory
state is authoritative. If the system crashes:
- Task files in phase folders show which phase each task is in
- Step files in pending/active/completed show worker progress
- Worker logs show exactly what happened during interrupted steps
- Manager journals show what decisions were made
- Everything needed to resume is on disk

On restart, the monitor scans all phase folders for in-flight tasks and
resumes processing from the last known state.

### Cold Start

On first run, all managers have zero journals, zero rules, and zero
memories. The reference.md per phase is the bootstrap -- it contains
enough context for a manager to operate on day one. Think of it as a
new employee's onboarding document. Over time, journals and rules
accumulate and the reference.md matters less.

The ego and monitor also have reference.md files that define their
behavior from the start. No special "learning mode" -- the system just
has less accumulated knowledge on day one and builds it naturally.

## Pipeline Phases

```
input/       -- Queue. Tasks land here. No processing.
why/         -- Why are we doing this? Motivation, pain point, goal.
scope/       -- What exactly? Boundaries, clarifications, acceptance criteria.
plan/        -- How? Steps, tools, approach.
execute/     -- Do it. Workers carry out the plan.
verify/      -- Did it work? Compare output to scope's acceptance criteria.
output/      -- Ego reviews, presents to user, scores everything.
```

Seven phases. Input and output as clean bookends. Each manager checks
its own memories for warnings and successes as a standard habit.

The why phase comes first because motivation shapes everything downstream.
If you don't know why you're doing a task, you can't draw the finish line.

## Task Lifecycle After Pipeline

```
completed/   -- Successful tasks. Ego references during reflection.
  recent/    -- Last 30 days. Actively scanned for patterns.
  archive/   -- Older than 30 days. Same structure, just stored.

failed/      -- Tasks that didn't work. User rejected or abandoned.
  recent/    -- Last 30 days. Ego analyzes failure patterns.
  archive/   -- Older than 30 days.

paused/      -- Tasks the user put off. Moved back to input/ to resume.

blocked/     -- Tasks stuck on unresolvable blockers. Ego presents to user.
```

**Completed** reminds the system of its wins -- positive reinforcement for
the happiness mechanic. The ego looks at completed/recent/ to track trends.

**Failed** is where the ego goes to learn from mistakes. Failure patterns
across recent tasks drive improvement-seeking behavior.

**Paused** is a clean holding state. Task file retains all accumulated notes
from whatever phase it was in when paused. When resumed, moves back to
input/ and flows through the pipeline with prior context intact.

**Blocked** holds tasks that hit unresolvable blockers -- missing
credentials, external dependencies, ambiguous requirements that need
user input. The ego periodically presents blocked tasks to the user
for resolution. Once unblocked, task moves back to the phase it was in.

Tasks are NEVER deleted. Sleep cron moves from recent/ to archive/ at
the 30-day mark.

## Folder Structure

```
pipeline/
  pipeline-reference.md          -- Global reference: how the whole system works

  input/                         -- Queue. Tasks land here. No processing.
    task-NNNN.md

  why/                           -- Why are we doing this? Motivation, goal.
    reference.md                 -- Phase identity, role separation, workflow
    manager/
      rules/                     -- Manager rules (keyword-matched per task)
      journal.md                 -- Running log: decisions, outcomes, +/-
      journal-archive/           -- Rotated journals + extracted summaries
      stats.yaml                 -- Performance metrics for ego monitoring
      predictions/               -- Manager predictions per step (not shown to workers)
      logs/
        active/                  -- Manager JSONL logs during task processing
        archive/                 -- Reviewed manager logs
    workers/
      rules/                     -- Worker rules (keyword-matched per task)
      steps/
        pending/                 -- Manager creates step files here
        active/                  -- Worker picks up, moves here while working
        completed/               -- Worker finishes, moves here
      logs/
        active/                  -- Worker JSONL logs during execution
        archive/                 -- Reviewed logs (pruned after 2 weeks)
    memory/
      short-term/
      long-term/
      lost/

  scope/                         -- (same structure as why/)
  plan/                          -- (same structure as why/)
  execute/                       -- (same structure as why/)
  verify/                        -- (same structure as why/)

  output/                        -- Ego reviews, presents to user, scores.
    task-NNNN-result.md

completed/
  recent/                        -- Last 30 days
  archive/                       -- Older than 30 days

failed/
  recent/
  archive/

paused/                          -- Tasks put off by user. Resume via input/

blocked/                         -- Stuck tasks. Ego presents to user.

ego/
  reference.md                   -- Ego identity, responsibilities, constraints
  state.yaml                     -- Happiness score, decay rate, thresholds
  journal.md                     -- Ego decisions, interventions, lessons
  journal-archive/               -- Rotated ego journals
  logs/                          -- Ego JSONL logs (datetime stamped)
  pain-signals/                  -- Incoming from managers and monitor
  notifications/                 -- Outgoing to Claude Code (ego is sole author)
    archive/                     -- Notifications already delivered
  investigations/                -- Investigation requests sent to managers
    responses/                   -- Manager investigation reports back to ego

monitor/
  reference.md                   -- Monitor identity, responsibilities, constraints
  logs/                          -- Monitor activity JSONL logs (datetime stamped)
  health/                        -- Latest health check results per phase

system/
  config.yaml                    -- Model choices, API settings, project_root, thresholds
  next-task-id                   -- Atomic counter file (integer, ego increments)
  agents/                        -- Agent prompt templates
    manager-base.md              -- Common manager instructions
    worker-base.md               -- Common worker instructions
    ego.md                       -- Ego system prompt
    monitor.md                   -- Monitor system prompt
  cron/
    reflection.yaml              -- End-of-session reflection job definition
    sleep.yaml                   -- Memory pruning/consolidation job definition
```

## Communication Hierarchy

```
User <-> Claude Code <-> Ego <-> { Managers, Monitor }
                                   Managers <-> Workers

No shortcuts. No agent bypasses the ego to reach the user.
No agent bypasses the manager to reach the ego (except monitor for health).
```

Detailed paths:

- User -> Claude Code -> Ego: `python ego.py "user request"`
- Ego -> Claude Code -> User: writes to ego/notifications/, hook injects into Claude Code
- Ego -> Input: creates task file in input/
- Monitor -> Manager: spawns manager subprocess when watchdog detects task arrival
- Manager -> Worker: creates step file in pending/
- Worker -> Manager: completes step file, moves to completed/; log in logs/active/
- Manager -> Next phase: moves task file to next phase folder (shutil.move)
- Manager -> Ego: writes to ego/pain-signals/ when blocked
- Manager -> Blocked: moves task to blocked/ when unresolvable
- Monitor -> Ego: writes to ego/pain-signals/ for health issues
- Ego -> Manager: writes investigation request to ego/investigations/
- Manager -> Ego: writes investigation response to ego/investigations/responses/
- Ego -> Manager: edits manager's rules/ or workers/rules/ files
- Ego -> Completed/Failed: moves task from output/ after user verdict
- Ego -> Paused: moves in-flight task to paused/ at user request
- Ego -> Input: resumes paused task by moving back to input/

## Rule File Format

Rules carry their own effectiveness scores in frontmatter. The score uses
a dopamine/cortisol model: good outcomes push the score positive (dopamine),
bad outcomes push it negative (cortisol). Range: -5 to +5.

```markdown
---
id: check-existing-code
keywords: [existing, code, duplicate, check, reuse]
enabled: true
score: 2
history:
  loaded: 15
  successes: 11
  failures: 4
  last_scored: 2026-03-12
---

# Check Existing Code Before Writing New

## WHY
Workers sometimes write code that duplicates existing functionality.
Checking first saves time and maintains consistency.

## Rule
Before writing new functions or modules, search the codebase for
existing implementations that do the same thing or something similar.

## Do NOT
- Do NOT write new utility functions without checking utils/ first
- Do NOT duplicate API client code that already exists
```

### Score Adjustment Rules

Scores are updated during the reflection cron. Adjustment magnitude is
driven by prediction error -- the bigger the surprise, the stronger the
signal, just like real dopamine responses.

| Outcome | Score adjustment | Analogy |
|---------|-----------------|---------|
| Rule loaded, output exceeded prediction | +3 | Big dopamine -- unexpectedly good |
| Rule loaded, output met prediction and criteria | +1 | Small dopamine -- expected good |
| Rule loaded, outcome unclear | 0 | No signal |
| Rule loaded, output fell short, worker's fault | -1 | Small cortisol -- rule may not have helped |
| Rule loaded, output fell short, clearly bad advice | -3 | Big cortisol -- rule actively hurt |

Key principle: NO score change if output fell short due to manager
calibration issues (unreasonable criteria, vague instructions). The rule
isn't at fault if the manager set the wrong bar.

### Ego Actions Based on Scores

| Score | Ego action |
|-------|------------|
| -5 (floor) | Disable or rewrite the rule -- it's actively harmful |
| -3 to -4 | Review urgently, likely needs major revision |
| -1 to -2 | Monitor, may need keyword tuning or content update |
| 0 | Neutral, review if loaded count is high (noise rule) |
| +1 to +2 | Healthy rule, no action needed |
| +3 to +4 | Strong rule, consider broadening keywords |
| +5 (ceiling) | Promote pattern to other phases if applicable |

Rules that haven't loaded in 20+ tasks may have bad keywords -- ego
reviews regardless of score.

## Task File Format

Task files accumulate notes from each phase as they move through the
pipeline. Each phase's manager appends a new section. Workers do NOT
write to the task file -- they write to step files. The manager
synthesizes step results into the task file.

```markdown
# Task NNNN: [title]
Created: [timestamp]
Source: user | ego | system

## User Request
[Original request text]

## References
[Paths to external files this task depends on]
- /path/to/SPEC.md
- /path/to/source/file.py

## Why
[Why manager's notes: motivation, pain point, what success means for user]
Memories consulted: [list with relevance notes]

## Scope
[Scope manager's notes: boundaries, what's in/out, acceptance criteria]
Memories consulted: [...]

## Plan
[Plan manager's notes: step-by-step approach, tools needed, gaps identified]
Memories consulted: [...]

## Execute
[Execute manager's summary: what was executed, what changed, blockers hit]
Worker results: [per-step outcomes with success/fail against criteria]
Memories consulted: [...]

## Verify
[Verify manager's assessment: criteria met? compare to scope's acceptance criteria]
Memory scoring: [which memories from all phases were accurate/useful]
Rule scoring: [which rules from all phases correlated with outcomes]
```

## Step File Format

Step files are created by managers and owned by individual workers.
One worker per step file. No concurrent access. Step files are local
to a phase -- they never move between phases. The task file is the
only artifact that crosses phase boundaries.

The manager defines success criteria BEFORE assigning the step -- this
is how the manager will evaluate the worker's output. The manager's
prediction is stored in a separate file (manager/predictions/) so
workers cannot be influenced by it.

```markdown
# Step [number]: [description]
Task: NNNN
Phase: [phase name]
Status: pending | active | completed | blocked
Assigned: [timestamp when moved to active]
Completed: [timestamp when moved to completed]
Worker-log: [path to worker's JSONL log file]

## Instructions
[What the worker needs to do]

## Success Criteria
[Specific, measurable criteria defined by the manager BEFORE assignment.
 The worker sees these so it knows the bar. The manager uses these to
 evaluate the completed work.]

Examples:
- "File compiles without errors"
- "All 3 test cases pass"
- "Response includes all 5 required fields"
- "No references to deprecated API remain"

## Context
[Relevant excerpts from the task file that the worker needs]
[Relevant warnings from manager's memory check]
[Relevant success patterns from manager's memory check]
[Paths to reference files from the task's References section]

## Output
[Worker writes results here before moving to completed]

## Blockers
[If status is blocked, describe what's blocking and flag for manager]
```

## Worker Log Format

Workers log their complete conversation to JSONL, one JSON object per
line. This mirrors Claude Code's session logging format.

```
logs/active/YYYY-MM-DDTHH-MM-SS-step-NNN.jsonl

Each line is one of:
{"type":"system","timestamp":"...","content":"[system prompt]"}
{"type":"user","timestamp":"...","content":"[prompt sent to API]"}
{"type":"assistant","timestamp":"...","content":"[API response]","tool_calls":[...]}
{"type":"tool_result","timestamp":"...","tool":"read_file","result":"[output]"}
```

Log lifecycle:
1. Worker creates log in logs/active/ when step starts
2. Worker appends every API interaction as it works
3. When step completes, manager reviews log alongside step output
4. After manager review, log moves to logs/archive/
5. Archive pruned on time-based rotation (default: 2 weeks)

## Manager Journal Format

Managers log both positive and negative outcomes. This dual tracking
prevents the system from becoming purely defensive/risk-averse.

```markdown
## Task NNNN: [title] ([date])

### Decisions
- [What the manager decided and why]

### Worker Performance
- Step 1: [description]
  Criteria met: yes/no | Prediction: met/exceeded/fell-short | Iterations: N | [GOOD|PAIN]
  Log: [path to worker log]
  Notes: [if exceeded -- what was better than expected and why]
         [if fell short -- was it worker execution or manager calibration?]
- Step 2: [description]
  Criteria met: yes/no | Prediction: met/exceeded/fell-short | Iterations: N | [GOOD|PAIN]
  Log: [path to worker log]

### Memories Consulted
- [memory-file.md]: relevant/irrelevant, accurate/inaccurate

### Rules Loaded
- [rule-id]: relevant/irrelevant to this task
  (scored during reflection)

### Lessons
- (positive) [What worked well and should be replicated]
- (negative) [What failed and should be avoided]
- (neutral) [Observations that may be useful later]
```

## Manager Stats Format

```yaml
# [phase]/manager/stats.yaml
tasks_processed: 0
outcomes:
  success: 0
  partial: 0
  failure: 0
  sent_back: 0         # times verify/ego sent task back to this phase
worker_metrics:
  total_steps: 0
  avg_iterations_per_step: 0.0
  criteria_met_first_try: 0
  criteria_met_after_retry: 0
  criteria_not_met: 0
  blocker_count: 0
  blocker_rate: 0.0
prediction_accuracy:
  total_reviewed: 0
  met_expectations: 0    # output matched prediction
  exceeded: 0            # output better than predicted
  fell_short: 0          # output worse than predicted
  accuracy_rate: 0.0     # met / total
  calibration_trend: stable  # improving | stable | declining
memory_effectiveness:
  top_useful: []        # memories that correlated with good outcomes
  top_misleading: []    # memories that correlated with bad outcomes
```

## Scoring

### Immediate Scoring (at output time)

When a task reaches output/ and the ego presents it to the user:
- User approval = immediate happiness signal (+task_success, +user_approval)
- User rejection = immediate pain signal (+user_correction)
- Basic pass/fail recorded on the task

### Deep Scoring (reflection cron)

The monitor triggers the reflection cron. Each phase manager then:
- Cross-references which rules were loaded across all phases
- Evaluates which memories were consulted and whether they were accurate
- Computes prediction accuracy stats
- Detects patterns across multiple tasks
- Updates rule scores (dopamine/cortisol adjustments)
- Updates memory importance scores

First few tasks get immediate scoring only. Deep scoring becomes
meaningful after enough tasks accumulate for pattern detection.

## Cron Jobs

### Reflection (end of session)

Triggered by the monitor. Each phase manager runs reflection:

1. Each phase manager reviews its completed steps and journal
2. Reviews worker logs for steps completed this session
3. Evaluates worker output against success criteria
4. Compares output to predictions (prediction error scoring)
5. Scores rules loaded during this session (dopamine/cortisol adjustments)
6. Scores memories consulted during this session
7. Extracts lessons (positive AND negative)
8. Writes new memory files to short-term/ if lessons are reusable
9. Updates stats.yaml with session metrics
10. Moves reviewed worker logs from logs/active/ to logs/archive/
11. Reports summary to ego
12. Ego reviews all reports, adjusts happiness, tweaks rules as needed
13. Ego reviews blocked/ tasks, notifies user if applicable

### Sleep (after reflection)

Triggered by the monitor after reflection completes:

1. Score all short-term memory files by importance
2. Below threshold: move to long-term/
3. Long-term files older than threshold with no implementation: move to lost/
4. Long-term files recently read + implemented: promote to short-term/
5. Consolidate related memories (merge similar lessons into summaries)
6. Rotate journals that exceed size threshold
7. Archive rotated journals, extract key lessons as memory files
8. Prune worker log archives older than retention period (default: 2 weeks)
9. Move completed/recent/ tasks older than 30 days to completed/archive/
10. Move failed/recent/ tasks older than 30 days to failed/archive/

### Journal Rotation

When journal.md exceeds threshold (50 entries or 100KB):
1. Summarize old journal into key lessons (LLM call during sleep cron)
2. Move full journal to journal-archive/ with timestamp
3. Start fresh journal.md with header referencing archive
4. Write extracted lessons as memory files in short-term/

## Pain Signals

Managers and the monitor flag issues to the ego by writing files to
ego/pain-signals/. The ego does NOT intervene in normal flow -- only
when pain is signaled.

Pain signal triggers (from managers):
- Worker reports a blocker it cannot resolve
- Manager detects circular behavior (same approach tried and failed)
- Task exceeds expected iteration count
- Rule violation detected but no rule exists to prevent it

Pain signal triggers (from monitor):
- Task stuck in a phase for too long
- Manager process not responding
- System resources spike (CPU/RAM/disk)
- Cron job failed

Pain signal triggers (from user via ego):
- User correction received (strongest pain signal)

The ego reads pain signals and delegates investigation to the relevant
phase manager by writing to ego/investigations/. The manager investigates
(reviews logs, checks worker output, examines step files) and writes a
response to ego/investigations/responses/. The ego reads the response
and decides:
- May send task back to an earlier phase
- May move task to blocked/ and notify user
- May add/modify rules in the relevant phase
- May adjust system config
- Logs all interventions in ego/logs/

## Happiness Mechanics

```yaml
# ego/state.yaml
happiness: 70.0
baseline: 50.0
decay_rate: 0.1        # per ego cycle
improvement_threshold: 40.0  # below this, ego seeks improvements

# Signal weights
signals:
  task_success: +5.0
  user_approval: +10.0
  user_correction: -15.0
  efficiency_gain: +3.0
  blocker_resolved: +2.0
  repeated_failure: -10.0
  rule_violation: -5.0
  worker_exceeded_prediction: +3.0
  worker_met_prediction: +1.0
  worker_fell_short: -2.0
  manager_miscalibrated: -1.0
  memory_accurate: +2.0
  memory_misleading: -3.0
```

Happiness = max(0, min(100, happiness + signals - decay))

When happiness < improvement_threshold, the ego enters improvement mode:
- Reviews recent task history for patterns
- Identifies phases with lowest quality scores
- Proactively tweaks rules and prompts
- Amplifies what's working (promotes effective memories, strengthens good rules)
- Does NOT wait for pain signals

## Implementation Stack

- **Language:** Python
- **LLM access:** Claude Agent SDK or raw `anthropic` library
- **Each manager:** Python script invoked by monitor per task (not long-running)
- **Each worker:** A single SDK call with phase-specific system prompt + tools
- **Ego:** Python CLI invoked by Claude Code per interaction, state on disk
- **Monitor:** Long-running Python daemon using watchdog for filesystem events
- **File operations:** Python stdlib (shutil.move, os.rename, pathlib)
- **Claude Code integration:** Hook checks ego/notifications/ on each prompt
- **No framework, no orchestrator, no swarm**
- **Config:** system/config.yaml includes project_root, model choices, thresholds

## Open Questions

- Optimal journal rotation threshold and memory consolidation strategy.
  Start with 50 entries / 100KB, adjust based on context window impact.

- How many workers per phase in parallel? Start with 1, scale up as
  we understand resource contention.

- Model selection per agent role: managers may need stronger models
  (Opus/Sonnet) while workers doing simple tasks could use Haiku.
  Experiment needed.

- How does the ego decide which phase to send a task back to on
  rejection? Needs heuristics or its own learned rules.

- What is the right balance between positive and negative signals
  in the happiness mechanic? Too much positive = complacent system.
  Too much negative = risk-averse system. Needs tuning.

- How granular should success criteria be? Too specific = managers
  spend more time writing criteria than the task is worth. Too vague
  = scoring is unreliable. Needs calibration per phase.
