#!/usr/bin/env python3
"""
Codex Cost Analyzer — CodexScope-compatible local session cost analysis.

Usage:
    python3 analyze.py [--cwd PATTERN] [--days N]
"""

import argparse
import json
import os
import glob
from collections import defaultdict
from typing import Optional, Dict, Any

# CodexScope pricing rules (USD per million tokens)
# Synced from: generate_codex_data.go → modelPricingUSDPerM
PRICING = [
    {"label": "gpt-5.5", "patterns": ["gpt-5.5"], "input": 5.00, "cached": 0.50, "output": 30.00},
    {"label": "gpt-5.4 mini", "patterns": ["gpt-5.4-mini", "gpt_5.4_mini", "gpt 5.4 mini"], "input": 0.75, "cached": 0.075, "output": 4.50},
    {"label": "gpt-5.4", "patterns": ["gpt-5.4"], "input": 2.50, "cached": 0.25, "output": 15.00},
    {"label": "gpt-5.3 codex spark", "patterns": ["gpt-5.3-codex-spark", "gpt_5.3_codex_spark", "gpt 5.3 codex spark"], "input": 1.75, "cached": 0.175, "output": 14.00},
    {"label": "gpt-5.3 codex", "patterns": ["gpt-5.3-codex", "gpt_5.3_codex", "gpt 5.3 codex"], "input": 1.75, "cached": 0.175, "output": 14.00},
    {"label": "gpt-5.2 codex", "patterns": ["gpt-5.2-codex", "gpt_5.2_codex", "gpt 5.2 codex"], "input": 1.75, "cached": 0.175, "output": 14.00},
    {"label": "gpt-5 / 5.1 codex", "patterns": ["gpt-5.1-codex", "gpt_5.1_codex", "gpt 5.1 codex", "gpt-5-codex", "gpt_5_codex", "gpt 5 codex", "gpt-5"], "input": 1.25, "cached": 0.125, "output": 10.00},
]

CNY_RATE = 7.25  # approximate USD→CNY


def pricing_for_model(model: str) -> Optional[dict]:
    model_lower = model.lower()
    for rule in PRICING:
        for pat in rule["patterns"]:
            if pat in model_lower:
                return rule
    return None


def price_usage(model: str, usage: dict) -> dict:
    """Mirrors CodexScope priceUsage() exactly."""
    input_tokens = max(0, usage.get("input_tokens", 0))
    cached_raw = max(0, usage.get("cached_input_tokens", 0))
    output_tokens = max(0, usage.get("output_tokens", 0))
    reasoning_raw = max(0, usage.get("reasoning_output_tokens", 0))

    cached_tokens = cached_raw
    if input_tokens > 0 and cached_tokens > input_tokens:
        cached_tokens = input_tokens

    billable_input = max(0, input_tokens - cached_tokens)
    billed_reasoning = reasoning_raw
    if output_tokens > 0 and billed_reasoning > output_tokens:
        billed_reasoning = output_tokens

    visible_output = max(0, output_tokens - billed_reasoning)
    priced_tokens = billable_input + cached_tokens + visible_output + billed_reasoning

    rule = pricing_for_model(model)
    if rule is None:
        return {"total": 0, "priced_tokens": priced_tokens, "unpriced_tokens": priced_tokens, "model_label": "unknown"}

    m = 1_000_000.0
    return {
        "input_cost": billable_input * rule["input"] / m,
        "cached_cost": cached_tokens * rule["cached"] / m,
        "output_cost": visible_output * rule["output"] / m,
        "reasoning_cost": billed_reasoning * rule["output"] / m,
        "total": (billable_input * rule["input"] + cached_tokens * rule["cached"]
                  + visible_output * rule["output"] + billed_reasoning * rule["output"]) / m,
        "priced_tokens": priced_tokens,
        "billable_input": billable_input,
        "cached_tokens": cached_tokens,
        "visible_output": visible_output,
        "reasoning_tokens": billed_reasoning,
        "model_label": rule["label"],
    }


def parse_session_file(fpath: str) -> Optional[dict]:
    """Parse one JSONL session file, returning metadata + token events."""
    sid = os.path.splitext(os.path.basename(fpath))[0]
    cwd = ""
    model = "unknown"
    usage_events = []
    completion_count = 0
    failure_count = 0
    prev_total = None

    try:
        with open(fpath, 'r') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue

                top_type = obj.get("type", "")
                payload = obj.get("payload", {})
                payload_type = payload.get("type", "")

                if top_type == "session_meta":
                    if payload.get("id"):
                        sid = payload["id"]
                    if payload.get("cwd"):
                        cwd = payload["cwd"]
                elif top_type == "turn_context":
                    if payload.get("model"):
                        model = payload["model"]
                    if payload.get("cwd"):
                        cwd = payload["cwd"]
                elif payload_type == "token_count":
                    info = payload.get("info", {})
                    last_usage = info.get("last_token_usage", {})
                    total_usage = info.get("total_token_usage", {})

                    usage = None
                    if total_usage and prev_total is not None:
                        usage = {
                            "input_tokens": max(0, total_usage.get("input_tokens", 0) - prev_total.get("input_tokens", 0)),
                            "cached_input_tokens": max(0, total_usage.get("cached_input_tokens", 0) - prev_total.get("cached_input_tokens", 0)),
                            "output_tokens": max(0, total_usage.get("output_tokens", 0) - prev_total.get("output_tokens", 0)),
                            "reasoning_output_tokens": max(0, total_usage.get("reasoning_output_tokens", 0) - prev_total.get("reasoning_output_tokens", 0)),
                            "total_tokens": max(0, total_usage.get("total_tokens", 0) - prev_total.get("total_tokens", 0)),
                        }
                    elif last_usage:
                        usage = last_usage

                    if total_usage:
                        prev_total = total_usage

                    if usage:
                        cost_info = price_usage(model, usage)
                        usage_events.append({
                            "ts": obj.get("timestamp", ""),
                            "usage": usage,
                            "model": model,
                            "cost": cost_info,
                        })
                elif payload_type == "task_complete":
                    completion_count += 1
                elif payload_type in ("error", "turn_aborted"):
                    failure_count += 1
    except Exception as e:
        return None

    return {
        "sid": sid,
        "file": fpath,
        "cwd": cwd,
        "model": model,
        "usage_events": usage_events,
        "completions": completion_count,
        "failures": failure_count,
    }


