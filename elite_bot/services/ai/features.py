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
    "You are Elite, a study assistant for medical preparatory-year students in Syria. "
    "Use ONLY the curriculum excerpts provided. Do not invent facts beyond them. "
    "Write ALL responses in Arabic. Keep English scientific/medical terms (anatomy names, "
    "drug names, Latin terms) in their original English within the Arabic text. "
    "Keep the level appropriate for a first-year medical prep student."
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
    difficulty: str = "medium"


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
            f'اكتب تعريفاً موجزاً جداً لمفهوم "{keyword}" بناءً على المقاطع أدناه. '
            "يجب أن يكون الملخص قصيراً: جملة تعريف واحدة + 2-3 نقاط رئيسية فقط (لا أكثر). "
            "استخدم التنسيق التالي في النص:\n"
            "- **كلمة** للمصطلحات الأساسية والتعريفات المهمة (تظهر بالخط العريض)\n"
            "- *كلمة* للأسماء العلمية والمصطلحات اللاتينية أو الإنجليزية (تظهر بخط مائل)\n"
            "- _كلمة_ للنقاط التي تستحق التأكيد (تظهر بخط تحتي)\n"
            "- ==كلمة== للكلمات التي تحتاج تمييزاً بلون (highlight)\n"
            "اكتب الإجابة باللغة العربية وأبقِ المصطلحات الإنجليزية/العلمية بالإنجليزية.\n\n"
            f"مقاطع المنهج:\n{_context(contexts)}"
        )
        result = self.provider.complete(prompt, system=_GROUNDING, temperature=0.3, max_tokens=300)
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
                "not_scientific": {"type": "boolean"},
                "explanation": {"type": "string"},
                "real_life": {"type": "string"},
                "related": {"type": "array", "items": {"type": "string"}, "minItems": 3},
            },
            "required": ["not_scientific"],
        }
        ctx_text = _context(contexts)
        if ctx_text:
            source_instruction = (
                "اشرح بناءً على صفحات الكتاب أدناه في المقام الأول، "
                "وأكمل من معرفتك الطبية العامة إن لزم.\n\n"
                f"صفحات الكتاب:\n{ctx_text}"
            )
            related_hint = "related = 4-6 مفاهيم مرتبطة من نفس الصفحات."
        else:
            source_instruction = "اشرح من معرفتك الطبية العامة."
            related_hint = "related = 4-6 مفاهيم طبية مرتبطة بهذا المفهوم."
        prompt = (
            f'أولاً: هل "{keyword}" مصطلح علمي أو طبي أو فيزيولوجي أو كيميائي أو بيولوجي؟\n'
            'إذا لم يكن مصطلحاً علمياً/طبياً (مثلاً: تحية، سؤال عام، اسم شخص، كلمة عادية)، أعد فقط:\n'
            '{"not_scientific": true}\n\n'
            f'أما إذا كان مصطلحاً علمياً/طبياً، اشرح "{keyword}" شرحاً مفصّلاً وعميقاً '
            f'لطالب في السنة التحضيرية الطبية. {source_instruction}\n'
            "أعد JSON بهذا الشكل:\n"
            '{"not_scientific": false, "explanation": "...", "real_life": "...", "related": ["...", "...", "..."]}\n'
            "explanation = شرح شامل ومفصّل جداً: ابدأ بالتعريف، ثم اشرح الآلية خطوة بخطوة، "
            "ثم التفاصيل والعوامل والأنواع إن وجدت، ثم الأهمية الطبية. استخدم العناوين الفرعية (###) والنقاط (-) والخط العريض (**). "
            "يجب أن يكون طويلاً ويغطي الموضوع كاملاً (لا تقل عن 10-15 جملة). "
            "real_life = سيناريو سريري/طبي واقعي مفصّل (3-4 جمل) يوضح هذا المفهوم عملياً. "
            f"{related_hint}\n"
            "اكتب باللغة العربية وأبقِ المصطلحات العلمية الإنجليزية كما هي.\n"
        )
        data = self.provider.complete_json(
            prompt, schema=schema, system=_GROUNDING, max_tokens=4096
        )
        if not isinstance(data, dict):
            raise AIError("explanation response was not an object")
        if data.get("not_scientific"):
            raise AIError("not_scientific")
        related = data.get("related") or []
        expl_text = str(data.get("explanation", "")).strip()
        explanation = Explanation(
            simple=expl_text,
            advanced="",
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
                    "difficulty": {"type": "string"},
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
        easy = max(1, n // 3)
        hard = max(1, n // 3)
        medium = n - easy - hard
        prompt = (
            f'اكتب بالضبط {n} أسئلة اختيار من متعدد جديدة عن "{keyword}" '
            "بناءً فقط على المنهج أدناه. لا تكرر أسئلة true/false أو مقالية."
            f"{avoid_clause}\n"
            f"وزّع الأسئلة على ثلاثة مستويات بالضبط:\n"
            f"- {easy} سؤال سهل (تعريف أساسي أو حقيقة مباشرة)\n"
            f"- {medium} سؤال متوسط (تطبيق أو مقارنة بين مفهومين)\n"
            f"- {hard} سؤال صعب (تحليل، آلية معقدة، أو سيناريو سريري)\n"
            "اكتب الأسئلة والخيارات باللغة العربية. "
            "أبقِ المصطلحات العلمية والطبية الإنجليزية (أسماء أعضاء، أدوية، مصطلحات) "
            "بالإنجليزية داخل نص السؤال العربي.\n"
            "أعد JSON فقط بهذا الشكل:\n"
            '[{"question": "...", "options": ["...", "...", "...", "..."], '
            '"correct_index": 0, "difficulty": "easy|medium|hard"}]\n'
            "لكل سؤال بالضبط 4 خيارات وإجابة صحيحة واحدة؛ "
            "correct_index هو الفهرس الصحيح (يبدأ من 0).\n\n"
            f"مقاطع المنهج:\n{_context(contexts)}"
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
    return {"question": m.question, "options": m.options,
            "correct_index": m.correct_index, "difficulty": m.difficulty}


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
        difficulty = str(item.get("difficulty", "medium")).strip().lower()
        if difficulty not in ("easy", "medium", "hard"):
            difficulty = "medium"
        correct_text = options[correct]
        shuffled = options[:]
        random.shuffle(shuffled)
        result.append(
            MCQ(question=question, options=shuffled,
                correct_index=shuffled.index(correct_text), difficulty=difficulty)
        )
        if len(result) >= n:
            break
    return result
