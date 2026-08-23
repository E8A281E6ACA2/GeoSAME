from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
COUNTS_PATH = ROOT / "results" / "paper_aggregate_counts.json"
EXPECTED_PATH = ROOT / "results" / "expected_metrics.json"


def _rate(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        raise ValueError(f"denominator must be positive, got {denominator}")
    if numerator < 0 or numerator > denominator:
        raise ValueError(f"invalid count pair: {numerator}/{denominator}")
    return numerator / denominator


def compute_metrics(counts: dict[str, Any]) -> dict[str, float]:
    main = counts["main_natural_study"]
    challenge = counts["challenge60_text_only_diagnostic"]
    external = counts["external_replication"]

    assert main["originals"] * main["slots_per_original"] == main["planned_slots"]
    assert main["generated_candidates"] + main["safe_abstentions"] == main["planned_slots"]
    assert main["system_accepted"] + main["natural_rejections"] == main["generated_candidates"]
    assert main["accepted_strict_yes"] == main["strict_primary_endpoint_successes"]

    tp, fn = challenge["tp"], challenge["fn"]
    fp, tn = challenge["fp"], challenge["tn"]
    assert tp + fn == challenge["gold_yes"]
    assert fp + tn == challenge["gold_no"]
    determinate = tp + fn + fp + tn
    assert determinate + challenge["gold_uncertain"] == 60

    sensitivity = _rate(tp, tp + fn)
    specificity = _rate(tn, tn + fp)
    mcc_denominator = math.sqrt((tp + fp) * (tp + fn) * (tn + fp) * (tn + fn))
    mcc = ((tp * tn) - (fp * fn)) / mcc_denominator

    return {
        "main.generated_rate": _rate(main["generated_candidates"], main["planned_slots"]),
        "main.strict_primary_endpoint": _rate(main["strict_primary_endpoint_successes"], main["planned_slots"]),
        "main.accepted_strict_yes_conditional": _rate(main["accepted_strict_yes"], main["system_accepted"]),
        "main.rejected_semantic_yes_rate": _rate(main["rejected_semantic_yes"], main["natural_rejections"]),
        "main.strict_false_rejection_rate": _rate(main["strict_false_rejections"], main["natural_rejections"]),
        "main.gate_recall_over_generated_strict_yes": _rate(main["accepted_strict_yes"], main["generated_strict_yes_diagnostic"]),
        "challenge60.accuracy": _rate(tp + tn, determinate),
        "challenge60.sensitivity": sensitivity,
        "challenge60.specificity": specificity,
        "challenge60.balanced_accuracy": (sensitivity + specificity) / 2,
        "challenge60.matthews_correlation": mcc,
        "external.formal_acceptance": _rate(external["formal_accepted"], external["attempted"]),
        "external.teacher_semantic_yes_a1": _rate(external["teacher_semantic_yes_a1"], external["teacher_evaluated"]),
        "external.teacher_semantic_yes_a2": _rate(external["teacher_semantic_yes_a2"], external["teacher_evaluated"]),
    }


def main() -> None:
    counts = json.loads(COUNTS_PATH.read_text(encoding="utf-8"))
    expected = json.loads(EXPECTED_PATH.read_text(encoding="utf-8"))
    metrics = compute_metrics(counts)

    for name, expected_value in expected.items():
        actual = metrics[name]
        if not math.isclose(actual, expected_value, rel_tol=0.0, abs_tol=1e-12):
            raise AssertionError(f"{name}: expected {expected_value}, got {actual}")

    printable = {
        "status": "PASS",
        "scope": "Aggregate arithmetic and denominator guards only.",
        "metrics": metrics,
    }
    print(json.dumps(printable, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
