from __future__ import annotations

from collections import defaultdict
from dataclasses import asdict, dataclass
from typing import Any, Iterable, Sequence

from .candidate_quality import candidate_output_issues, candidate_semantic_boundary_issues
from .diversity_audit import (
    experimental_key,
    flatten_generation_records,
    normalize_candidate_text,
)
from .predicate_parser import compare_predicates, normalize_predicate_vocabulary
from .verifiers import verify_candidate


DUPLICATE_REASON = "normalized_duplicate"
SEMANTIC_BOUNDARY_REASON = "semantic_boundary_violation"

ExperimentalKey = tuple[str, str, str, int, int]


@dataclass(frozen=True)
class CandidateAcceptance:
    accepted: bool
    rejection_reasons: tuple[str, ...]
    normalized_candidate: str
    output_quality_issues: tuple[str, ...]
    semantic_boundary_issues: tuple[str, ...]
    verifier_failures: tuple[str, ...]
    verifier_payload: dict[str, Any]
    predicate_comparison: dict[str, Any] | None

    def as_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["rejection_reasons"] = list(self.rejection_reasons)
        payload["output_quality_issues"] = list(self.output_quality_issues)
        payload["semantic_boundary_issues"] = list(self.semantic_boundary_issues)
        payload["verifier_failures"] = list(self.verifier_failures)
        return payload


def _slot_payload(row: dict[str, Any]) -> dict[str, Any]:
    key = experimental_key(row)
    return {
        "experimental_key": list(key),
        "problem_id": key[0],
        "method": key[1],
        "intensity": key[2],
        "replicate": key[3],
        "variant_index": key[4],
        "source_line": row.get("source_line"),
        "original_text": str(row.get("original_text", "")),
        "old_candidate_text": str(row.get("candidate_text", "")),
        "old_normalized_candidate": str(row.get("normalized_candidate", "")),
    }