def analyze(cwd_pattern: str, days: int = 0):
    sessions_dir = os.path.expanduser("~/.codex/sessions")
    # Walk all year/month/day subdirs
    session_files = glob.glob(os.path.join(sessions_dir, "**/*.jsonl"), recursive=True)

    sessions = []
    all_scanned = 0

    for fpath in sorted(session_files):
        all_scanned += 1
        parsed = parse_session_file(fpath)
        if parsed is None:
            continue
        if cwd_pattern.lower() not in parsed["cwd"].lower():
            continue
        if parsed["usage_events"]:
            sessions.append(parsed)

    if not sessions:
        print(f"Scanned {all_scanned} session files. No sessions matched CWD '*{cwd_pattern}*'.")
        return

    # Aggregate
    total_cost = 0
    total_input = 0
    total_cached = 0
    total_output = 0
    total_reasoning = 0
    total_requests = 0
    total_completions = 0
    total_failures = 0
    model_usage = defaultdict(lambda: {"cost": 0, "input": 0, "cached": 0, "output": 0, "reasoning": 0, "requests": 0})

    for s in sessions:
        sc = 0
        si = sca = so = sr = 0
        for ev in s["usage_events"]:
            u = ev["usage"]
            c = ev["cost"]
            sc += c["total"]
            si += u.get("input_tokens", 0)
            sca += u.get("cached_input_tokens", 0)
            so += u.get("output_tokens", 0)
            sr += u.get("reasoning_output_tokens", 0)
            m = ev["model"]
            model_usage[m]["cost"] += c["total"]
            model_usage[m]["input"] += u.get("input_tokens", 0)
            model_usage[m]["cached"] += u.get("cached_input_tokens", 0)
            model_usage[m]["output"] += u.get("output_tokens", 0)
            model_usage[m]["reasoning"] += u.get("reasoning_output_tokens", 0)
            model_usage[m]["requests"] += 1

        total_cost += sc
        total_input += si
        total_cached += sca
        total_output += so
        total_reasoning += sr
        total_requests += len(s["usage_events"])
        total_completions += s["completions"]
        total_failures += s["failures"]

        cwd_short = os.path.basename(s["cwd"]) if s["cwd"] else "?"
        print(f"Session {s['sid'][:16]} | CWD: {cwd_short} | Model: {s['model'][:30]}")
        print(f"  Requests: {len(s['usage_events'])} | Completions: {s['completions']} | Failures: {s['failures']}")
        print(f"  Input: {si:,} | Cached: {sca:,} | Output: {so:,} | Reasoning: {sr:,}")
        print(f"  Cost: ${sc:.4f}")
        print()

    print("=" * 60)
    print(f"SUMMARY — {cwd_pattern} (CodexScope methodology)")
    print("=" * 60)
    print(f"Sessions: {len(sessions)}")
    print(f"Requests: {total_requests} | Completions: {total_completions} | Failures: {total_failures}")
    print()
    print("Token Usage:")
    print(f"  Input tokens:     {total_input:>14,}")
    print(f"  Cached tokens:    {total_cached:>14,}")
    print(f"  Output tokens:    {total_output:>14,}")
    print(f"  Reasoning tokens: {total_reasoning:>14,}")
    print(f"  Total tokens:     {(total_input + total_output):>14,}")
    print()
    print(f"Estimated Cost: ${total_cost:.4f} USD")
    print(f"Estimated Cost: ¥{total_cost * CNY_RATE:.2f} CNY (≈{CNY_RATE} rate)")
    print()
    print("By Model:")
    for model in sorted(model_usage.keys(), key=lambda m: model_usage[m]["cost"], reverse=True):
        mu = model_usage[model]
        rule = pricing_for_model(model)
        label = rule["label"] if rule else "unknown"
        print(f"  {label} ({model[:50]}):")
        print(f"    Requests: {mu['requests']} | Cost: ${mu['cost']:.4f}")
        print(f"    Input: {mu['input']:,} | Cached: {mu['cached']:,} | Output: {mu['output']:,} | Reasoning: {mu['reasoning']:,}")
        print()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Codex cost analyzer (CodexScope methodology)")
    parser.add_argument("--cwd", type=str, default=None,
                        help="Filter sessions by CWD substring (default: basename of PWD)")
    parser.add_argument("--days", type=int, default=0,
                        help="Only include last N days (0 = all history)")
    args = parser.parse_args()

    cwd_pattern = args.cwd or os.path.basename(os.getcwd())
    analyze(cwd_pattern, args.days)
