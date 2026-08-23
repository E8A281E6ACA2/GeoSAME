from __future__ import annotations

from pathlib import Path
from typing import Any

from .paths import project_root


PROMPT_DIR = project_root() / "prompts"


INTENSITY_INSTRUCTIONS = {
    "conservative": (
        "进行保守改写：至少做两处自然的词汇或句法变化，可改变问句表达；"
        "不要求重排全部条件，禁止仅改标点或复制原题。"
    ),
    "structural": (
        "进行结构性改写：必须明显重组句子结构，例如调整条件顺序、合并或拆分分句、"
        "改变语态或重写问句；不能为了差异而扩展不完整定义、增加隐含条件或改变术语。"
    ),
}


def load_prompt(name: str) -> str:
    path = PROMPT_DIR / name
    return path.read_text(encoding="utf-8")


def render_prompt(name: str, **kwargs: Any) -> str:
    template = load_prompt(name)
    safe_kwargs = {key: "" if value is None else value for key, value in kwargs.items()}
    rendered = template
    for key, value in safe_kwargs.items():
        rendered = rendered.replace("{" + key + "}", str(value))
    return rendered


def normalize_method(method: str) -> str:
    aliases = {
        "mwe_guided": "structure_guided",
        "mwe_guided_verify_revise": "structure_guided_verify_revise",
    }
    return aliases.get(method, method)


def prompt_for_method(method: str) -> str:
    normalized = normalize_method(method)
    mapping = {
        "direct": "direct_rewrite.zh.txt",
        "constrained": "constrained_rewrite.zh.txt",
        "structure_guided": "structure_guided_rewrite.zh.txt",
        "structure_guided_verify_revise": "structure_guided_rewrite.zh.txt",
    }
    if normalized not in mapping:
        raise ValueError(f"未知生成方法：{method}")
    return mapping[normalized]


def intensity_instruction(intensity: str) -> str:
    try:
        return INTENSITY_INSTRUCTIONS[intensity]
    except KeyError as exc:
        raise ValueError(f"未知改写强度：{intensity}") from exc
