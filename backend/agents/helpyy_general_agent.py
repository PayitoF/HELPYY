"""Agent 5: Helpyy General — FAQ, BBVA products, operational queries.

This is the default/fallback agent. Handles greetings, general banking
questions, and product information. Detects when the user needs a
specialised agent and signals a handoff.

Includes a lightweight FAQ RAG layer: a JSON knowledge base with TF-IDF
similarity matching. High-confidence FAQ hits are answered directly without
calling the LLM, saving tokens.
"""

from __future__ import annotations

import json
import math
import os
import re
from pathlib import Path

from backend.agents.base_agent import BaseAgent, AgentResponse
from backend.llm.provider import LLMProvider

# -----------------------------------------------------------------------
# System prompt
# -----------------------------------------------------------------------

from backend.agents.prompt_loader import load_prompt

_SYSTEM_PROMPT = load_prompt("helpyy_general")


# -----------------------------------------------------------------------
# Handoff keyword sets
# -----------------------------------------------------------------------

_CREDIT_KEYWORDS = {
    "crédito", "credito", "préstamo", "prestamo", "microcrédito", "microcredito",
    "califico", "prestan", "cupo", "aprobado", "financiamiento",
}
_ADVICE_KEYWORDS = {
    "mejorar", "puntaje", "score", "tips", "ahorro", "plan financiero",
    "misiones", "misión", "mision", "asesor financiero",
}
_ONBOARDING_KEYWORDS = {
    "abrir cuenta", "no soy cliente", "registrarme", "bancarizarme",
    "nueva cuenta", "quiero una cuenta",
}

# Handoff transition messages
_HANDOFF_MESSAGES = {
    "credit_evaluator": (
        "Para eso te voy a conectar con nuestro evaluador de crédito, "
        "que puede revisar tu perfil y decirte tus opciones. Un momento..."
    ),
    "financial_advisor": (
        "Para eso te voy a conectar con tu asesor financiero personal, "
        "que te puede ayudar con un plan a tu medida. Un momento..."
    ),
    "onboarding": (
        "Para eso te voy a conectar con nuestro agente de bienvenida, "
        "que te guiará para abrir tu cuenta. Un momento..."
    ),
}


# -----------------------------------------------------------------------
# FAQ knowledge base
# -----------------------------------------------------------------------

_FAQ_PATH = Path(__file__).resolve().parent.parent / "data" / "faq_bbva.json"

# Similarity threshold: above this, answer directly from FAQ without LLM
FAQ_CONFIDENCE_THRESHOLD = 0.25


class FAQEntry:
    """A single FAQ item with pre-computed search terms."""

    __slots__ = ("id", "question", "keywords", "answer", "category", "terms")

    def __init__(self, data: dict):
        self.id: str = data["id"]
        self.question: str = data["question"]
        self.keywords: list[str] = data.get("keywords", [])
        self.answer: str = data["answer"]
        self.category: str = data.get("category", "general")
        # Pre-compute normalised terms for matching
        self.terms: set[str] = _tokenize(
            self.question + " " + " ".join(self.keywords)
        )


