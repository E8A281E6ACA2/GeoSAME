from __future__ import annotations

import re


_METADATA_LABEL_RE = re.compile(
    r"(?im)^\s*(?:standard\s+answer|correct\s+answer|answer|solution|"
    r"explanation|rationale|change[_ -]?log|risk[_ -]?notes|"
    r"标准答案|正确答案|答案|解答|解析|修改说明|风险说明)\s*[:：]"
)
_JSON_WRAPPER_RE = re.compile(r"^\s*[\[{]")
_CODE_FENCE_RE = re.compile(r"```")

SEMANTIC_BOUNDARY_VERSION_V2_5 = "semantic_boundary_v2_5_legacy_20260717"
SEMANTIC_BOUNDARY_VERSION_V2_6 = "semantic_boundary_v2_6_case_sensitive_labels_20260717"
# Historical callers and frozen v2.5 artifacts keep the legacy behavior unless
# a newer protocol explicitly requests v2.6.
SEMANTIC_BOUNDARY_VERSION = SEMANTIC_BOUNDARY_VERSION_V2_5


def candidate_output_issues(text: str) -> list[str]:
    """Return conservative format/leakage issues in a generated problem statement.

    The detector intentionally does not flag a bare answer value because Geometry3K
    often stores answers as option letters such as A-D, which can occur naturally in
    point names. It instead detects explicit answer/solution metadata markers.
    """

    stripped = str(text or "").strip()
    issues: list[str] = []
    if not stripped:
        return ["empty_candidate_text"]
    if _CODE_FENCE_RE.search(stripped):
        issues.append("markdown_code_fence")
    if _JSON_WRAPPER_RE.search(stripped):
        issues.append("json_or_list_wrapper_in_text")
    if _METADATA_LABEL_RE.search(stripped):
        issues.append("answer_solution_or_metadata_leakage")
    return issues


_SINGLE_POINT_RE = re.compile(r"\b[A-Z]\b")
_COMPACT_POINT_SEQUENCE_RE = re.compile(r"\b[A-Z]{2,4}\b")
_BETWEEN_RE = re.compile(r"\bbetween\b", re.I)
_BETWEEN_EQUIVALENT_SOURCE_RE = re.compile(
    r"\b(?:between|lies?\s+on\s+(?:the\s+)?segment|is\s+on\s+(?:the\s+)?segment)\b",
    re.I,
)
_INTERSECTION_RE = re.compile(r"\b(?:intersect(?:s|ed|ing)?|intersection)\b", re.I)
_INTERSECTION_EQUIVALENT_SOURCE_RE = re.compile(
    r"\b(?:intersect(?:s|ed|ing)?|intersection|meet(?:s|ing)?|cross(?:es|ing)?)\b",
    re.I,
)
_NAMED_POLYGON_RE = re.compile(
    r"\b(triangle|quadrilateral|polygon|parallelogram|rectangle|rhombus|square|trapezoid)\s+"
    r"((?:[A-Z]\s+){2,3}[A-Z]|[A-Z]{3,4})\b",
    re.I,
)
# v2.6 keeps polygon words case-insensitive while requiring point-label groups
# to remain uppercase.  The legacy regex applies ``re.I`` to ``[A-Z]`` too,
# which made the conjunction "and" look like the compact point sequence AND.
_NAMED_POLYGON_RE_V2_6 = re.compile(
    r"\b(?P<object_type>(?i:triangle|quadrilateral|polygon|parallelogram|rectangle|rhombus|square|trapezoid))\s+"
    r"(?P<label>(?:(?-i:[A-Z])\s+){2,3}(?-i:[A-Z])|(?-i:[A-Z]{3,4}))\b"
)
_NAMED_CIRCLE_RE = re.compile(
    r"(?:\b(?:circle)\s+(?:with\s+center\s+|centered\s+at\s+)?([A-Z])\b|(?:⊙|\\odot)\s*([A-Z])\b)",
    re.I,
)
_TANGENT_OBJECT_RE = re.compile(
    r"\b(?:(?P<object_type>(?i:line|segment|ray))\s+)?"
    r"(?P<point_a>[A-Z])\s*(?P<point_b>[A-Z])\s+(?i:is\s+tangent)\b"
)


def extract_explicit_point_labels(text: str) -> set[str]:
    """Extract labels explicitly written in the visible stem.

    Geometry3K alternates between spaced labels (``A B C D``) and compact
    segment/polygon notation (``ABCD`` or ``TV``).  The lightweight verifier's
    single-letter regex misses the compact form, so this boundary detector
    handles both without consulting diagrams or dataset logic forms.
    """

    value = str(text or "")
    labels = set(_SINGLE_POINT_RE.findall(value))
    for token in _COMPACT_POINT_SEQUENCE_RE.findall(value):
        labels.update(token)
    return labels


