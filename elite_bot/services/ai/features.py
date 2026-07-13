"""Curriculum-grounded study features built on any :class:`AIProvider`.

Every method is grounded in the actual page text pulled from the search index,
and the prompts instruct the model to stay inside that curriculum and answer in
its language. Nothing here knows which provider is in use.
"""

from __future__ import annotations

import logging
import random
from dataclasses import dataclass

from services.ai.base import AIError, AIProvider
from services.ai.cache import AICache
from utils.arabic import normalize

logger = logging.getLogger(__name__)

#: Character budget for the curriculum context handed to the model.
_CONTEXT_BUDGET = 6000

#: Upper bound on the accumulated question pool per keyword.
_MAX_QUESTION_POOL = 30

_GROUNDING = (
    "You are Elite, a study assistant for secondary-school students. "
    "Use ONLY the curriculum excerpts provided. Do not invent facts beyond them. "
    "Answer in the SAME LANGUAGE as the excerpts (Arabic excerpts -> Arabic answer). "
    "Keep the level appropriate for a secondary-school student."
)


@dataclass(frozen=True, slots=True)
class Explanation:
    simple: str
    advanced: str
    real_life: str
    related: list[str]


@dataclass(frozen=True, slots=True)
class MCQ:
    question: str
    options: list[str]
    correct_index: int


def _context(contexts: list[str]) -> str:
    joined = "\n---\n".join(c.strip() for c in contexts if c.strip())
    return joined[:_CONTEXT_BUDGET]


