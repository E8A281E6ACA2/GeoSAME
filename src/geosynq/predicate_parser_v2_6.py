from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from typing import Any

from .json_utils import extract_json
from .llm import OpenAICompatibleClient, make_messages
from .prompts import render_prompt
from .verifiers_v2_6 import extract_points, predicate_names


FUNCTION_NAME_RE = re.compile(r"\b([A-Za-z_][A-Za-z0-9_]*)\(")
PREDICATE_POINT_RE = re.compile(r"(?<![A-Za-z0-9_])([A-Z])(?![A-Za-z0-9_])")
PREDICATE_NORMALIZER_VERSION_V2_1 = "predicate_normalizer_v2_1_20260716"
PREDICATE_NORMALIZER_VERSION_V2_2 = "predicate_normalizer_v2_2_quadrilateral_implication_20260717"
# Backward-compatible default for every frozen v2.1-v2.5 artifact.
PREDICATE_NORMALIZER_VERSION = PREDICATE_NORMALIZER_VERSION_V2_1


PREDICATE_VOCABULARY_ALIASES = {
    # Confirmed parser-schema synonym. Keep this list deliberately narrow.
    "PointOnCircle": "OnCircle",
}
PREDICATE_NORMALIZATION_DESCRIPTIONS = {
    **PREDICATE_VOCABULARY_ALIASES,
    # Confirmed representation variation for a diagram-numbered angle.  This
    # does not infer vertex labels or use the diagram; it only canonicalizes the
    # two text-parser spellings Angle5 and Angle(5).
    "Angle<number>": "Angle(<number>)",
    "ShadedRegion()": "ShadedRegion",
    "Find(ValueOf(x))": "Find(x)",
    "number*variable": "numbervariable",
}
PREDICATE_NORMALIZATION_DESCRIPTIONS_V2_2 = {
    **PREDICATE_NORMALIZATION_DESCRIPTIONS,
    "Rectangle/Square/Parallelogram/Rhombus/Trapezoid/Kite(A,B,C,D)": (
        "implies Quadrilateral(A,B,C,D)"
    ),
}
_SPECIFIC_QUADRILATERAL_RE = re.compile(
    r"^\s*(Rectangle|Square|Parallelogram|Rhombus|Trapezoid|Kite)\s*\(\s*"
    r"([A-Z])\s*,\s*([A-Z])\s*,\s*([A-Z])\s*,\s*([A-Z])\s*\)\s*$"
)
ZERO_ARITY_OBJECT_SYMBOLS = {
    # Confirmed parser variation: ShadedRegion and ShadedRegion() denote the
    # same anonymous region object in the existing Gate10 parses.
    "ShadedRegion",
}


@dataclass(frozen=True)
class PredicateParseResult:
    predicates: list[str]
    notes: str
    raw_response: str
    success: bool
    error: str | None = None
    request_metadata: dict[str, Any] | None = None


@dataclass(frozen=True)
class PredicateComparison:
    original_predicate_names: list[str]
    candidate_predicate_names: list[str]
    original_all_function_names: list[str]
    candidate_all_function_names: list[str]
    missing_predicate_names: list[str]
    extra_predicate_names: list[str]
    predicate_name_consistent: bool
    missing_predicates: list[str]
    extra_predicates: list[str]
    predicate_structure_consistent: bool
    original_normalized_predicates: list[str]
    candidate_normalized_predicates: list[str]
    normalization_aliases: dict[str, str]


