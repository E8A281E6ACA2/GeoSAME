from __future__ import annotations

from dataclasses import dataclass

from .verifiers import VerificationResult, verify_candidate


@dataclass(frozen=True)
class GeoProblem:
    problem_id: str
    text: str
    image_path: str | None
    answer: str | None
    logic_forms: list[str]
    source: str


@dataclass(frozen=True)
class CandidateVariant:
    problem_id: str
    text: str
    method: str
    verification: VerificationResult


def template_rewrite(problem: GeoProblem) -> str:
    """Deterministic baseline that only normalizes common surface markers."""
    text = problem.text
    text = text.replace("Find", "Determine")
    text = text.replace("what is", "determine")
    text = text.replace("Ёу", "°")
    return text


def generate_template_candidate(problem: GeoProblem) -> CandidateVariant:
    candidate_text = template_rewrite(problem)
    verification = verify_candidate(
        original_text=problem.text,
        candidate_text=candidate_text,
        original_logic_forms=problem.logic_forms,
        candidate_logic_forms=problem.logic_forms,
        original_answer_text=problem.answer,
        candidate_answer_text=problem.answer,
    )
    return CandidateVariant(
        problem_id=problem.problem_id,
        text=candidate_text,
        method="template_rewrite",
        verification=verification,
    )
