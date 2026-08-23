from __future__ import annotations

from dataclasses import asdict
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from geosynq.verifiers import verify_candidate


def main() -> None:
    payload = json.loads((Path(__file__).with_name("example_input.json")).read_text(encoding="utf-8"))
    source = payload["source"]
    candidate = payload["candidate"]

    result = verify_candidate(
        original_text=source["text"],
        candidate_text=candidate["text"],
        original_logic_forms=source["logic_forms"],
        candidate_logic_forms=candidate["logic_forms"],
        original_answer_text=source["answer"],
        candidate_answer_text=candidate["answer"],
    )

    required = {
        "predicate_consistent": result.predicate_consistent,
        "no_new_points": result.no_new_points,
        "numeric_consistent": result.numeric_consistent,
        "target_consistent": result.target_consistent is True,
        "term_preserved": result.term_preserved,
        "answer_consistent": result.answer_consistent is True,
    }
    report = {
        "problem_id": payload["problem_id"],
        "passed": all(required.values()),
        "required_checks": required,
        "verification": asdict(result),
    }
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))

    if not report["passed"]:
        raise SystemExit("Minimal example failed its required checks.")


if __name__ == "__main__":
    main()
