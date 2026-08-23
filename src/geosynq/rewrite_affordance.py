from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from typing import Any


_WORD_RE = re.compile(r"[A-Za-z0-9]+|\\[A-Za-z]+|[\u4e00-\u9fff]")
_CLAUSE_RE = re.compile(r"[,;:]|\b(?:and|if|where|given|while|when|such\s+that)\b", re.I)


@dataclass(frozen=True)
class RewriteAffordance:
    band: str
    character_count: int
    token_count: int
    clause_count: int
    visible_condition_count: int
    structural_eligible: bool
    rationale: str

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def visible_rewrite_affordance(problem_text: str) -> RewriteAffordance:
    """Classify how much safe paraphrase structure is visible in the stem.

    The classifier deliberately uses only the visible problem text. It does not
    consult the diagram, answer, dataset logic forms, generation outputs, or
    human labels. The bands are design strata, not quality labels.
    """

    text = str(problem_text or "").strip()
    character_count = len(text)
    token_count = len(_WORD_RE.findall(text))
    clause_markers = len(_CLAUSE_RE.findall(text))
    clause_count = 1 + clause_markers if text else 0
    visible_condition_count = len(
        re.findall(
            r"(?:^|[,;.]\s*)(?:if\b|given\b|where\b)|(?:=|\\perp|\\parallel|\\sim|\\cong)",
            text,
            re.I,
        )
    )

    if character_count <= 35 and token_count <= 10 and clause_markers == 0:
        band = "low"
        structural_eligible = False
        rationale = "single short target statement with no visible clause-reordering opportunity"
    elif character_count <= 80 or clause_count <= 2:
        band = "medium"
        structural_eligible = clause_count >= 2 or visible_condition_count >= 1
        rationale = "limited but nonzero visible paraphrase structure"
    else:
        band = "high"
        structural_eligible = True
        rationale = "multiple visible conditions or clauses support safe structural reorganization"

    return RewriteAffordance(
        band=band,
        character_count=character_count,
        token_count=token_count,
        clause_count=clause_count,
        visible_condition_count=visible_condition_count,
        structural_eligible=structural_eligible,
        rationale=rationale,
    )
