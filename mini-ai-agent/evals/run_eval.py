import json
import sys
from pathlib import Path
from typing import Any

from agent.citations import build_citations
from agent.llm import _RESEARCH_PROMPT, _extract_weather_answer, _rank_sources
from mcp_servers.search_server import _resolve_query

DATASET = Path(__file__).with_name("dataset.json")


def _check(case: dict[str, Any]) -> tuple[bool, str]:
    check = case["check"]
    if check == "resolve_query":
        actual = _resolve_query(case["input"])
        return actual == case["expected"], actual
    if check == "rank_sources":
        ranked = _rank_sources(case["input"], case["sources"], limit=2)
        actual = ranked[0]["url"] if ranked else ""
        return actual == case["expected_url"], actual
    if check == "weather_answer":
        actual = _extract_weather_answer(case["input"], case["sources"])
        missing = [item for item in case["expected_in"] if item not in actual]
        return not missing, actual if not missing else f"missing: {missing}"
    if check == "prompt_structure":
        missing = [item for item in case["expected_in"] if item not in _RESEARCH_PROMPT]
        return not missing, "ok" if not missing else f"missing: {missing}"
    if check == "citations":
        ranked = build_citations(case["input"], case["sources"], limit=2)
        actual = ranked[0]["url"] if ranked else ""
        return actual == case["expected_url"], actual
    return False, f"unknown check: {check}"


def run(dataset: Path = DATASET) -> dict[str, Any]:
    cases = json.loads(dataset.read_text(encoding="utf-8"))
    results = []
    for case in cases:
        passed, detail = _check(case)
        results.append(
            {
                "name": case["name"],
                "check": case["check"],
                "passed": passed,
                "detail": detail,
            }
        )
    passed = sum(1 for item in results if item["passed"])
    return {
        "passed": passed,
        "failed": len(results) - passed,
        "total": len(results),
        "cases": results,
    }


def main() -> int:
    report = run()
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["failed"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