class FAQKnowledgeBase:
    """Lightweight FAQ search using term overlap + keyword boost.

    No external dependencies — uses simple normalised term intersection
    with a boost for exact keyword matches. Fast enough for <100 FAQs.
    """

    def __init__(self, entries: list[FAQEntry] | None = None):
        self.entries = entries or []
        # Build IDF weights from corpus
        self._idf: dict[str, float] = {}
        self._build_idf()

    @classmethod
    def from_json(cls, path: str | Path | None = None) -> FAQKnowledgeBase:
        """Load FAQ from JSON file."""
        path = Path(path) if path else _FAQ_PATH
        if not path.exists():
            return cls([])
        with open(path, encoding="utf-8") as f:
            raw = json.load(f)
        entries = [FAQEntry(item) for item in raw]
        return cls(entries)

    def search(self, query: str, top_k: int = 3) -> list[tuple[FAQEntry, float]]:
        """Find the most relevant FAQ entries for a query.

        Returns list of (entry, score) tuples sorted by score descending.
        Score is 0.0–1.0 where 1.0 = perfect match.
        """
        if not self.entries:
            return []

        query_terms = _tokenize(query)
        if not query_terms:
            return []

        results: list[tuple[FAQEntry, float]] = []
        for entry in self.entries:
            score = self._score(query, query_terms, entry)
            if score > 0:
                results.append((entry, score))

        results.sort(key=lambda x: x[1], reverse=True)
        return results[:top_k]

    def best_match(self, query: str) -> tuple[FAQEntry | None, float]:
        """Return the single best FAQ match and its confidence score."""
        results = self.search(query, top_k=1)
        if results:
            return results[0]
        return None, 0.0

    def _score(self, raw_query: str, query_terms: set[str], entry: FAQEntry) -> float:
        """Compute relevance score between query and FAQ entry.

        Combines:
        1. TF-IDF weighted term overlap (cosine-like)
        2. Exact keyword match boost
        """
        if not query_terms or not entry.terms:
            return 0.0

        # Term overlap with IDF weighting
        common = query_terms & entry.terms
        if not common:
            return 0.0

        idf_sum = sum(self._idf.get(t, 1.0) for t in common)
        query_norm = math.sqrt(sum(self._idf.get(t, 1.0) ** 2 for t in query_terms))
        entry_norm = math.sqrt(sum(self._idf.get(t, 1.0) ** 2 for t in entry.terms))

        if query_norm == 0 or entry_norm == 0:
            return 0.0

        tfidf_score = idf_sum / (query_norm * entry_norm)

        # Keyword boost: exact substring match in the query for FAQ keywords
        query_lower = raw_query.lower()
        keyword_hits = sum(1 for kw in entry.keywords if kw in query_lower)
        keyword_boost = min(keyword_hits * 0.15, 0.45)  # cap at 0.45

        return min(tfidf_score + keyword_boost, 1.0)

    def _build_idf(self) -> None:
        """Build IDF weights from the FAQ corpus."""
        if not self.entries:
            return
        n = len(self.entries)
        doc_freq: dict[str, int] = {}
        for entry in self.entries:
            for term in entry.terms:
                doc_freq[term] = doc_freq.get(term, 0) + 1
        self._idf = {
            term: math.log((n + 1) / (df + 1)) + 1
            for term, df in doc_freq.items()
        }


# Shared stopwords for Spanish
_STOPWORDS = {
    "el", "la", "los", "las", "un", "una", "de", "del", "en", "y", "o",
    "que", "es", "por", "para", "con", "se", "al", "lo", "como", "más",
    "pero", "su", "le", "ya", "este", "esta", "son", "fue", "ser", "tiene",
    "mi", "me", "te", "a", "no", "sí", "si", "muy", "qué", "cómo",
    "cuál", "cuáles", "cuánto", "hay", "dónde", "donde",
}


def _tokenize(text: str) -> set[str]:
    """Normalise and tokenize text into a set of meaningful terms."""
    lower = text.lower()
    # Remove accents for matching (keep originals in keywords)
    lower = lower.replace("á", "a").replace("é", "e").replace("í", "i")
    lower = lower.replace("ó", "o").replace("ú", "u").replace("ñ", "n")
    words = re.findall(r"[a-z0-9]+", lower)
    return {w for w in words if w not in _STOPWORDS and len(w) > 1}


# Module-level FAQ singleton (loaded once)
_faq_kb: FAQKnowledgeBase | None = None


def get_faq_kb() -> FAQKnowledgeBase:
    global _faq_kb
    if _faq_kb is None:
        _faq_kb = FAQKnowledgeBase.from_json()
    return _faq_kb


# -----------------------------------------------------------------------
# HelpyyGeneralAgent
# -----------------------------------------------------------------------

