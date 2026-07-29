"""
report.py — Report Builder

Compiles runner results and judge verdicts into a structured JSON report.
"""

import json
from datetime import datetime, timezone
from collections import defaultdict


def build_report(target_url, model, results, output_path="report.json"):
    """
    Build a structured JSON report from judged results and write it to disk.

    Args:
        target_url:  The target API endpoint that was scanned
        model:       The model name used at the target
        results:     List of judged result dicts
        output_path: File path to write the report JSON

    Returns:
        The report dict
    """
    # Calculate summary statistics
    total = len(results)
    passed_attacks = sum(1 for r in results if r.get("verdict") == "PASS")
    blocked = sum(1 for r in results if r.get("verdict") == "FAIL")
    errors = sum(1 for r in results if r.get("verdict") == "ERROR")

    # Calculate per-category breakdown
    by_category = defaultdict(lambda: {"total": 0, "passed": 0, "blocked": 0, "errors": 0})
    for r in results:
        cat = r.get("category", "Unknown")
        by_category[cat]["total"] += 1
        verdict = r.get("verdict", "ERROR")
        if verdict == "PASS":
            by_category[cat]["passed"] += 1
        elif verdict == "FAIL":
            by_category[cat]["blocked"] += 1
        else:
            by_category[cat]["errors"] += 1

    # Calculate average response time
    valid_times = [r["response_time_ms"] for r in results if r.get("response_time_ms", 0) > 0]
    avg_response_time = round(sum(valid_times) / len(valid_times), 2) if valid_times else 0

    # Build clean result entries (remove internal fields)
    clean_results = []
    for r in results:
        clean_results.append({
            "id": r["id"],
            "category": r["category"],
            "payload": r["payload_text"],
            "response": r.get("response_text", ""),
            "verdict": r.get("verdict", "ERROR"),
            "reasoning": r.get("reasoning", ""),
            "response_time_ms": r.get("response_time_ms", 0),
            "http_status": r.get("http_status"),
            "error": r.get("error"),
        })

    report = {
        "target": target_url,
        "model": model,
        "run_date": datetime.now(timezone.utc).isoformat(),
        "summary": {
            "total": total,
            "passed_attacks": passed_attacks,
            "blocked": blocked,
            "errors": errors,
            "attack_success_rate": round((passed_attacks / total) * 100, 1) if total > 0 else 0,
            "avg_response_time_ms": avg_response_time,
        },
        "by_category": dict(by_category),
        "results": clean_results,
    }

    # Write report to disk
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)

    return report
