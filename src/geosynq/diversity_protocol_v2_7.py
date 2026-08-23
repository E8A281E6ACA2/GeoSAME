from __future__ import annotations

import hashlib
import random
from dataclasses import dataclass
from typing import Any, Iterable, Sequence

from .diversity_audit import normalize_candidate_text
from .rewrite_affordance import visible_rewrite_affordance


PROTOCOL_V1 = "independent_v1"
PROTOCOL_V2 = "balanced_history_v2"
PROTOCOL_V2_1 = "balanced_history_v2_1"
PROTOCOL_V2_2 = "balanced_history_v2_2"
PROTOCOL_V2_3 = "balanced_history_v2_3"
PROTOCOL_V2_4 = "balanced_history_v2_4"
PROTOCOL_V2_5 = "balanced_history_v2_5"
PROTOCOL_V2_6 = "balanced_history_v2_6"
PROTOCOL_V2_7 = "balanced_history_v2_7"
PROTOCOL_AMENDMENT_VERSION_V2_1 = "protocol_v2_1_amendment_20260716"
PROTOCOL_AMENDMENT_VERSION_V2_2 = "protocol_v2_2_amendment_20260717"
PROTOCOL_AMENDMENT_VERSION_V2_3 = "protocol_v2_3_precision_gerund_amendment_20260717"
PROTOCOL_AMENDMENT_VERSION_V2_4 = "protocol_v2_4_circle_context_suffix_amendment_20260717"
PROTOCOL_AMENDMENT_VERSION_V2_5 = "protocol_v2_5_figure_context_suffix_amendment_20260717"
PROTOCOL_AMENDMENT_VERSION_V2_6 = (
    "protocol_v2_6_polygon_label_and_quadrilateral_implication_amendment_20260717"
)
PROTOCOL_AMENDMENT_VERSION_V2_7 = (
    "protocol_v2_7_safe_abstention_and_yield_amendment_20260718"
)
# Backward-compatible alias retained for frozen v2.1 readers.
PROTOCOL_AMENDMENT_VERSION = PROTOCOL_AMENDMENT_VERSION_V2_1
BALANCED_HISTORY_PROTOCOLS = frozenset({
    PROTOCOL_V2,
    PROTOCOL_V2_1,
    PROTOCOL_V2_2,
    PROTOCOL_V2_3,
    PROTOCOL_V2_4,
    PROTOCOL_V2_5,
    PROTOCOL_V2_6,
    PROTOCOL_V2_7,
})

DIVERSITY_MOVES = (
    "direct_question",
    "imperative_determine",
    "target_fronting",
    "condition_first",
    "clause_reorder",
    "split_or_merge_clauses",
    "object_centered_wording",
    "concise_natural_alternative",
)


@dataclass(frozen=True)
class GenerationSlot:
    method: str
    intensity: str
    replicate: int
    position_within_problem: int
    diversity_move: str

    @property
    def key_without_problem(self) -> tuple[str, str, int]:
        return (self.method, self.intensity, self.replicate)


def _stable_int(seed: int, value: str) -> int:
    digest = hashlib.sha256(f"{seed}|{value}".encode("utf-8")).hexdigest()
    return int(digest[:16], 16)


def base_slots(
    methods: Sequence[str],
    intensities: Sequence[str],
    replicates: int,
    seed: int,
) -> list[tuple[str, str, int]]:
    slots = [
        (method, intensity, replicate)
        for method in methods
        for intensity in intensities
        for replicate in range(1, replicates + 1)
    ]
    random.Random(seed).shuffle(slots)
    return slots


def balanced_slots_for_problem(
    problem_id: str,
    problem_index: int,
    methods: Sequence[str],
    intensities: Sequence[str],
    replicates: int,
    seed: int,
) -> list[GenerationSlot]:
    """Return a deterministic cyclic schedule that balances history position.

    Across every complete block of ``len(slots)`` problems, each method/intensity
    slot occupies each history position exactly once. The base permutation and
    move offset are frozen by ``seed``; they do not depend on generated text.
    """

    slots = base_slots(methods, intensities, replicates, seed)
    if not slots:
        return []
    rotation = problem_index % len(slots)
    ordered = slots[rotation:] + slots[:rotation]
    move_offset = _stable_int(seed, problem_id) % len(DIVERSITY_MOVES)
    return [
        GenerationSlot(
            method=method,
            intensity=intensity,
            replicate=replicate,
            position_within_problem=position,
            diversity_move=DIVERSITY_MOVES[(move_offset + position - 1) % len(DIVERSITY_MOVES)],
        )
        for position, (method, intensity, replicate) in enumerate(ordered, start=1)
    ]


