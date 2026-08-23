from __future__ import annotations

import csv
import json
import re
import unicodedata
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from statistics import median
from typing import Any, Iterable

from .candidate_quality import candidate_output_issues, candidate_semantic_boundary_issues


_ANGLE_FORMS_RE = re.compile(r"(?:\\angle|∠)", re.IGNORECASE)
_NON_ALNUM_RE = re.compile(r"[^a-z0-9]+")


@dataclass(frozen=True)
class GateThresholds:
    median_normalized_unique_per_problem_min: float
    global_extra_normalized_duplicate_rate_max: float
    structural_recognizable_rewrite_rate_min: float
    new_implicit_condition_count_max: int
    answer_solution_metadata_leakage_count_max: int


def normalize_candidate_text(text: str) -> str:
    """Normalize surface formatting for exact-duplicate auditing.

    This deliberately stays conservative: case, whitespace, punctuation, Unicode
    compatibility variants, and angle-symbol formatting are ignored. Lexical
    substitutions such as ``find`` -> ``determine`` are *not* collapsed.
    """

    value = unicodedata.normalize("NFKC", str(text or "")).lower()
    value = _ANGLE_FORMS_RE.sub("angle", value)
    return _NON_ALNUM_RE.sub("", value)


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as handle:
        for source_line, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            record = json.loads(line)
            record["_source_line"] = source_line
            records.append(record)
    return records