class StudyAI:
    """Summary / explanation / question generation over curriculum text.

    An optional :class:`AICache` reuses results across users and restarts,
    keyed by ``(feature, scope, keyword)``. ``scope`` distinguishes semesters
    or grades so the same keyword in different curricula is cached separately.
    """

    def __init__(self, provider: AIProvider, cache: AICache | None = None) -> None:
        self.provider = provider
        self.cache = cache

    def available(self) -> bool:
        return self.provider.available()

    # -- summary ----------------------------------------------------------
    def summary(self, keyword: str, contexts: list[str], scope: str = "") -> str:
        if self.cache and (hit := self.cache.get("summary", scope, keyword)) is not None:
            return hit
        prompt = (
            f'Summarize everything the curriculum says about "{keyword}". '
            "Merge repeated ideas, remove duplication, and produce one clean, "
            "concise study summary as short bullet points.\n\n"
            f"CURRICULUM EXCERPTS:\n{_context(contexts)}"
        )
        result = self.provider.complete(prompt, system=_GROUNDING, temperature=0.3, max_tokens=800)
        if self.cache:
            self.cache.set("summary", scope, keyword, result)
        return result

    # -- explanation ------------------------------------------------------
    def explanation(self, keyword: str, contexts: list[str], scope: str = "") -> Explanation:
        if self.cache and (hit := self.cache.get("explanation", scope, keyword)) is not None:
            return Explanation(**hit)
        schema = {
            "type": "object",
            "properties": {
                "simple": {"type": "string"},
                "advanced": {"type": "string"},
                "real_life": {"type": "string"},
                "related": {"type": "array", "items": {"type": "string"}, "minItems": 3},
            },
        }
        prompt = (
            f'Using ONLY the book pages below, explain "{keyword}" for a medical prep student.\n'
            "Return ONLY a JSON object of this exact shape (values in the same language as the book):\n"
            '{"simple": "...", "advanced": "...", "real_life": "...", '
            '"related": ["...", "...", "..."]}\n'
            "simple = a clear beginner summary drawn directly from the book text, "
            "advanced = a deeper explanation of the mechanism or detail from the book, "
            "real_life = a real clinical/medical example mentioned or implied by the book, "
            "related = 3-5 related concept names found in the same pages.\n"
            "Do NOT add any information not present in the book pages.\n\n"
            f"BOOK PAGES:\n{_context(contexts)}"
        )
        data = self.provider.complete_json(
            prompt, schema=schema, system=_GROUNDING, max_tokens=3072
        )
        if not isinstance(data, dict):
            raise AIError("explanation response was not an object")
        related = data.get("related") or []
        explanation = Explanation(
            simple=str(data.get("simple", "")).strip(),
            advanced=str(data.get("advanced", "")).strip(),
            real_life=str(data.get("real_life", "")).strip(),
            related=[str(r).strip() for r in related if str(r).strip()],
        )
        if self.cache:
            self.cache.set("explanation", scope, keyword, {
                "simple": explanation.simple, "advanced": explanation.advanced,
                "real_life": explanation.real_life, "related": explanation.related,
            })
        return explanation

    # -- questions --------------------------------------------------------
    def questions(self, keyword: str, contexts: list[str], n: int = 5,
                  scope: str = "", force: bool = False) -> list[MCQ]:
        """Return ``n`` MCQs.

        The cache holds a *growing pool* per keyword. A normal request returns
        the stable first ``n`` from the pool (or generates them if empty).
        ``force`` (the "Generate More" path) generates ``n`` NEW questions the
        pool doesn't already contain, appends them, and returns just those —
        the original set is never overwritten.
        """
        pool = self._load_pool(scope, keyword)

        if not force and pool:
            return pool[:n]

        fresh = self._generate_questions(keyword, contexts, n, avoid=pool)
        if not fresh:
            return pool[:n]  # generation failed; fall back to what we have

        # Append the genuinely-new questions to the pool (dedup, capped).
        merged = _dedup_questions(pool + fresh)[:_MAX_QUESTION_POOL]
        if self.cache:
            self.cache.set("questions", scope, keyword, [_mcq_to_dict(m) for m in merged])
        return fresh if force else merged[:n]

    def _load_pool(self, scope: str, keyword: str) -> list[MCQ]:
        if not self.cache:
            return []
        raw = self.cache.get("questions", scope, keyword) or []
        return [MCQ(**q) for q in raw]

    def _generate_questions(self, keyword: str, contexts: list[str], n: int,
                            avoid: list[MCQ]) -> list[MCQ]:
        schema = {
            "type": "array",
            "minItems": n,
            "items": {
                "type": "object",
                "properties": {
                    "question": {"type": "string"},
                    "options": {"type": "array", "items": {"type": "string"}, "minItems": 4},
                    "correct_index": {"type": "integer"},
                },
            },
        }
        avoid_clause = ""
        if avoid:
            # Show the most recent existing questions so new ones differ.
            recent = "; ".join(m.question for m in avoid[-15:])
            avoid_clause = (
                "\nDo NOT repeat or paraphrase any of these already-asked questions: "
                f"{recent}\n"
            )
        prompt = (
            f'Write exactly {n} NEW multiple-choice questions about "{keyword}", based ONLY '
            "on the curriculum below. No true/false, no essay questions."
            f"{avoid_clause}\n"
            "Return ONLY a JSON array of objects of this exact shape (text in the "
            "curriculum's language):\n"
            '[{"question": "...", "options": ["...", "...", "...", "..."], '
            '"correct_index": 0}]\n'
            "Each object must have exactly 4 options and exactly one correct answer; "
            "correct_index is the 0-based index of the correct option.\n\n"
            f"CURRICULUM EXCERPTS:\n{_context(contexts)}"
        )
        data = self.provider.complete_json(
            prompt, schema=schema, system=_GROUNDING, max_tokens=6144
        )
        if not isinstance(data, list):
            data = data.get("questions", []) if isinstance(data, dict) else []
        fresh = _normalize_questions(data, n)
        # Drop any that duplicate the existing pool despite the instruction.
        seen = {normalize(m.question) for m in avoid}
        return [m for m in fresh if normalize(m.question) not in seen]


def _mcq_to_dict(m: MCQ) -> dict:
    return {"question": m.question, "options": m.options, "correct_index": m.correct_index}


def _dedup_questions(mcqs: list[MCQ]) -> list[MCQ]:
    """Keep first occurrence of each question (by normalized text), in order."""
    seen: set[str] = set()
    unique: list[MCQ] = []
    for m in mcqs:
        key = normalize(m.question)
        if key and key not in seen:
            seen.add(key)
            unique.append(m)
    return unique


def _normalize_questions(raw: list, n: int) -> list[MCQ]:
    """Validate, shuffle options, and keep at most ``n`` well-formed MCQs."""
    result: list[MCQ] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        question = str(item.get("question", "")).strip()
        options = [str(o).strip() for o in (item.get("options") or []) if str(o).strip()]
        if not question or len(options) < 2:
            continue
        options = options[:4]
        try:
            correct = int(item.get("correct_index", 0))
        except (TypeError, ValueError):
            correct = 0
        correct = max(0, min(correct, len(options) - 1))

        # Shuffle so the correct answer isn't always in the model's first slot.
        correct_text = options[correct]
        shuffled = options[:]
        random.shuffle(shuffled)
        result.append(
            MCQ(question=question, options=shuffled, correct_index=shuffled.index(correct_text))
        )
        if len(result) >= n:
            break
    return result