def format_candidate_history(candidates: Iterable[str]) -> str:
    values = [str(value).strip() for value in candidates if str(value).strip()]
    if not values:
        return "（当前尚无已接受候选；仍须避免照抄原题。）"
    return "\n".join(f"- {value}" for value in values)


def protocol_v2_prompt_block(
    *,
    problem_text: str,
    accepted_candidates: Sequence[str],
    position_within_problem: int,
    total_slots: int,
    diversity_move: str,
    protocol_name: str = PROTOCOL_V2,
) -> str:
    affordance = visible_rewrite_affordance(problem_text)
    if protocol_name == PROTOCOL_V2:
        protocol_heading = "预注册多样性协议 balanced_history_v2"
    elif protocol_name == PROTOCOL_V2_1:
        protocol_heading = f"Protocol v2.1 implementation amendment {protocol_name}"
    elif protocol_name == PROTOCOL_V2_2:
        protocol_heading = f"Protocol v2.2 target-boundary amendment {protocol_name}"
    elif protocol_name == PROTOCOL_V2_3:
        protocol_heading = f"Protocol v2.3 precision-gerund verifier amendment {protocol_name}"
    elif protocol_name == PROTOCOL_V2_4:
        protocol_heading = f"Protocol v2.4 circle-context target verifier amendment {protocol_name}"
    elif protocol_name == PROTOCOL_V2_5:
        protocol_heading = f"Protocol v2.5 figure-context target verifier amendment {protocol_name}"
    elif protocol_name == PROTOCOL_V2_6:
        protocol_heading = f"Protocol v2.6 semantic-boundary and predicate implication amendment {protocol_name}"
    elif protocol_name == PROTOCOL_V2_7:
        protocol_heading = f"Protocol v2.7 safe-abstention and candidate-yield amendment {protocol_name}"
    else:
        raise ValueError(f"unsupported balanced-history protocol: {protocol_name}")
    return (
        f"\n\n【{protocol_heading}】\n"
        f"本候选在同题 {total_slots} 个槽位中的平衡位置：{position_within_problem}/{total_slots}。\n"
        f"原题可改写空间分层：{affordance.band}；结构改写适用："
        f"{'是' if affordance.structural_eligible else '否'}。\n"
        f"优先尝试的表达动作：{diversity_move}。若该动作不适用于本题，改用另一种自然句法；"
        "不得为了差异增加条件、补足图中信息、改换术语或写得不自然。\n"
        "以下是同一原题下已经接受的候选。新 text 不得与其中任何一条在忽略大小写、空白和标点后相同，"
        "也不得仅做符号空格或标点变化：\n"
        f"{format_candidate_history(accepted_candidates)}\n"
        "语义安全优先于多样性。如果原题极短、无法安全执行结构重排，只做自然的问句框架或动词变化，"
        "不要虚构原题未明示的长度、角度、相交、平行、垂直或图形类别。"
    )


def protocol_candidate_issues(
    original_text: str,
    candidate_text: str,
    accepted_candidates: Sequence[str],
) -> list[str]:
    normalized = normalize_candidate_text(candidate_text)
    issues: list[str] = []
    if not normalized:
        issues.append("protocol:empty_normalized_candidate")
    if normalized and normalized == normalize_candidate_text(original_text):
        issues.append("protocol:unchanged_from_original")
    accepted = {
        normalize_candidate_text(value)
        for value in accepted_candidates
        if normalize_candidate_text(value)
    }
    if normalized and normalized in accepted:
        issues.append("protocol:normalized_duplicate_with_problem_history")
    return issues


def protocol_metadata(
    *,
    problem_text: str,
    slot: GenerationSlot,
    total_slots: int,
    accepted_candidates: Sequence[str],
    seed: int,
    protocol_name: str = PROTOCOL_V2,
) -> dict[str, Any]:
    return {
        "name": protocol_name,
        "schedule_seed": seed,
        "position_within_problem": slot.position_within_problem,
        "total_slots_within_problem": total_slots,
        "diversity_move": slot.diversity_move,
        "history_candidate_count": len(accepted_candidates),
        "history_conditioning_scope": "same_problem_accepted_text_only_without_method_labels",
        "rewrite_affordance": visible_rewrite_affordance(problem_text).as_dict(),
    }