def flatten_generation_records(records: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    flattened: list[dict[str, Any]] = []
    for record in records:
        variants = record.get("variants") or []
        if not variants:
            variants = [{}]
        for variant_index, variant in enumerate(variants, start=1):
            candidate_text = str(variant.get("text", "")).strip()
            auto = variant.get("auto_verification") or {}
            parse_payload = variant.get("predicate_parse") or {}
            output_issues = list(variant.get("output_quality_issues") or [])
            if not output_issues:
                output_issues = candidate_output_issues(candidate_text)
            semantic_issues = list(variant.get("semantic_boundary_issues") or [])
            if not semantic_issues:
                semantic_issues = candidate_semantic_boundary_issues(
                    str(record.get("original_text", "")), candidate_text
                )
            flattened.append(
                {
                    "source_line": record.get("_source_line"),
                    "problem_id": str(record.get("problem_id", "")),
                    "method": str(record.get("method", "")),
                    "intensity": str(record.get("intensity", "")),
                    "replicate": int(record.get("replicate") or 1),
                    "variant_index": variant_index,
                    "status": str(record.get("status", "")),
                    "original_text": str(record.get("original_text", "")),
                    "candidate_text": candidate_text,
                    "normalized_candidate": normalize_candidate_text(candidate_text),
                    "image_path": str(record.get("image_path", "")),
                    "output_quality_issues": output_issues,
                    "output_quality_passed": not output_issues,
                    "semantic_boundary_issues": semantic_issues,
                    "semantic_boundary_passed": not semantic_issues,
                    "revision_count": len(variant.get("revision_history") or []),
                    "predicate_consistent": auto.get("predicate_consistent"),
                    "no_new_points": auto.get("no_new_points"),
                    "numeric_consistent": auto.get("numeric_consistent"),
                    "target_consistent": auto.get("target_consistent"),
                    "term_preserved": auto.get("term_preserved"),
                    "answer_consistent": auto.get("answer_consistent"),
                    "auto_notes": auto.get("notes") or [],
                    "missing_predicates": parse_payload.get("missing_predicates") or [],
                    "extra_predicates": parse_payload.get("extra_predicates") or [],
                }
            )
    return flattened


def experimental_key(row: dict[str, Any]) -> tuple[str, str, str, int, int]:
    return (
        str(row["problem_id"]),
        str(row["method"]),
        str(row["intensity"]),
        int(row["replicate"]),
        int(row["variant_index"]),
    )


def duplicate_groups(rows: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        groups[str(row["normalized_candidate"])].append(row)
    output: list[dict[str, Any]] = []
    group_index = 0
    for normalized, members in sorted(groups.items()):
        if not normalized or len(members) < 2:
            continue
        group_index += 1
        problem_ids = sorted({str(member["problem_id"]) for member in members})
        for member in sorted(members, key=experimental_key):
            output.append(
                {
                    "duplicate_group_id": f"dup_{group_index:03d}",
                    "group_size": len(members),
                    "cross_problem_duplicate": len(problem_ids) > 1,
                    "problem_ids_in_group": problem_ids,
                    **member,
                }
            )
    return output


def per_problem_metrics(rows: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[str(row["problem_id"])].append(row)
    output: list[dict[str, Any]] = []
    for problem_id, members in sorted(grouped.items()):
        normalized = [str(member["normalized_candidate"]) for member in members]
        unique_count = len(set(normalized))
        output.append(
            {
                "problem_id": problem_id,
                "candidate_count": len(members),
                "normalized_unique_count": unique_count,
                "extra_normalized_duplicate_count": len(members) - unique_count,
                "extra_normalized_duplicate_rate": (
                    (len(members) - unique_count) / len(members) if members else 0.0
                ),
            }
        )
    return output


def load_manual_review(path: Path, decision_column: str) -> dict[tuple[str, str, str, int, int], dict[str, str]]:
    decisions: dict[tuple[str, str, str, int, int], dict[str, str]] = {}
    with path.open(encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            key = (
                row["problem_id"],
                row["method"],
                row["intensity"],
                int(row.get("replicate") or 1),
                int(row.get("variant_index") or 1),
            )
            decision = str(row.get(decision_column, "")).strip().lower()
            if decision not in {"yes", "no"}:
                raise ValueError(f"invalid {decision_column}={decision!r} for {key}")
            decisions[key] = dict(row)
    return decisions


def threshold_config(design: dict[str, Any]) -> GateThresholds:
    values = design["thresholds"]
    return GateThresholds(
        median_normalized_unique_per_problem_min=float(values["median_normalized_unique_per_problem_min"]),
        global_extra_normalized_duplicate_rate_max=float(values["global_extra_normalized_duplicate_rate_max"]),
        structural_recognizable_rewrite_rate_min=float(values["structural_recognizable_rewrite_rate_min"]),
        new_implicit_condition_count_max=int(values["new_implicit_condition_count_max"]),
        answer_solution_metadata_leakage_count_max=int(values["answer_solution_metadata_leakage_count_max"]),
    )


def compute_gate_metrics(
    rows: list[dict[str, Any]],
    design: dict[str, Any],
    structural_review: dict[tuple[str, str, str, int, int], dict[str, str]],
    implicit_review: dict[tuple[str, str, str, int, int], dict[str, str]],
) -> dict[str, Any]:
    thresholds = threshold_config(design)
    problem_metrics = per_problem_metrics(rows)
    unique_counts = [int(row["normalized_unique_count"]) for row in problem_metrics]
    global_unique = len({str(row["normalized_candidate"]) for row in rows})
    global_extra = len(rows) - global_unique
    structural_rows = [row for row in rows if row["intensity"] == "structural"]
    structural_keys = {experimental_key(row) for row in structural_rows}
    missing_structural = sorted(structural_keys - set(structural_review))
    if missing_structural:
        raise ValueError(f"structural review missing {len(missing_structural)} rows: {missing_structural[:3]}")
    all_keys = {experimental_key(row) for row in rows}
    missing_implicit = sorted(all_keys - set(implicit_review))
    if missing_implicit:
        raise ValueError(f"implicit-condition review missing {len(missing_implicit)} rows: {missing_implicit[:3]}")

    structural_yes = sum(
        structural_review[key]["recognizable_structural_rewrite"].strip().lower() == "yes"
        for key in structural_keys
    )
    structural_rate = structural_yes / len(structural_rows) if structural_rows else 0.0
    implicit_count = sum(
        implicit_review[key]["new_implicit_condition"].strip().lower() == "yes"
        for key in all_keys
    )
    leakage_count = sum(bool(row["output_quality_issues"]) for row in rows)
    median_unique = float(median(unique_counts)) if unique_counts else 0.0
    duplicate_rate = global_extra / len(rows) if rows else 0.0

    checks = {
        "median_normalized_unique_per_problem": {
            "value": median_unique,
            "operator": ">=",
            "threshold": thresholds.median_normalized_unique_per_problem_min,
            "passed": median_unique >= thresholds.median_normalized_unique_per_problem_min,
        },
        "global_extra_normalized_duplicate_rate": {
            "value": duplicate_rate,
            "operator": "<=",
            "threshold": thresholds.global_extra_normalized_duplicate_rate_max,
            "passed": duplicate_rate <= thresholds.global_extra_normalized_duplicate_rate_max,
        },
        "structural_recognizable_rewrite_rate": {
            "value": structural_rate,
            "numerator": structural_yes,
            "denominator": len(structural_rows),
            "operator": ">=",
            "threshold": thresholds.structural_recognizable_rewrite_rate_min,
            "passed": structural_rate >= thresholds.structural_recognizable_rewrite_rate_min,
        },
        "new_implicit_condition_count": {
            "value": implicit_count,
            "operator": "<=",
            "threshold": thresholds.new_implicit_condition_count_max,
            "passed": implicit_count <= thresholds.new_implicit_condition_count_max,
        },
        "answer_solution_metadata_leakage_count": {
            "value": leakage_count,
            "operator": "<=",
            "threshold": thresholds.answer_solution_metadata_leakage_count_max,
            "passed": leakage_count <= thresholds.answer_solution_metadata_leakage_count_max,
        },
    }
    return {
        "schema_version": "geosynq.diversity_gate_audit.1",
        "gate_id": design.get("gate_id"),
        "candidate_rows": len(rows),
        "distinct_problem_ids": len({row["problem_id"] for row in rows}),
        "unique_experimental_keys": len({experimental_key(row) for row in rows}),
        "status_counts": dict(Counter(str(row["status"]) for row in rows)),
        "global_normalized_unique_count": global_unique,
        "global_extra_normalized_duplicate_count": global_extra,
        "cross_problem_duplicate_group_count": len({
            row["duplicate_group_id"]
            for row in duplicate_groups(rows)
            if row["cross_problem_duplicate"]
        }),
        "checks": checks,
        "overall_gate_passed": all(check["passed"] for check in checks.values()),
    }
