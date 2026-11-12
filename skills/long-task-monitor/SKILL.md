---
name: long-task-monitor
description: Report task status only for an actual goal task or when the user explicitly requests reporting for the current task. Ordinary conversations and general multi-step work must not report merely because this skill or server configuration exists. Supports Codex and any harness that can execute Python, including DeepSeek harnesses; does not change goal state itself.
---

# Long task monitor

Use `scripts/report.py` (Python 3.10+, standard library only) to send concise task status to the user's configured server. Resolve its absolute path relative to this SKILL.md. This skill is instructions plus a reporter, not a background hook: the harness must load the skill and execute checkpoint calls.

## Reporting gate

Before reading reporting credentials or running the reporter, check whether the current work is an actual goal task (the user invoked goal mode for this objective, or the harness identifies this objective as its current goal), or the user explicitly requested reporting for this task. Only either condition permits reporting.

- Ordinary conversations, code edits and multi-step tasks do not report automatically. A previous completed goal in the same chat is not a trigger for new work.
- Discussing, sharing, installing or configuring this skill does not request reporting. Loading or explicitly naming the skill while asking how it works is not reporting authorization.
- An explicit “do not report” instruction overrides both triggers for its stated scope, including goal tasks. Do not send start, checkpoints, heartbeats, completion, replay or connection-test events while reporting is disabled.
- Apply all checkpoints below only after this gate permits reporting. Do not create a goal or invent authorization to enable monitoring.

## Configuration and scope

Read `MONITOR_URL` and `MONITOR_TOKEN` from environment variables or `~/.config/long-task-monitor/client.env`. `MONITOR_CONFIG` or `--config` can select another file. Example configuration:

```ini
MONITOR_URL=https://monitor.example.com
MONITOR_TOKEN=<reporting secret>
```

Configuration supplies the destination and credentials; it does not authorize reporting by itself. When the reporting gate permits it, send only task titles, summaries, step names, status, progress and time estimates to that configured server. If configuration is absent for an eligible task, keep doing the original task and explain how to enable monitoring once. Do not invent a server or send to an unrelated destination. Never include credentials, private file contents, source code, full prompts or tool outputs in reports. Summarize sensitive work at a high level. Keep secrets in the configuration file or environment, never CLI arguments or printed output. Remote endpoints must use HTTPS.

For account-based servers, the user obtains a personal reporting key by logging into the dashboard, changing the initial password, and opening “我的账号 → 个人上报密钥”. They may download `client.env` there. Ask them to configure it privately; never ask for their login password or print their key. Keys only permit reporting tasks owned by that account, not dashboard access, account management or task deletion. Regenerating/revoking a key, disabling an account or an administrator resetting its password invalidates the previous key. HTTP 401 means authentication failed: keep doing the task and explain that the user should update their private reporting configuration. Do not fall back to shared server secrets.

## Checkpoints

- At task start, choose one stable ID and send `start` with title, overview, harness and current step. Use `codex:<threadId>` when a Codex goal/thread ID is available; otherwise create a UUID once and reuse it. Concurrent tasks need separate IDs.
- Send `update` after finishing a milestone, changing the plan, or entering a materially different step. Send `block` for a real blocker, `pause` only when the task is paused, and `resume` when execution resumes.
- While actively executing, aim for a heartbeat every 60 seconds if the harness offers a safe opportunity. `heartbeat` means only that the harness is reachable; it must not claim progress. For a single uninterrupted long tool call, use a native periodic callback if available. Otherwise report before and after the call; update timeout on the dashboard does not prove task failure. Do not launch an unmanaged background heartbeat that would keep a dead task looking alive.
- Send `complete` only after the user's objective is actually achieved. Use `fail` for terminal failure or `cancel` for cancellation. Terminal tasks cannot be reopened; use a new ID for a new attempt.
- Report best known progress in 0–100. Prefer completed, weighted milestones to token usage or elapsed time. Omit progress or use `--unknown-progress` when it cannot be estimated honestly. Completion sets progress to 100 on the server.
- Estimate remaining active work yourself from the unfinished steps, their amount and complexity, expected durations and observed execution speed. Once scope is understood, send `--eta-seconds`; reassess at milestones or plan changes. Do not substitute a progress-percentage formula for a workload assessment. If there is not enough information, omit ETA or use `--clear-eta`; the dashboard displays “未完成评估” and never estimates ETA from progress. A progress or step update clears the previous estimate unless a new one is supplied. A heartbeat preserves it. Pause/block time is excluded from execution time and ETA.
- A monitoring failure must not stop or redefine the user's task. The reporter retries twice with the same event ID and saves failed events locally. At a later checkpoint, replay a saved event once using `replay --json <pending_file>`; duplicates and old arrivals will not overwrite newer status. Do not retry indefinitely. Summarize unresolved reporting failure when material.
- If the server rejects this task ID with HTTP 410, the user deleted its monitoring record. Stop reporting that ID, continue the original work, and do not recreate the record under a new ID unless the user asks to monitor it again. Deleting a monitoring record does not cancel the actual harness task.

## Common calls (any harness)

Replace `REPORTER` with the absolute script path and reuse the same task ID. No model-specific API is required.

```text
python REPORTER start --task-id deepseek:example-123 --harness deepseek --title "分析数据" --overview "清洗、分析并交付报告" --current-step "检查输入" --progress 0
python REPORTER update --task-id deepseek:example-123 --current-step "生成分析报告" --progress 60 --eta-seconds 180 --message "数据清洗已完成"
python REPORTER heartbeat --task-id deepseek:example-123
python REPORTER block --task-id deepseek:example-123 --message "等待缺失的数据"
python REPORTER resume --task-id deepseek:example-123 --current-step "继续分析"
python REPORTER complete --task-id deepseek:example-123 --current-step "报告已交付" --message "检查通过，任务完成"
```

Other harnesses use their own `--harness` name with the same protocol. Native callbacks may call the reporter with `--json -` and protocol JSON on stdin. Do not assume a DeepSeek harness has a specific built-in hook API; integrate with the callbacks that actually exist there.

## Codex goals

When `get_goal` is available, read the actual goal and keep its stable `threadId`. Do not infer completion or change the goal just to satisfy monitoring. The reporter accepts a saved JSON result via `--goal-file`; it maps the first objective line to title, plus ID, harness and status. Review/redact that line before reporting if necessary. Pass a concise safe summary via `--overview`; the full objective is not copied into it. Progress and ETA are never invented:

```text
python REPORTER update --goal-file goal-snapshot.json --current-step "验证实现" --progress 80
```

For `active` the reporter uses `running`; `complete` becomes `completed`; paused/blocked retain their meaning. Budget/usage limits map to paused. If the exact goal status is unknown, omit it in the common protocol and report the known step only. Use `update --goal-file` to retain the goal's actual status; the explicit commands such as `start` and `complete` intentionally override it.

If the harness lacks `get_goal`, use the common calls. Installing this skill enables discovery; it does not guarantee that every harness will automatically invoke it. A deterministic integration needs the harness's native lifecycle callbacks to call the same reporter.