@dataclass(frozen=True)
class PredicateReferenceSanitization:
    usable: bool
    raw_predicates: list[str]
    sanitized_predicates: list[str]
    explicit_point_labels: list[str]
    predicate_point_labels: list[str]
    rejection_reasons: list[str]
    normalization_aliases: dict[str, str]

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def normalize_predicates(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    predicates: list[str] = []
    for item in value:
        text = str(item).strip()
        if text:
            predicates.append(text)
    return predicates


def normalize_predicate_vocabulary(forms: list[str]) -> list[str]:
    normalized: list[str] = []
    for form in forms:
        text = str(form).strip()
        for source, target in PREDICATE_VOCABULARY_ALIASES.items():
            text = re.sub(rf"\b{re.escape(source)}(?=\s*\()", target, text)
        text = re.sub(r"\bAngle\s*([0-9]+)\b", r"Angle(\1)", text)
        # Confirmed text-parser surface alias from the frozen Stress12 run:
        # asking for the value of a scalar target is the same Find predicate.
        text = re.sub(
            r"\bFind\s*\(\s*ValueOf\s*\(\s*([A-Za-z][A-Za-z0-9_]*)\s*\)\s*\)",
            r"Find(\1)",
            text,
        )
        for symbol in ZERO_ARITY_OBJECT_SYMBOLS:
            text = re.sub(rf"\b{re.escape(symbol)}\s*\(\s*\)", symbol, text)
        if text:
            normalized.append(text)
    return normalized


def all_function_names(forms: list[str]) -> set[str]:
    names: set[str] = set()
    for form in forms:
        names.update(FUNCTION_NAME_RE.findall(form))
    return names


def parse_predicates_from_response(raw_response: str) -> PredicateParseResult:
    try:
        data = extract_json(raw_response)
    except Exception as exc:
        return PredicateParseResult(
            predicates=[], notes="", raw_response=raw_response, success=False,
            error=f"unparseable_json: {exc}",
        )
    if not isinstance(data, dict):
        return PredicateParseResult(
            predicates=[], notes="", raw_response=raw_response, success=False,
            error="json_root_not_object",
        )
    predicates = normalize_predicates(data.get("predicates"))
    return PredicateParseResult(
        predicates=predicates,
        notes=str(data.get("notes", "")).strip(),
        raw_response=raw_response,
        success=bool(predicates),
        error=None if predicates else "empty_predicates",
    )


def build_text_only_predicate_prompt(candidate_text: str) -> str:
    """Build a predicate prompt whose sole evidence is the visible problem text.

    Dataset logic forms, diagram-object summaries, and gold annotations are
    intentionally excluded. Otherwise the parser can hallucinate an explicit
    relation from metadata and a later revision step may leak it into the stem.
    """

    return render_prompt("predicate_parse.zh.txt", problem_text=candidate_text)


def parse_candidate_predicates(
    client: OpenAICompatibleClient,
    candidate_text: str,
    system_prompt: str | None = None,
) -> PredicateParseResult:
    prompt = build_text_only_predicate_prompt(candidate_text)
    response = client.chat_with_metadata(
        make_messages(prompt, system_prompt=system_prompt),
        temperature=0.0,
        top_p=0.8,
        max_tokens=800,
    )
    parsed = parse_predicates_from_response(response.content)
    return PredicateParseResult(
        predicates=parsed.predicates,
        notes=parsed.notes,
        raw_response=parsed.raw_response,
        success=parsed.success,
        error=parsed.error,
        request_metadata=response.metadata(),
    )


def _contains_named_circle(text: str, label: str) -> bool:
    return bool(re.search(rf"\bcircle\s+{re.escape(label)}\b", text, re.I))


def _contains_named_quadrilateral(text: str, labels: list[str]) -> bool:
    if not labels:
        return False
    spaced = r"\s*".join(re.escape(label) for label in labels)
    compact = "".join(labels)
    return bool(
        re.search(rf"\bquadrilateral\s+(?:{spaced}|{re.escape(compact)})\b", text, re.I)
    )


def sanitize_text_only_predicate_reference(
    source_text: str,
    predicates: list[str],
) -> PredicateReferenceSanitization:
    """Reject legacy predicate references that contain facts absent from source text.

    This is intentionally conservative. A rejected reference disables predicate
    comparison; it never falls back to dataset logic, diagrams, or gold answers.
    """

    raw = normalize_predicates(predicates)
    sanitized = normalize_predicate_vocabulary(raw)
    explicit_points = sorted(extract_points(source_text))
    predicate_points = sorted(set(PREDICATE_POINT_RE.findall("\n".join(sanitized))))
    reasons: list[str] = []

    hidden_points = sorted(set(predicate_points) - set(explicit_points))
    if hidden_points:
        reasons.append("predicate_introduces_unwritten_point_labels:" + ",".join(hidden_points))

    for form in sanitized:
        for label in re.findall(r"\bCircle\(\s*([A-Z])\s*\)", form):
            if not _contains_named_circle(source_text, label):
                reasons.append(f"anonymous_circle_was_given_label:{label}")
        match = re.match(r"\s*Quadrilateral\(([^)]*)\)", form)
        if match:
            labels = re.findall(r"\b[A-Z]\b", match.group(1))
            if labels and not _contains_named_quadrilateral(source_text, labels):
                reasons.append("anonymous_quadrilateral_was_given_labels:" + "".join(labels))

    lowered = source_text.lower()
    function_names = all_function_names(sanitized)
    if "IntersectAt" in function_names and not re.search(r"\b(intersect|intersection|meet|cross)\w*\b", lowered):
        reasons.append("intersect_relation_not_explicit_in_source_text")
    if "Between" in function_names and not re.search(r"\bbetween\b", lowered):
        reasons.append("between_relation_not_explicit_in_source_text")

    # Some legacy Gate v1 parses expanded the explicitly written term
    # "altitude" into PointOnLine + Perpendicular, while the current text-only
    # parser emits Altitude(...).  That representation is not stable enough for
    # exact predicate comparison.  Disable only this legacy reference shape;
    # never treat the expansion as an alias and never consult hidden logic.
    has_explicit_altitude_term = bool(re.search(r"\baltitudes?\b", lowered))
    has_explicit_perpendicular_relation = bool(
        re.search(r"\bperpendicular\b|(?:^|\s)\u22a5(?:\s|$)", source_text, re.I)
    )
    legacy_altitude_expansion = (
        "Altitude" not in function_names
        and {"PointOnLine", "Perpendicular"}.issubset(function_names)
    )
    if (
        has_explicit_altitude_term
        and legacy_altitude_expansion
        and not has_explicit_perpendicular_relation
    ):
        reasons.append("derived_altitude_expansion_not_stable")

    # De-duplicate while preserving deterministic order.
    reasons = list(dict.fromkeys(reasons))
    return PredicateReferenceSanitization(
        usable=bool(sanitized) and not reasons,
        raw_predicates=raw,
        sanitized_predicates=sanitized if not reasons else [],
        explicit_point_labels=explicit_points,
        predicate_point_labels=predicate_points,
        rejection_reasons=reasons,
        normalization_aliases=dict(PREDICATE_NORMALIZATION_DESCRIPTIONS),
    )


def normalize_logic_form(form: str) -> str:
    normalized = normalize_predicate_vocabulary([form])
    compact = re.sub(r"\s+", "", normalized[0] if normalized else "")
    # Confirmed parser formatting variation: 2x and 2*x denote the same
    # coefficient-variable product. Restrict this to digit + lowercase variable
    # so object labels and numbered geometric symbols are not rewritten.
    return re.sub(r"(?<=\d)\*(?=[a-z])", "", compact)


def _expand_quadrilateral_implications(forms: list[str]) -> list[str]:
    """Add only the universally valid generic type implied by a named quadrilateral.

    The expansion is deliberately narrow: it requires four explicit uppercase
    point arguments and does not infer relationships between specific classes.
    """

    expanded = list(forms)
    for form in forms:
        match = _SPECIFIC_QUADRILATERAL_RE.fullmatch(form)
        if match:
            expanded.append(f"Quadrilateral({','.join(match.groups()[1:])})")
    return list(dict.fromkeys(expanded))


def compare_predicates(
    original_logic_forms: list[str],
    candidate_logic_forms: list[str],
    *,
    normalizer_version: str = PREDICATE_NORMALIZER_VERSION,
) -> PredicateComparison:
    original_canonical = normalize_predicate_vocabulary(original_logic_forms)
    candidate_canonical = normalize_predicate_vocabulary(candidate_logic_forms)
    if normalizer_version == PREDICATE_NORMALIZER_VERSION_V2_2:
        original_canonical = _expand_quadrilateral_implications(original_canonical)
        candidate_canonical = _expand_quadrilateral_implications(candidate_canonical)
        normalization_aliases = PREDICATE_NORMALIZATION_DESCRIPTIONS_V2_2
    elif normalizer_version == PREDICATE_NORMALIZER_VERSION_V2_1:
        normalization_aliases = PREDICATE_NORMALIZATION_DESCRIPTIONS
    else:
        raise ValueError(f"unsupported predicate normalizer version: {normalizer_version}")
    original_names = sorted(predicate_names(original_canonical))
    candidate_names = sorted(predicate_names(candidate_canonical))
    original_set = set(original_names)
    candidate_set = set(candidate_names)
    original_all = all_function_names(original_canonical)
    candidate_all = all_function_names(candidate_canonical)
    missing = sorted(original_set - candidate_all)
    extra = sorted(candidate_set - original_all)
    original_normalized = {normalize_logic_form(form) for form in original_canonical if form.strip()}
    candidate_normalized = {normalize_logic_form(form) for form in candidate_canonical if form.strip()}
    missing_predicates = sorted(original_normalized - candidate_normalized)
    extra_predicates = sorted(candidate_normalized - original_normalized)
    return PredicateComparison(
        original_predicate_names=original_names,
        candidate_predicate_names=candidate_names,
        original_all_function_names=sorted(original_all),
        candidate_all_function_names=sorted(candidate_all),
        missing_predicate_names=missing,
        extra_predicate_names=extra,
        predicate_name_consistent=not missing and not extra,
        missing_predicates=missing_predicates,
        extra_predicates=extra_predicates,
        predicate_structure_consistent=not missing_predicates and not extra_predicates,
        original_normalized_predicates=sorted(original_normalized),
        candidate_normalized_predicates=sorted(candidate_normalized),
        normalization_aliases=dict(normalization_aliases),
    )


def predicate_parse_payload(result: PredicateParseResult, comparison: PredicateComparison | None = None) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "success": result.success,
        "predicates": result.predicates,
        "notes": result.notes,
        "raw_response": result.raw_response,
        "error": result.error,
        "request_metadata": result.request_metadata,
    }
    if comparison is not None:
        payload.update(
            {
                "original_predicate_names": comparison.original_predicate_names,
                "candidate_predicate_names": comparison.candidate_predicate_names,
                "original_all_function_names": comparison.original_all_function_names,
                "candidate_all_function_names": comparison.candidate_all_function_names,
                "missing_predicate_names": comparison.missing_predicate_names,
                "extra_predicate_names": comparison.extra_predicate_names,
                "predicate_name_consistent": comparison.predicate_name_consistent,
                "missing_predicates": comparison.missing_predicates,
                "extra_predicates": comparison.extra_predicates,
                "predicate_structure_consistent": comparison.predicate_structure_consistent,
                "original_normalized_predicates": comparison.original_normalized_predicates,
                "candidate_normalized_predicates": comparison.candidate_normalized_predicates,
                "normalization_aliases": comparison.normalization_aliases,
            }
        )
    return payload
