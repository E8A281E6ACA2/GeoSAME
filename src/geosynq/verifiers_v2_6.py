from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass

from .terms import count_geometry_terms, find_geometry_terms, normalize_text


VERIFIER_VERSION_V2_1 = "verifier_target_v2_1_20260716"
VERIFIER_VERSION_V2_2 = "verifier_target_v2_2_20260717"
VERIFIER_VERSION_V2_3 = "verifier_target_v2_3_20260717"
VERIFIER_VERSION_V2_4 = "verifier_target_v2_4_20260717"
VERIFIER_VERSION_V2_5 = "verifier_target_v2_5_20260717"
VERIFIER_VERSION_V2_6 = "verifier_target_v2_6_20260717"
# Backward-compatible default: historical callers keep the frozen v2.1 extractor.
VERIFIER_VERSION = VERIFIER_VERSION_V2_1

PREDICATE_RE = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)\(")
POINT_RE = re.compile(r"\b[A-Z]\b")
ANSWER_RE = re.compile(r"(?:Answer\s*:\s*|故选[:：]?\s*|答案[:：]?\s*)([A-D]|[-+]?\d+(?:\.\d+)?)", re.I)
NUMBER_RE = re.compile(r"(?<![A-Za-z])[-+]?\d+(?:\.\d+)?")
TARGET_CONDITION_BOUNDARY_V2_1 = (
    r"when|if|given|assume|assumed|assuming|provided|where|so that|use|using"
    r"|and\s+assume(?:d|ing)?"
    r"|by\s+using"
    r"|with\s+(?:the\s+)?help\s+of"
    r"|in\s+(?:the\s+)?(?:given|provided)"
    r"|for\s+(?:the\s+)?(?:given|provided)"
    r"|in\s+the\s+(?:figure|diagram)"
    r"|from\s+(?:the\s+)?(?:information|givens?|data)"
)

# v2.2 adds only a controlled set of diagram/figure context nouns after
# "from".  A generic ``from the`` boundary would corrupt genuine targets
# such as "distance from the point to the line" and "segment from A to B".
TARGET_CONTEXT_NOUN_V2_2 = (
    r"figure|diagram|illustration|graph|parallelogram|rectangle|square|triangle"
    r"|trapezoid|polygon|circle|rhombus|kite"
)
TARGET_CONDITION_BOUNDARY_V2_2 = (
    TARGET_CONDITION_BOUNDARY_V2_1
    + rf"|from\s+(?:the\s+)?(?:(?:given|provided)\s+)?(?:{TARGET_CONTEXT_NOUN_V2_2})"
)

# v2.4 adds one evidence-backed suffix boundary only: a requested object may
# be followed by a circle locator and then an explicit ``where`` clause.
# This intentionally does not treat generic ``in ...`` phrases as context.
TARGET_CIRCLE_CONTEXT_SUFFIX_V2_4 = (
    r"in\s+(?:the\s+)?(?:\\odot|circle)\s+[A-Za-z0-9]+\s*,\s*where"
)
TARGET_CONDITION_BOUNDARY_V2_4 = (
    TARGET_CONDITION_BOUNDARY_V2_2 + rf"|{TARGET_CIRCLE_CONTEXT_SUFFIX_V2_4}"
)

# v2.5 adds one further evidence-backed suffix boundary: a requested object may
# be followed by a controlled geometry figure locator and an explicit ``where``
# clause.  The figure identifier is deliberately case-sensitive even though the
# surrounding target regex is case-insensitive; this prevents ordinary phrases
# such as ``in square units, where`` from being truncated as figure context.
TARGET_FIGURE_CONTEXT_NOUN_V2_5 = (
    r"right\s+triangle|isosceles\s+triangle|equilateral\s+triangle"
    r"|scalene\s+triangle|triangle|rectangle|square|parallelogram"
    r"|trapezoid|polygon|quadrilateral|rhombus|kite"
)
TARGET_FIGURE_IDENTIFIER_V2_5 = r"(?-i:[A-Z](?:\s*[A-Z]){1,7})"
TARGET_FIGURE_CONTEXT_SUFFIX_V2_5 = (
    rf"in\s+(?:the\s+)?(?:(?:given|provided)\s+)?"
    rf"(?:{TARGET_FIGURE_CONTEXT_NOUN_V2_5})\s+"
    rf"{TARGET_FIGURE_IDENTIFIER_V2_5}\s*,\s*where"
)
TARGET_CONDITION_BOUNDARY_V2_5 = (
    TARGET_CONDITION_BOUNDARY_V2_4 + rf"|{TARGET_FIGURE_CONTEXT_SUFFIX_V2_5}"
)


def _target_patterns(condition_boundary: str) -> tuple[re.Pattern[str], re.Pattern[str]]:
    target_re = re.compile(
        rf"\b(?:find|determine|calculate|compute)\s+(.*?)(?=[,;:]?\s+(?:{condition_boundary})\b|[.?!]|$)",
        re.I,
    )
    what_target_re = re.compile(
        rf"\bwhat\s+is\s+(.*?)(?=[,;:]?\s+(?:{condition_boundary})\b|[.?!]|$)",
        re.I,
    )
    return target_re, what_target_re


TARGET_RE_V2_1, WHAT_TARGET_RE_V2_1 = _target_patterns(TARGET_CONDITION_BOUNDARY_V2_1)
TARGET_RE_V2_2, WHAT_TARGET_RE_V2_2 = _target_patterns(TARGET_CONDITION_BOUNDARY_V2_2)
TARGET_RE_V2_4, WHAT_TARGET_RE_V2_4 = _target_patterns(TARGET_CONDITION_BOUNDARY_V2_4)
TARGET_RE_V2_5, WHAT_TARGET_RE_V2_5 = _target_patterns(TARGET_CONDITION_BOUNDARY_V2_5)
# Compatibility aliases for code that imported the original regex constants.
TARGET_CONDITION_BOUNDARY = TARGET_CONDITION_BOUNDARY_V2_1
TARGET_RE = TARGET_RE_V2_1
WHAT_TARGET_RE = WHAT_TARGET_RE_V2_1
PRECISION_RE_V2_1_V2_2 = re.compile(
    r"\b(?:round(?:ed)?(?:\s+(?:it|the\s+(?:answer|result)))?\s+)?to\s+(?:the\s+)?nearest\s+"
    r"(tenth|hundredth|thousandth|whole\s+number|integer|degree)\b",
    re.I,
)
PRECISION_RE_V2_3 = re.compile(
    r"\b(?:round(?:ed|ing)?(?:\s+(?:it|the\s+(?:answer|result)))?\s+)?to\s+(?:the\s+)?nearest\s+"
    r"(tenth|hundredth|thousandth|whole\s+number|integer|degree)\b",
    re.I,
)
# Compatibility alias for code that imported the original precision regex.
PRECISION_RE = PRECISION_RE_V2_1_V2_2


def predicate_names(logic_forms: list[str]) -> set[str]:
    names: set[str] = set()
    for form in logic_forms:
        match = PREDICATE_RE.match(form.strip())
        if match:
            names.add(match.group(1))
    return names


def extract_points(text: str) -> set[str]:
    return set(POINT_RE.findall(text))


def extract_answer(text: str) -> str | None:
    match = ANSWER_RE.search(text)
    if match:
        return match.group(1).upper()
    return None


def extract_numbers(text: str) -> list[str]:
    return NUMBER_RE.findall(normalize_text(text))


def number_multiset(text: str) -> Counter[str]:
    return Counter(extract_numbers(text))


def precision_pattern(verifier_version: str) -> re.Pattern[str]:
    if verifier_version in {VERIFIER_VERSION_V2_1, VERIFIER_VERSION_V2_2}:
        return PRECISION_RE_V2_1_V2_2
    if verifier_version in {
        VERIFIER_VERSION_V2_3,
        VERIFIER_VERSION_V2_4,
        VERIFIER_VERSION_V2_5,
        VERIFIER_VERSION_V2_6,
    }:
        return PRECISION_RE_V2_3
    raise ValueError(f"unsupported verifier version: {verifier_version}")


def normalize_precision_instruction(
    text: str,
    *,
    verifier_version: str = VERIFIER_VERSION_V2_1,
) -> str:
    match = precision_pattern(verifier_version).search(normalize_text(text))
    if not match:
        return ""
    unit = re.sub(r"\s+", "", match.group(1).lower())
    return "tonearest" + unit


def normalize_target(
    target: str,
    *,
    verifier_version: str = VERIFIER_VERSION_V2_1,
) -> str:
    normalized = normalize_text(target).lower()
    normalized = normalized.replace("\\angle", " angle ")
    normalized = normalized.replace("∠", " angle ")
    normalized = normalized.replace("\\odot", " circle ")
    # Precision/rounding instructions may occur before or after the interrogative.
    # Remove them from the object phrase and append one canonical modifier later.
    normalized = precision_pattern(verifier_version).sub(" ", normalized)
    # Convert common descriptive questions to their explicit object before
    # removing generic measure/length words.  Pronoun-only targets such as
    # "its measure" are intentionally treated as unavailable rather than as
    # a contradictory target.
    normalized = re.sub(r"\bhow\s+(?:large|long|big)\s+(.+?)\s+is\b", r"\1", normalized)
    normalized = re.sub(r"\b(?:its|their)\b", " ", normalized)
    normalized = re.sub(r"(?:[,;:]\s*)?\bthen\b\s*$", " ", normalized)
    normalized = re.sub(r"\bat\s+(?:vertex|point)\s+[a-z]\b", "", normalized)
    normalized = re.sub(r"\b(?:the|value|measure|length|area|of|m)\b", " ", normalized)
    normalized = re.sub(r"[^a-z0-9]+", "", normalized)
    return normalized


def extract_targets(text: str, *, verifier_version: str = VERIFIER_VERSION_V2_1) -> list[str]:
    """Extract normalized targets using an explicitly versioned boundary set.

    The default remains v2.1 so historical artifacts and callers are not
    silently reinterpreted. New Protocol v2.2 records pass the v2.2 version.
    """

    normalized = normalize_text(text)
    if verifier_version == VERIFIER_VERSION_V2_1:
        target_re, what_target_re = TARGET_RE_V2_1, WHAT_TARGET_RE_V2_1
    elif verifier_version in {VERIFIER_VERSION_V2_2, VERIFIER_VERSION_V2_3}:
        target_re, what_target_re = TARGET_RE_V2_2, WHAT_TARGET_RE_V2_2
    elif verifier_version == VERIFIER_VERSION_V2_4:
        target_re, what_target_re = TARGET_RE_V2_4, WHAT_TARGET_RE_V2_4
    elif verifier_version in {VERIFIER_VERSION_V2_5, VERIFIER_VERSION_V2_6}:
        target_re, what_target_re = TARGET_RE_V2_5, WHAT_TARGET_RE_V2_5
    else:
        raise ValueError(f"unsupported verifier version: {verifier_version}")
    targets = [match.group(1).strip() for match in target_re.finditer(normalized)]
    targets.extend(match.group(1).strip() for match in what_target_re.finditer(normalized))
    precision = normalize_precision_instruction(normalized, verifier_version=verifier_version)
    normalized_targets = []
    for target in targets:
        value = normalize_target(target, verifier_version=verifier_version)
        if value:
            normalized_targets.append(value + precision)
    return normalized_targets


def extract_targets_v2_2(text: str) -> list[str]:
    return extract_targets(text, verifier_version=VERIFIER_VERSION_V2_2)


def extract_targets_v2_3(text: str) -> list[str]:
    return extract_targets(text, verifier_version=VERIFIER_VERSION_V2_3)


def extract_targets_v2_4(text: str) -> list[str]:
    return extract_targets(text, verifier_version=VERIFIER_VERSION_V2_4)


def extract_targets_v2_5(text: str) -> list[str]:
    return extract_targets(text, verifier_version=VERIFIER_VERSION_V2_5)


def extract_targets_v2_6(text: str) -> list[str]:
    return extract_targets(text, verifier_version=VERIFIER_VERSION_V2_6)


@dataclass(frozen=True)
class VerificationResult:
    predicate_consistent: bool
    no_new_points: bool
    numeric_consistent: bool
    target_consistent: bool | None
    term_preserved: bool
    answer_consistent: bool | None
    original_terms: list[str]
    candidate_terms: list[str]
    original_term_counts: dict[str, int]
    candidate_term_counts: dict[str, int]
    original_numbers: list[str]
    candidate_numbers: list[str]
    original_targets: list[str]
    candidate_targets: list[str]
    notes: list[str]


def verify_candidate(
    original_text: str,
    candidate_text: str,
    original_logic_forms: list[str] | None = None,
    candidate_logic_forms: list[str] | None = None,
    original_answer_text: str | None = None,
    candidate_answer_text: str | None = None,
    verifier_version: str = VERIFIER_VERSION_V2_1,
) -> VerificationResult:
    """Lightweight rule verifier used before heavier parser/model checks."""
    original_logic_forms = original_logic_forms or []
    candidate_logic_forms = candidate_logic_forms or []
    notes: list[str] = []

    if original_logic_forms and candidate_logic_forms:
        predicate_consistent = predicate_names(original_logic_forms) == predicate_names(candidate_logic_forms)
    else:
        predicate_consistent = True
        notes.append("predicate check skipped because one side has no logic forms")

    original_points = extract_points(normalize_text(original_text))
    candidate_points = extract_points(normalize_text(candidate_text))
    new_points = candidate_points - original_points
    no_new_points = not new_points
    if new_points:
        notes.append(f"candidate introduces new point labels: {sorted(new_points)}")

    original_numbers = extract_numbers(original_text)
    candidate_numbers = extract_numbers(candidate_text)
    numeric_consistent = number_multiset(original_text) == number_multiset(candidate_text)
    if not numeric_consistent:
        notes.append(
            "numeric values changed: "
            f"original={original_numbers}, candidate={candidate_numbers}"
        )

    original_targets = extract_targets(original_text, verifier_version=verifier_version)
    candidate_targets = extract_targets(candidate_text, verifier_version=verifier_version)
    if original_targets and candidate_targets:
        target_consistent = Counter(original_targets) == Counter(candidate_targets)
        if not target_consistent:
            notes.append(
                "target changed: "
                f"original={original_targets}, candidate={candidate_targets}"
            )
    else:
        target_consistent = None
        notes.append("target check skipped because one side has no extractable target")

    original_term_counts = count_geometry_terms(original_text)
    candidate_term_counts = count_geometry_terms(candidate_text)
    original_terms = find_geometry_terms(original_text)
    candidate_terms = find_geometry_terms(candidate_text)
    reduced_terms = {
        term: {
            "original": original_count,
            "candidate": candidate_term_counts.get(term, 0),
        }
        for term, original_count in sorted(original_term_counts.items())
        if candidate_term_counts.get(term, 0) < original_count
    }
    term_preserved = not reduced_terms
    if reduced_terms:
        notes.append(f"candidate may reduce geometry term counts: {reduced_terms}")

    answer_consistent: bool | None
    if original_answer_text and candidate_answer_text:
        answer_consistent = extract_answer(original_answer_text) == extract_answer(candidate_answer_text)
    else:
        answer_consistent = None
        notes.append("answer check skipped because answer text is missing")

    return VerificationResult(
        predicate_consistent=predicate_consistent,
        no_new_points=no_new_points,
        numeric_consistent=numeric_consistent,
        target_consistent=target_consistent,
        term_preserved=term_preserved,
        answer_consistent=answer_consistent,
        original_terms=original_terms,
        candidate_terms=candidate_terms,
        original_term_counts=dict(original_term_counts),
        candidate_term_counts=dict(candidate_term_counts),
        original_numbers=original_numbers,
        candidate_numbers=candidate_numbers,
        original_targets=original_targets,
        candidate_targets=candidate_targets,
        notes=notes,
    )