def _named_polygon_objects(
    text: str,
    *,
    boundary_version: str = SEMANTIC_BOUNDARY_VERSION,
) -> dict[str, set[str]]:
    result: dict[str, set[str]] = {}
    if boundary_version == SEMANTIC_BOUNDARY_VERSION_V2_5:
        pattern = _NAMED_POLYGON_RE
    elif boundary_version == SEMANTIC_BOUNDARY_VERSION_V2_6:
        pattern = _NAMED_POLYGON_RE_V2_6
    else:
        raise ValueError(f"unsupported semantic boundary version: {boundary_version}")
    for match in pattern.finditer(str(text or "")):
        if boundary_version == SEMANTIC_BOUNDARY_VERSION_V2_6:
            object_type = match.group("object_type").lower()
            label_text = match.group("label")
        else:
            object_type = match.group(1).lower()
            label_text = match.group(2)
        label = re.sub(r"\s+", "", label_text).upper()
        result.setdefault(object_type, set()).add(label)
    return result


def _named_circles(text: str) -> set[str]:
    labels: set[str] = set()
    for match in _NAMED_CIRCLE_RE.finditer(str(text or "")):
        label = match.group(1) or match.group(2)
        if label:
            labels.add(label.upper())
    return labels


def _tangent_object_types(text: str) -> dict[str, set[str]]:
    """Return visible type descriptions for objects declared tangent.

    The rule is intentionally limited to the observed ``TV is tangent`` form.
    It does not infer a type for arbitrary two-point expressions elsewhere in
    the stem.
    """

    result: dict[str, set[str]] = {}
    for match in _TANGENT_OBJECT_RE.finditer(str(text or "")):
        label = (match.group("point_a") + match.group("point_b")).upper()
        object_type = (match.group("object_type") or "bare").lower()
        result.setdefault(label, set()).add(object_type)
    return result


def candidate_semantic_boundary_issues(
    original_text: str,
    candidate_text: str,
    *,
    boundary_version: str = SEMANTIC_BOUNDARY_VERSION,
) -> list[str]:
    """Return high-precision signs that a rewrite crossed the source-text boundary.

    This is deliberately narrower than full semantic equivalence.  It targets
    observed leakage modes that can be decided from text alone: new explicit
    point labels, naming an object that was anonymous in the source, and adding
    explicit between/intersection relations absent from the source wording.
    """

    original = str(original_text or "")
    candidate = str(candidate_text or "")
    issues: list[str] = []

    new_labels = sorted(extract_explicit_point_labels(candidate) - extract_explicit_point_labels(original))
    if new_labels:
        issues.append("new_explicit_point_labels:" + ",".join(new_labels))

    original_polygons = _named_polygon_objects(original, boundary_version=boundary_version)
    candidate_polygons = _named_polygon_objects(candidate, boundary_version=boundary_version)
    original_polygon_names = {
        name for names in original_polygons.values() for name in names
    }
    for object_type, candidate_names in sorted(candidate_polygons.items()):
        if re.search(rf"\b(?:the|a|an)\s+{re.escape(object_type)}\b", original, re.I):
            unseen_names = sorted(
                candidate_names
                - original_polygons.get(object_type, set())
                - original_polygon_names
            )
            for name in unseen_names:
                issues.append(f"anonymous_{object_type}_named:{name}")

    original_circles = _named_circles(original)
    candidate_circles = _named_circles(candidate)
    if re.search(r"\b(?:the|a|an)\s+circle\b", original, re.I):
        for name in sorted(candidate_circles - original_circles):
            issues.append(f"anonymous_circle_named:{name}")

    if _BETWEEN_RE.search(candidate) and not _BETWEEN_EQUIVALENT_SOURCE_RE.search(original):
        issues.append("new_between_relation")
    if _INTERSECTION_RE.search(candidate) and not _INTERSECTION_EQUIVALENT_SOURCE_RE.search(original):
        issues.append("new_intersection_relation")

    original_tangent_types = _tangent_object_types(original)
    candidate_tangent_types = _tangent_object_types(candidate)
    for label, source_types in sorted(original_tangent_types.items()):
        # Only reject when the source uses the observed bare form and provides
        # no explicit line/segment/ray type for that tangent object.
        if source_types == {"bare"} and candidate_tangent_types.get(label, {"bare"}) - {"bare"}:
            issues.append(f"bare_tangent_object_was_explicitly_typed:{label}")

    return list(dict.fromkeys(issues))
