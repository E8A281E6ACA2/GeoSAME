from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass


@dataclass(frozen=True)
class GeometryTerm:
    canonical: str
    aliases: tuple[str, ...]
    predicate_hint: str


GEOMETRY_TERMS: tuple[GeometryTerm, ...] = (
    GeometryTerm("triangle", ("triangle", "triangular", "△", "\\triangle", "三角形"), "Triangle"),
    GeometryTerm("congruent triangles", ("congruent", "congruence", "全等"), "Congruent"),
    GeometryTerm("similar triangles", ("similar", "similarity", "相似"), "Similar"),
    GeometryTerm("parallel lines", ("parallel", "∥", "//", "平行"), "Parallel"),
    GeometryTerm("perpendicular lines", ("perpendicular", "⊥", "垂直"), "Perpendicular"),
    GeometryTerm("angle bisector", ("angle bisector", "bisects angle", "角平分线"), "AngleBisector"),
    GeometryTerm("perpendicular bisector", ("perpendicular bisector", "垂直平分线", "中垂线"), "PerpendicularBisector"),
    GeometryTerm("median", ("median", "中线"), "Median"),
    GeometryTerm("altitude", ("altitude", "height", "高线"), "Altitude"),
    GeometryTerm("tangent", ("tangent", "切线"), "Tangent"),
    GeometryTerm("circle", ("circle", "圆"), "Circle"),
    GeometryTerm("isosceles triangle", ("isosceles", "等腰三角形"), "Isosceles"),
    GeometryTerm("right triangle", ("right triangle", "直角三角形"), "RightTriangle"),
)


def normalize_text(text: str) -> str:
    replacements = {
        "Ёу": "°",
        "∥": " parallel ",
        "//": " parallel ",
        "⊥": " perpendicular ",
        "\\triangle": " triangle ",
    }
    normalized = text
    for src, dst in replacements.items():
        normalized = normalized.replace(src, dst)
    normalized = re.sub(r"\s+", " ", normalized).strip()
    return normalized


def find_geometry_terms(text: str) -> list[str]:
    lowered = normalize_text(text).lower()
    found: list[str] = []
    for term in GEOMETRY_TERMS:
        if any(alias.lower() in lowered for alias in term.aliases):
            found.append(term.canonical)
    return found


def count_geometry_terms(text: str) -> Counter[str]:
    lowered = normalize_text(text).lower()
    counts: Counter[str] = Counter()
    for term in GEOMETRY_TERMS:
        term_count = 0
        alias_texts = sorted(
            {
                normalize_text(alias).lower()
                for alias in term.aliases
                if normalize_text(alias).strip()
            },
            key=len,
            reverse=True,
        )
        for alias_text in alias_texts:
            pattern = re.escape(alias_text)
            if re.match(r"^[a-z0-9 ]+$", alias_text):
                pattern = r"\b" + pattern + r"\b"
            term_count += len(re.findall(pattern, lowered))
        if term_count:
            counts[term.canonical] = term_count
    return counts