def identify_duplicate_repair_slots(rows: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return every extra normalized duplicate, retaining the first key in each group.

    The grouping matches the frozen gate's global duplicate metric.  It is not
    limited to one problem_id, because cross-problem duplicates also reduce the
    gate's global unique count.
    """

    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        normalized = str(row.get("normalized_candidate", ""))
        if normalized:
            grouped[normalized].append(row)

    slots: list[dict[str, Any]] = []
    for normalized, members in sorted(grouped.items()):
        ordered = sorted(members, key=experimental_key)
        if len(ordered) < 2:
            continue
        keeper = ordered[0]
        keeper_key = list(experimental_key(keeper))
        member_keys = [list(experimental_key(member)) for member in ordered]
        for member in ordered[1:]:
            slots.append(
                {
                    **_slot_payload(member),
                    "reason": DUPLICATE_REASON,
                    "duplicate_normalized_candidate": normalized,
                    "duplicate_group_size": len(ordered),
                    "duplicate_group_keys": member_keys,
                    "retained_experimental_key": keeper_key,
                }
            )
    return sorted(slots, key=lambda item: tuple(item["experimental_key"]))


def identify_semantic_repair_slots(rows: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    slots: list[dict[str, Any]] = []
    for row in rows:
        issues = candidate_semantic_boundary_issues(
            str(row.get("original_text", "")),
            str(row.get("candidate_text", "")),
        )
        if issues:
            slots.append(
                {
                    **_slot_payload(row),
                    "reason": SEMANTIC_BOUNDARY_REASON,
                    "semantic_boundary_issues": issues,
                }
            )
    return sorted(slots, key=lambda item: tuple(item["experimental_key"]))


def build_repair_plan(records: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """Build one deterministic repair item per experimental slot.

    A slot can have multiple reasons, but it is repaired only once.  The plan is
    pure: source records are never modified.
    """

    rows = flatten_generation_records(records)
    rows_by_key = {experimental_key(row): row for row in rows}
    reasons_by_key: dict[ExperimentalKey, list[dict[str, Any]]] = defaultdict(list)
    for item in identify_duplicate_repair_slots(rows):
        reasons_by_key[tuple(item["experimental_key"])].append(item)
    for item in identify_semantic_repair_slots(rows):
        reasons_by_key[tuple(item["experimental_key"])].append(item)

    plan: list[dict[str, Any]] = []
    for key in sorted(reasons_by_key):
        row = rows_by_key[key]
        reason_items = reasons_by_key[key]
        reason_names = sorted({str(item["reason"]) for item in reason_items})
        details: dict[str, Any] = {}
        for item in reason_items:
            reason = str(item["reason"])
            details[reason] = {
                name: value
                for name, value in item.items()
                if name
                not in {
                    "experimental_key",
                    "problem_id",
                    "method",
                    "intensity",
                    "replicate",
                    "variant_index",
                    "source_line",
                    "original_text",
                    "old_candidate_text",
                    "old_normalized_candidate",
                    "reason",
                }
            }
        plan.append(
            {
                **_slot_payload(row),
                "replacement_reasons": reason_names,
                "reason_details": details,
            }
        )
    return plan


def candidate_is_acceptable(
    *,
    original_text: str,
    candidate_text: str,
    forbidden_normalized_candidates: Iterable[str] = (),
    original_predicates: Sequence[str] | None = None,
    candidate_predicates: Sequence[str] | None = None,
) -> CandidateAcceptance:
    """Apply deterministic guards before a repaired candidate can be accepted."""

    text = str(candidate_text or "").strip()
    normalized = normalize_candidate_text(text)
    output_issues = candidate_output_issues(text)
    semantic_issues = candidate_semantic_boundary_issues(original_text, text)
    canonical_original_predicates = normalize_predicate_vocabulary(list(original_predicates or []))
    canonical_candidate_predicates = normalize_predicate_vocabulary(list(candidate_predicates or []))
    verifier = verify_candidate(
        original_text=original_text,
        candidate_text=text,
        original_logic_forms=canonical_original_predicates,
        candidate_logic_forms=canonical_candidate_predicates,
        original_answer_text=None,
        candidate_answer_text=None,
    )
    verifier_payload = {
        "predicate_consistent": verifier.predicate_consistent,
        "no_new_points": verifier.no_new_points,
        "numeric_consistent": verifier.numeric_consistent,
        "target_consistent": verifier.target_consistent,
        "term_preserved": verifier.term_preserved,
        "answer_consistent": verifier.answer_consistent,
        "original_terms": verifier.original_terms,
        "candidate_terms": verifier.candidate_terms,
        "original_term_counts": verifier.original_term_counts,
        "candidate_term_counts": verifier.candidate_term_counts,
        "original_numbers": verifier.original_numbers,
        "candidate_numbers": verifier.candidate_numbers,
        "original_targets": verifier.original_targets,
        "candidate_targets": verifier.candidate_targets,
        "notes": verifier.notes,
    }

    predicate_comparison_payload: dict[str, Any] | None = None
    if original_predicates and candidate_predicates:
        comparison = compare_predicates(list(original_predicates), list(candidate_predicates))
        predicate_comparison_payload = {
            "predicate_name_consistent": comparison.predicate_name_consistent,
            "predicate_structure_consistent": comparison.predicate_structure_consistent,
            "missing_predicate_names": comparison.missing_predicate_names,
            "extra_predicate_names": comparison.extra_predicate_names,
            "missing_predicates": comparison.missing_predicates,
            "extra_predicates": comparison.extra_predicates,
        }

    failures: list[str] = []
    if verifier.no_new_points is False:
        failures.append("no_new_points")
    if verifier.numeric_consistent is False:
        failures.append("numeric_consistent")
    if verifier.target_consistent is False:
        failures.append("target_consistent")
    if verifier.term_preserved is False:
        failures.append("term_preserved")
    if original_predicates and candidate_predicates and verifier.predicate_consistent is False:
        failures.append("predicate_consistent")
    if (
        predicate_comparison_payload is not None
        and predicate_comparison_payload["predicate_structure_consistent"] is False
    ):
        failures.append("predicate_structure_consistent")

    rejection_reasons: list[str] = []
    rejection_reasons.extend(f"output_quality:{issue}" for issue in output_issues)
    rejection_reasons.extend(f"semantic_boundary:{issue}" for issue in semantic_issues)
    rejection_reasons.extend(f"verifier:{failure}" for failure in failures)
    if not normalized:
        rejection_reasons.append("empty_normalized_candidate")
    if normalized and normalized == normalize_candidate_text(original_text):
        rejection_reasons.append("unchanged_from_original")
    forbidden = {str(item) for item in forbidden_normalized_candidates if str(item)}
    if normalized and normalized in forbidden:
        rejection_reasons.append("normalized_duplicate_with_accepted_candidate")

    return CandidateAcceptance(
        accepted=not rejection_reasons,
        rejection_reasons=tuple(rejection_reasons),
        normalized_candidate=normalized,
        output_quality_issues=tuple(output_issues),
        semantic_boundary_issues=tuple(semantic_issues),
        verifier_failures=tuple(failures),
        verifier_payload=verifier_payload,
        predicate_comparison=predicate_comparison_payload,
    )
