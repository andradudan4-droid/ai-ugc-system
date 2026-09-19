# Roles & Coordination

Multiple sessions work this repo at once. Each owns specific agents. Do not build agents
you do not own — message the session that owns them instead.

## Role assignment

| Role | Owns | Nature of work |
|------|------|----------------|
| **Strategy** | none — direction, review, routing | Decides scope, catches judgment errors, resolves blocks. Does not build. |
| **Writer** | Agent 0 (Intake), Agent 3 (Scriptwriter) | Per-brand. Fast, LLM-heavy. |
| **Miner** | Agent 1 (Ad miner), Agent 2 (Taxonomist) | Per-category. Browser-heavy, long-running. |
| **Producer** | Agent 4 (Render), Agent 5 (QA) | Per-batch. Spends money — requires explicit sign-off before any run. |

Agent −1 (Prospector) is complete and owned by Writer for maintenance reruns.

## What runs in parallel

Writer and Miner are independent and **must run simultaneously**:

- Agent 0 needs `targets.csv` only
- Agent 1 needs `targets.csv` only

Neither blocks the other. Run them at the same time.

The one real dependency: **Agent 3 needs `angles.json` from Agent 2.** Writer can build Agent 3
and test it against a stub, but cannot produce real scripts until Miner delivers. When Writer
reaches that point it does not idle — it messages Miner, then continues on the next brand's
Agent 0 while waiting.

Producer does nothing until Agent 3 has output AND spend is approved by Strategy.

## Shared state

Code is per-session (own worktree, own branch). **Data is shared.**

```
~/Desktop/ai-ugc-system/shared/data/     <- single source of truth for artifacts
```

Write finished artifacts there by absolute path. Do not keep them only in your worktree —
another session cannot see your branch.

| Artifact | Producer | Consumers |
|----------|----------|-----------|
| `targets.csv` | Writer | Writer, Miner |
| `brands/<slug>/brand.md` | Writer | Writer |
| `hooks.jsonl` | Miner | Miner |
| `angles.json` | Miner | Writer |
| `scripts.json` | Writer | Producer |

## Signalling — do not wait to be asked

`shared/STATUS.md` is an append-only log. **Append a line the moment you finish a stage or hit
a block.** Format:

```
2026-09-19T08:12Z  Miner   DONE    hooks.jsonl — 1,240 hooks from 38 brands
2026-09-19T08:40Z  Miner   DONE    angles.json — 14 clusters, 4 unclaimed
2026-09-19T09:02Z  Writer  BLOCKED Agent 3 needs angles.json
```

Read `STATUS.md` before starting any stage with a dependency.

When you produce an artifact another role is waiting on, **message that session directly** — do
not wait for Strategy to relay it. Sessions are addressed by their session id; ask Strategy for
the id once and keep it.

## Escalate to Strategy, do not decide yourself

- Any spend
- Any artifact format change
- Any scope change or new agent
- A data source that blocks you
