---
name: codex-cost-analyzer
description: Analyze Codex session costs using CodexScope pricing methodology. Parses ~/.codex/sessions JSONL logs, filters by CWD, applies per-model USD pricing rules, and outputs token + cost breakdowns per session and per model.
---

# Codex Cost Analyzer

Analyze local Codex session costs using the same methodology as [CodexScope](https://github.com/JUk1-GH/CodexScope).

## When to use

- User asks "这个项目 codex 花了多少钱" / "analyze codex cost for this project"
- User wants a token usage + cost breakdown for Codex sessions
- User asks about codex quota consumption in a specific directory

## How it works

1. Scans `~/.codex/sessions/YYYY/MM/DD/*.jsonl`
2. Parses `session_meta` / `turn_context` for CWD and model
3. Extracts `token_count` events, computing deltas from cumulative `total_token_usage`
4. Falls back to `last_token_usage` when no prior cumulative snapshot exists
5. Applies CodexScope pricing rules (USD per million tokens)

## Pricing rules (synced from CodexScope `generate_codex_data.go`)

| Model | Input | Cached | Output |
|---|---|---|---|
| gpt-5.5 | $5.00 | $0.50 | $30.00 |
| gpt-5.4 | $2.50 | $0.25 | $15.00 |
| gpt-5.4-mini | $0.75 | $0.075 | $4.50 |
| gpt-5.3-codex / spark | $1.75 | $0.175 | $14.00 |
| gpt-5.2-codex | $1.75 | $0.175 | $14.00 |
| gpt-5 / 5.1 codex | $1.25 | $0.125 | $10.00 |

## Cost formula

```
billable_input = input_tokens - cached_tokens
reasoning_cost = reasoning_tokens × output_price / 1M
output_cost = (output_tokens - reasoning_tokens) × output_price / 1M
input_cost = billable_input × input_price / 1M
cached_cost = cached_tokens × cached_price / 1M
total = input_cost + cached_cost + output_cost + reasoning_cost
```

## Execution

Run the analysis script directly:

```bash
python3 scripts/analyze.py [--cwd PATTERN] [--days N]
```

- `--cwd PATTERN`: filter sessions by CWD substring (default: basename of current directory)
- `--days N`: only include sessions from last N days (default: 0 = all history)

## Output

Per-session: sid, CWD, model, request/completion/failure counts, token breakdown, cost.
Summary: total sessions, requests, tokens by type, total cost (USD + CNY estimate), per-model breakdown.

## Pitfalls

- Codex logs cumulative `total_token_usage`; the script computes per-event deltas. If a session file is truncated or rotated mid-session, the first event after the gap may show inflated token counts (it falls back to `last_token_usage` which is absolute, not delta).
- Sessions with no `turn_context` or `session_meta` CWD will not match directory filters.
- Pricing rules must be manually synced with CodexScope when OpenAI changes prices or adds new models. The canonical source is `modelPricingUSDPerM` in `generate_codex_data.go`.
- CNY conversion uses a hardcoded ~7.25 rate. Update in the script if needed.