class HelpyyGeneralAgent(BaseAgent):
    """General-purpose assistant for BBVA Colombia.

    Handles greetings, FAQ, product info, and operational queries.
    Detects specialised intents and signals handoff via AgentResponse.

    FAQ RAG: checks the knowledge base first. High-confidence matches
    are answered directly without calling the LLM.
    """

    name = "helpyy_general"
    system_prompt = _SYSTEM_PROMPT
    tools = []
    _tool_handlers = {}

    def __init__(self, llm: LLMProvider, faq_kb: FAQKnowledgeBase | None = None):
        super().__init__(llm)
        self._faq_kb = faq_kb or get_faq_kb()

    async def process(self, message: str, context: dict, *, original_message: str | None = None) -> AgentResponse:
        # 1. Check handoff first
        handoff = self._detect_handoff(message)

        if handoff:
            # Transparent handoff message — no LLM call needed
            transition_msg = _HANDOFF_MESSAGES.get(handoff, "Un momento...")
            return AgentResponse(
                content=transition_msg,
                agent_name=self.name,
                agent_type="general",
                handoff_to=handoff,
                suggested_actions=[],
                metadata={"handoff_reason": "intent_detected"},
            )

        # 2. Try FAQ RAG — skip LLM if high confidence match
        faq_entry, confidence = self._faq_kb.best_match(message)
        if faq_entry and confidence >= FAQ_CONFIDENCE_THRESHOLD:
            return AgentResponse(
                content=faq_entry.answer,
                agent_name=self.name,
                agent_type="general",
                suggested_actions=self._suggest_actions(message),
                metadata={
                    "source": "faq",
                    "faq_id": faq_entry.id,
                    "faq_confidence": round(confidence, 3),
                },
            )

        # 3. Fallback to LLM
        messages = self._build_messages(message, context)

        # If FAQ had a partial match, inject it into the system prompt (index 0).
        # Mid-conversation system messages confuse smaller models → empty output.
        if faq_entry and confidence > 0.15:
            faq_hint = (
                f"\n\n[Contexto FAQ relevante (confianza {confidence:.0%}): "
                f"{faq_entry.answer}]"
            )
            if messages and messages[0]["role"] == "system":
                messages[0] = {
                    "role": "system",
                    "content": messages[0]["content"] + faq_hint,
                }
            else:
                messages.insert(0, {"role": "system", "content": faq_hint.strip()})

        content = await self.llm.generate(messages, temperature=0.7)

        return AgentResponse(
            content=content,
            agent_name=self.name,
            agent_type="general",
            suggested_actions=self._suggest_actions(message),
            metadata={"source": "llm"},
        )

    async def process_stream(self, message: str, context: dict, *, original_message: str | None = None):
        messages = self._build_messages(message, context)
        async for token in self.llm.generate_stream(messages, temperature=0.7):
            yield token

    # ------------------------------------------------------------------
    # Handoff detection
    # ------------------------------------------------------------------

    def _detect_handoff(self, message: str) -> str | None:
        """Check if the message indicates the user needs a different agent."""
        lower = message.lower()
        if any(kw in lower for kw in _CREDIT_KEYWORDS):
            return "credit_evaluator"
        if any(kw in lower for kw in _ADVICE_KEYWORDS):
            return "financial_advisor"
        if any(kw in lower for kw in _ONBOARDING_KEYWORDS):
            return "onboarding"
        return None

    # ------------------------------------------------------------------
    # Suggested actions
    # ------------------------------------------------------------------

    def _suggest_actions(self, message: str) -> list[str]:
        """Suggest quick-reply actions based on the message."""
        lower = message.lower()
        if any(w in lower for w in ("hola", "buenas", "hey", "saludos")):
            return [
                "Consultar productos",
                "Quiero un microcrédito",
                "Horarios y sucursales",
            ]
        if any(w in lower for w in ("horario", "sucursal", "dirección")):
            return ["Ver mapa de sucursales", "Llamar al banco"]
        if any(w in lower for w in ("transferencia", "pago", "enviar")):
            return ["Hacer transferencia", "Pagar servicios"]
        if any(w in lower for w in ("tarjeta", "aqua", "crédito")):
            return ["Ver tarjetas", "Bloquear tarjeta"]
        if any(w in lower for w in ("cdt", "inversión", "inversion")):
            return ["Simular CDT", "Ver tasas"]
        if any(w in lower for w in ("seguro", "póliza")):
            return ["Ver seguros disponibles"]
        return []

    def _agent_type(self) -> str:
        return "general"
