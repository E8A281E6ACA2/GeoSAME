from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Sequence

from .diversity_audit import normalize_candidate_text


SAFE_ABSTENTION_VERSION_V2_7 = (
    "safe_abstention_v2_7_exhausted_exact_copy_semantic_safe_20260718"
)
SAFE_ABSTENTION_STATUS = "safe_abstention_no_nontrivial_rewrite"
PROTOCOL_REJECTED_STATUS = "protocol_rejected_after_retry_budget"
SAFE_ABSTENTION_REASON = "protocol_retry_budget_exhausted_exact_copy_semantically_safe"

_REQUIRED_TRUE_AUTO_CHECKS = (
    "predicate_consistent",
    "no_new_points",
    "numeric_consistent",
    "target_consistent",
    "term_preserved",
    "semantic_boundary_passed",
)
_UNCHANGED_ISSUE = "protocol:unchanged_from_original"


@dataclass(frozen=True)
class SafeAbstentionDecision:
    eligible: bool
    reason: str
    failed_requirements: tuple[str, ...]
    evidence: dict[str, Any]

    def as_dict(self) -> dict[str, Any]:
        return {
            "version": SAFE_ABSTENTION_VERSION_V2_7,
            "eligible": self.eligible,
            "status_if_applied": SAFE_ABSTENTION_STATUS if self.eligible else None,
            "reason": self.reason,
            "failed_requirements": list(self.failed_requirements),
            "evidence": self.evidence,
        }


def _single_variant(attempt: dict[str, Any]) -> dict[str, Any] | None:
    variants = attempt.get("variants") or []
    if len(variants) != 1 or not isinstance(variants[0], dict):
        return None
    return variants[0]


def classify_safe_abstention_v2_7(
    *,
    original_text: str,
    protocol_attempts: Sequence[dict[str, Any]],
    expected_protocol_attempts: int,
    protocol_accepted: bool,
) -> SafeAbstentionDecision:
    """Classify only an exhausted, semantically safe exact-copy outcome.

    This is intentionally strict. A semantic, quality, count, duplicate-history,
    empty-output, or unavailable-predicate failure remains a hard protocol failure.
    The safe-abstention status is available only after the full preregistered retry
    budget and only when every final attempt returns the original wording after
    normalization while the terminal attempt passes all required safety checks.
    """

    failures: list[str] = []
    normalized_original = normalize_candidate_text(original_text)
    attempts = list(protocol_attempts)
    attempt_variants = [_single_variant(attempt) for attempt in attempts]
    attempt_issues = [list(attempt.get("final_issues") or []) for attempt in attempts]
    attempt_normalized_texts = [
        normalize_candidate_text(str(variant.get("text") or "")) if variant else ""
        for variant in attempt_variants
    ]

    if protocol_accepted:
        failures.append("candidate_already_accepted")
    if expected_protocol_attempts < 1:
        failures.append("invalid_expected_attempt_count")
    if len(attempts) != expected_protocol_attempts:
        failures.append("protocol_retry_budget_not_exhausted")
    if not normalized_original:
        failures.append("empty_normalized_original")
    if any(variant is None for variant in attempt_variants):
        failures.append("attempt_variant_count_not_one")
    if any(not value for value in attempt_normalized_texts):
        failures.append("empty_attempt_candidate")
    if normalized_original and any(
        value != normalized_original for value in attempt_normalized_texts
    ):
        failures.append("at_least_one_attempt_is_not_exact_copy")
    if any(_UNCHANGED_ISSUE not in issues for issues in attempt_issues):
        failures.append("unchanged_issue_not_present_in_every_attempt")

    terminal_variant = attempt_variants[-1] if attempt_variants else None
    terminal_issues = attempt_issues[-1] if attempt_issues else []
    terminal_auto = (
        terminal_variant.get("auto_verification") or {}
        if terminal_variant is not None
        else {}
    )
    terminal_acceptance = (
        terminal_variant.get("protocol_acceptance") or {}
        if terminal_variant is not None
        else {}
    )
    terminal_parse = (
        terminal_variant.get("predicate_parse") or {}
        if terminal_variant is not None
        else {}
    )

    if terminal_issues != [_UNCHANGED_ISSUE]:
        failures.append("terminal_issue_is_not_unchanged_only")
    if terminal_acceptance.get("accepted") is not False:
        failures.append("terminal_acceptance_not_false")
    if list(terminal_acceptance.get("issues") or []) != [_UNCHANGED_ISSUE]:
        failures.append("terminal_acceptance_issues_not_unchanged_only")
    failed_auto_checks = [
        name for name in _REQUIRED_TRUE_AUTO_CHECKS if terminal_auto.get(name) is not True
    ]
    if failed_auto_checks:
        failures.append("terminal_required_auto_checks_not_true")
    if terminal_auto.get("answer_consistent") is False:
        failures.append("terminal_answer_inconsistent")
    if list(terminal_variant.get("output_quality_issues") or []) if terminal_variant else []:
        failures.append("terminal_output_quality_issue")
    if list(terminal_variant.get("semantic_boundary_issues") or []) if terminal_variant else []:
        failures.append("terminal_semantic_boundary_issue")
    if terminal_parse.get("success") is not True:
        failures.append("terminal_predicate_parse_unavailable")
    if list(terminal_parse.get("missing_predicates") or []):
        failures.append("terminal_missing_predicates")
    if list(terminal_parse.get("extra_predicates") or []):
        failures.append("terminal_extra_predicates")

    evidence = {
        "expected_protocol_attempts": expected_protocol_attempts,
        "observed_protocol_attempts": len(attempts),
        "all_attempts_have_one_variant": all(
            variant is not None for variant in attempt_variants
        ),
        "all_attempts_exact_copy_after_normalization": bool(normalized_original)
        and bool(attempts)
        and all(value == normalized_original for value in attempt_normalized_texts),
        "unchanged_issue_present_in_every_attempt": bool(attempt_issues)
        and all(_UNCHANGED_ISSUE in issues for issues in attempt_issues),
        "attempt_final_issues": attempt_issues,
        "terminal_final_issues": terminal_issues,
        "terminal_required_auto_checks": {
            name: terminal_auto.get(name) for name in _REQUIRED_TRUE_AUTO_CHECKS
        },
        "terminal_answer_consistent": terminal_auto.get("answer_consistent"),
        "terminal_predicate_parse_success": terminal_parse.get("success"),
        "terminal_missing_predicates": list(terminal_parse.get("missing_predicates") or []),
        "terminal_extra_predicates": list(terminal_parse.get("extra_predicates") or []),
    }
    return SafeAbstentionDecision(
        eligible=not failures,
        reason=SAFE_ABSTENTION_REASON if not failures else "requirements_not_met",
        failed_requirements=tuple(dict.fromkeys(failures)),
        evidence=evidence,
    )
