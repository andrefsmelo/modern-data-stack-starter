#!/usr/bin/env python3
"""Send structured Slack notifications from GitHub Actions workflows.

Usage:
  python notify_slack.py \
    --status success|failure|warning \
    --job dbt-build \
    --run-url https://... \
    --run-number 42 \
    --duration 300 \
    --dbt-results target/run_results.json \
    --dbt-manifest target/manifest.json \
    --freshness-results target/sources.json

Environment variables:
  SLACK_WEBHOOK_URL  Slack incoming webhook URL (required)
"""

import json
import os
import sys
from urllib.request import Request, urlopen


def _load_json(path):
    if not path or not os.path.isfile(path):
        return None
    with open(path) as f:
        return json.load(f)


def _dbt_summary(run_results, manifest):
    if not run_results:
        return None
    unique_id_map = {}
    if manifest:
        for node in list(manifest.get("nodes", {}).values()) + list(
            manifest.get("sources", {}).values()
        ):
            unique_id_map[node.get("unique_id", "")] = node.get("name", node.get("unique_id", ""))

    models_ok, models_fail = 0, 0
    tests_ok, tests_fail = 0, 0
    skipped = 0
    error_details = []

    for result in run_results.get("results", []):
        unique_id = result.get("unique_id", "")
        status = result.get("status", "")
        name = unique_id_map.get(unique_id, unique_id)
        resource_type = unique_id.split(".")[1] if "." in unique_id else ""

        if status == "success":
            if resource_type == "test":
                tests_ok += 1
            else:
                models_ok += 1
        elif status in ("error", "fail", "runtime error"):
            if resource_type == "test":
                tests_fail += 1
            else:
                models_fail += 1
            error_details.append(f"  - {name}: {result.get('message', status)}")
        elif status == "skipped":
            skipped += 1
        elif status == "warn":
            tests_ok += 1
            error_details.append(f"  - {name}: warn")

    lines = [
        f"*Models:* {models_ok} ok, {models_fail} failed",
        f"*Tests:* {tests_ok} ok, {tests_fail} failed, {skipped} skipped",
    ]
    if error_details:
        lines.append("*Errors/warnings:*")
        lines.extend(error_details[:20])
    return "\n".join(lines)


def _freshness_summary(freshness_results):
    if not freshness_results:
        return None
    results = freshness_results.get("results", []) if isinstance(freshness_results, dict) else []
    lines = []
    for result in results:
        unique_id = result.get("unique_id", "")
        parts = unique_id.split(".")
        name = ".".join(parts[-2:]) if len(parts) >= 2 else unique_id
        status = result.get("status", "")
        if status in ("runtime error", "error"):
            msg = result.get("message") or status
            lines.append(f"  :warning: {name}: {msg}")
            continue
        age_seconds = result.get("max_loaded_at_time_ago_in_s")
        age = f"{int(age_seconds)}s" if isinstance(age_seconds, (int, float)) else ""
        icon = {
            "pass": ":white_check_mark:",
            "warn": ":warning:",
            "fail": ":x:",
        }.get(status, ":grey_question:")
        suffix = f" (age: {age})" if age else ""
        lines.append(f"  {icon} {name}{suffix}")
    return "\n".join(lines) if lines else None


def build_payload(status, job, run_url, run_number, duration, dbt_summary, freshness_summary):
    emoji = {"success": ":white_check_mark:", "failure": ":x:", "warning": ":warning:"}.get(
        status, ":grey_question:"
    )
    title = f"{emoji} {job} {status}"

    text_lines = [title]
    if run_url:
        text_lines.append(f"<{run_url}|Run #{run_number}>")
    if duration:
        mins, secs = divmod(int(duration), 60)
        text_lines.append(f"*Duration:* {mins}m {secs}s")

    if dbt_summary:
        text_lines.append(f"\n{dbt_summary}")
    if freshness_summary:
        text_lines.append(f"\n*Freshness:*\n{freshness_summary}")

    text = "\n".join(text_lines)

    color = {"success": "#36a64f", "failure": "#e01e5a", "warning": "#ecb22e"}.get(status, "#808080")

    return {
        "text": title,
        "attachments": [
            {"color": color, "text": text, "mrkdwn_in": ["text"]},
        ],
    }


def send(payload):
    url = os.environ.get("SLACK_WEBHOOK_URL")
    if not url:
        print("SLACK_WEBHOOK_URL not set — skipping notification.")
        return
    data = json.dumps(payload).encode()
    req = Request(url, data=data, headers={"Content-Type": "application/json"})
    resp = urlopen(req)
    print(f"Slack responded with HTTP {resp.status}")


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Send Slack notification for a workflow run")
    parser.add_argument("--status", required=True, choices=["success", "failure", "warning"])
    parser.add_argument("--job", required=True, help="Job name, e.g. dbt-build")
    parser.add_argument("--run-url", default="", help="GitHub Actions run URL")
    parser.add_argument("--run-number", default="", help="GitHub Actions run number")
    parser.add_argument("--duration", type=int, default=0, help="Duration in seconds")
    parser.add_argument("--dbt-results", default="", help="Path to run_results.json")
    parser.add_argument("--dbt-manifest", default="", help="Path to manifest.json")
    parser.add_argument("--freshness-results", default="", help="Path to sources.json")
    args = parser.parse_args()

    run_results = _load_json(args.dbt_results)
    manifest = _load_json(args.dbt_manifest)
    freshness = _load_json(args.freshness_results)

    dbt_summary = _dbt_summary(run_results, manifest)
    fresh_summary = _freshness_summary(freshness)

    payload = build_payload(
        status=args.status,
        job=args.job,
        run_url=args.run_url,
        run_number=args.run_number,
        duration=args.duration,
        dbt_summary=dbt_summary,
        freshness_summary=fresh_summary,
    )
    send(payload)


if __name__ == "__main__":
    main()