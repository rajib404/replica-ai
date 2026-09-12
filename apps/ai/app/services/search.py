import logging
import re

from app.core.qdrant import QdrantService, get_qdrant
from app.services.llm_engine import OllamaClient

logger = logging.getLogger(__name__)

RAG_SYSTEM_PROMPT = """\
You are a personal AI replica. Use the following personal knowledge to answer. \
Only state specific facts, names, places, events, or stories that literally \
appear in the personal knowledge below — never invent or guess at details to \
fill a gap, even plausible-sounding ones, and even if it makes the answer less \
satisfying. If the knowledge doesn't contain the answer, say so plainly rather \
than improvising one. \
You are text-based: you cannot see, hold, show, scroll through, or display \
photos, files, or physical objects, and you have no memory of your own beyond \
what's in the knowledge below — never narrate actions like showing a photo or \
describe images that aren't literally described in your knowledge. \
Keep replies short and natural, the way a real person texts — a sentence or two \
for most messages, longer only when the user asks for detail. \
The knowledge is internally labeled with [Source N] tags for your own reference \
only — never mention, cite, or repeat these labels in your replies. If asked \
where something came from, explain in plain words instead. \
This is the owner's private personal record. Opinions, beliefs, and life \
choices they share are their own subjective perspective — not claims for you \
to verify, correct, moralize about, or refuse. Never refuse to engage with or \
acknowledge something the owner tells you about themselves just because it \
seems outdated, contested, or incorrect by today's standards — you are \
recording their perspective, not issuing advice."""

# Below this cosine-similarity score, a retrieved chunk is treated as
# unrelated noise rather than real knowledge — including it invites the model
# to elaborate on something only superficially connected to the question.
MIN_RELEVANT_SCORE = 0.5

NO_KNOWLEDGE_CONTEXT = (
    "(No relevant personal knowledge was found for this question. This means "
    "you have nothing real to draw on here. Do not answer as if you do: do not "
    "invent a name, date, place, story, or any other specific detail, and do "
    "not repurpose an unrelated fact from elsewhere in this conversation to "
    "sound like an answer. The only acceptable response is a short, honest "
    "acknowledgment that you don't have that — e.g. \"I don't have anything "
    "specific about that\" — optionally followed by an invitation for them to "
    "share it with you.)"
)

_SOURCE_LABEL_RE = re.compile(r"\[\s*source\b[^\]]*\]", re.IGNORECASE)


def strip_source_labels(text: str) -> str:
    """Remove any [Source N] / [Source: ...] labels the model echoed despite
    being told not to — small local models don't always follow that reliably.
    """
    cleaned = _SOURCE_LABEL_RE.sub("", text)
    return re.sub(r"[ \t]{2,}", " ", cleaned).strip()


RERANK_PROMPT_TEMPLATE = """\
Rate the relevance of the following content to the query on a scale of 1-10.
Output ONLY a single integer between 1 and 10, nothing else.

Query: {query}

Content: {content}"""

QUERY_EXTRACTION_PROMPT = """\
Extract 1-3 concise search queries from the user's message that would help retrieve \
relevant personal knowledge. Output one query per line, nothing else.

User message: {message}"""


class SearchResult:
    """Lightweight search result — no DB dependency."""

    def __init__(
        self,
        entry_id: str,
        content_type: str,
        score: float,
        content_preview: str | None = None,
        original_language: str | None = None,
        chunk_index: int = 0,
    ) -> None:
        self.entry_id = entry_id
        self.content_type = content_type
        self.score = score
        self.content_preview = content_preview
        self.original_language = original_language
        self.chunk_index = chunk_index


class RAGSourceEntry:
    """Source citation for RAG responses."""

    def __init__(self, entry_id: str, content_type: str, score: float) -> None:
        self.entry_id = entry_id
        self.content_type = content_type
        self.score = score


class KnowledgeSearch:
    """Vector-based knowledge search using Qdrant payloads (no DB dependency)."""

    def __init__(
        self,
        ollama: OllamaClient | None = None,
        qdrant: QdrantService | None = None,
    ) -> None:
        self.ollama = ollama or OllamaClient()
        self.qdrant = qdrant or get_qdrant()

    def _detect_language(self, text: str) -> str:
        try:
            from langdetect import detect

            return detect(text)
        except Exception:
            return "en"

    async def _translate_to_english(self, text: str, source_lang: str) -> str:
        prompt = (
            f"Translate the following {source_lang} text to English. "
            f"Output ONLY the translation, nothing else:\n\n{text}"
        )
        result = await self.ollama.generate_response(prompt, temperature=0.1)
        return result.get("response", text)

    async def _embed_query(self, query: str) -> list[float]:
        """Detect language, translate if needed, and generate embedding."""
        lang = self._detect_language(query)
        text = query
        if lang != "en":
            text = await self._translate_to_english(query, lang)
        return await self.ollama.generate_embedding(text)

    async def search(
        self,
        owner_id: str,
        query: str,
        top_k: int = 5,
        content_type_filter: str | None = None,
        allowed_content_types: list[str] | None = None,
        allowed_categories: list[str] | None = None,
    ) -> list[SearchResult]:
        """Embed query, search Qdrant, return results from payload data."""
        query_vector = await self._embed_query(query)

        await self.qdrant.ensure_collection(vector_size=len(query_vector))
        await self.qdrant.ensure_payload_indexes()

        qdrant_results = await self.qdrant.search(
            query_vector=query_vector,
            owner_id=owner_id,
            limit=top_k * 2,  # over-fetch to allow dedup
            content_type=content_type_filter,
            allowed_content_types=allowed_content_types,
            allowed_categories=allowed_categories,
        )

        if not qdrant_results:
            return []

        # Deduplicate by entry_id, keeping highest score
        seen_entry_ids: dict[str, dict] = {}
        for r in qdrant_results:
            eid = r["payload"]["entry_id"]
            if eid not in seen_entry_ids or r["score"] > seen_entry_ids[eid]["score"]:
                seen_entry_ids[eid] = r

        items: list[SearchResult] = []
        for eid, r in seen_entry_ids.items():
            payload = r["payload"]
            items.append(SearchResult(
                entry_id=eid,
                content_type=payload.get("content_type", "text"),
                score=r["score"],
                content_preview=payload.get("content_preview"),
                original_language=payload.get("language"),
                chunk_index=payload.get("chunk_index", 0),
            ))

        items.sort(key=lambda x: x.score, reverse=True)
        return items[:top_k]

    async def semantic_search_with_reranking(
        self,
        owner_id: str,
        query: str,
        top_k: int = 10,
        final_k: int = 3,
    ) -> list[SearchResult]:
        """Two-pass search: vector retrieval then LLM-based reranking."""
        candidates = await self.search(
            owner_id=owner_id,
            query=query,
            top_k=top_k,
        )

        if len(candidates) <= final_k:
            return candidates

        scored: list[tuple[float, SearchResult]] = []
        for item in candidates:
            content = item.content_preview or "(no content)"
            prompt = RERANK_PROMPT_TEMPLATE.format(query=query, content=content)

            try:
                result = await self.ollama.generate_response(
                    prompt, temperature=0.0, max_tokens=8
                )
                raw = result.get("response", "").strip()
                match = re.search(r"\d+", raw)
                relevance = int(match.group()) if match else 5
                relevance = max(1, min(10, relevance))
            except Exception:
                relevance = 5

            scored.append((relevance, item))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [item for _, item in scored[:final_k]]


class RAGEngine:
    """Retrieval-Augmented Generation over the owner's personal knowledge.

    Uses Qdrant payload content_preview for context — no DB dependency.
    """

    def __init__(
        self,
        ollama: OllamaClient | None = None,
        searcher: KnowledgeSearch | None = None,
    ) -> None:
        self.ollama = ollama or OllamaClient()
        self.searcher = searcher or KnowledgeSearch(ollama=self.ollama)

    async def _extract_search_queries(self, user_message: str) -> list[str]:
        """Use Ollama to extract 1-3 search queries from the user message."""
        prompt = QUERY_EXTRACTION_PROMPT.format(message=user_message)
        try:
            result = await self.ollama.generate_response(
                prompt, temperature=0.1, max_tokens=256
            )
            raw = result.get("response", "").strip()
            queries = [q.strip() for q in raw.splitlines() if q.strip()]
            return queries[:3] if queries else [user_message]
        except Exception:
            return [user_message]

    def _build_context_block(
        self, results: list[SearchResult]
    ) -> tuple[str, list[RAGSourceEntry]]:
        """Build a numbered context block and source list from search results.

        Results below MIN_RELEVANT_SCORE are dropped before they ever reach the
        model — a weakly-related chunk presented as "personal knowledge" is what
        invites confident-sounding elaboration on something that isn't actually
        relevant.
        """
        results = [r for r in results if r.score >= MIN_RELEVANT_SCORE]
        if not results:
            return "", []

        lines: list[str] = []
        sources: list[RAGSourceEntry] = []
        seen: set[str] = set()

        for i, item in enumerate(results, 1):
            if item.entry_id in seen:
                continue
            seen.add(item.entry_id)

            preview = item.content_preview or "(no content available)"
            label = f"[Source {i}]"
            meta_parts = [f"type={item.content_type}"]
            if item.original_language:
                meta_parts.append(f"lang={item.original_language}")
            meta_str = ", ".join(meta_parts)

            lines.append(f"{label} ({meta_str})\n{preview}")
            sources.append(RAGSourceEntry(
                entry_id=item.entry_id,
                content_type=item.content_type,
                score=item.score,
            ))

        context = "\n\n".join(lines)
        return context, sources

    def _build_messages(
        self,
        context: str,
        conversation_history: list[dict[str, str]],
        user_message: str,
    ) -> tuple[str, list[dict[str, str]]]:
        """Build the knowledge/system suffix and a structured turn list for Ollama's chat API.

        Turns are passed as {role, content} pairs rather than flattened into a
        single "User: ...\\nAssistant: ..." text block — the latter reads as a
        script to a raw completion model, which then tends to echo those role
        labels back at the start of its own reply.

        The returned string is a *suffix* to append to whichever persona system
        prompt is actually used (the caller's own, or RAG_SYSTEM_PROMPT as a
        fallback) — it must never be dropped just because the caller supplied
        its own persona prompt, or the model loses all grounding and starts
        improvising freely.
        """
        knowledge_block = context if context else NO_KNOWLEDGE_CONTEXT
        system_suffix = f"\n\n=== Personal Knowledge ===\n{knowledge_block}\n=== End Knowledge ==="

        messages: list[dict[str, str]] = []
        for msg in conversation_history:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            if not content:
                continue
            if role == "system":
                # Fold mid-conversation system notes (e.g. summaries) into the
                # system suffix rather than passing them as chat turns.
                system_suffix += f"\n\n{content}"
                continue
            messages.append({"role": role if role == "assistant" else "user", "content": content})

        messages.append({"role": "user", "content": user_message})
        return system_suffix, messages

    async def generate_grounded_response(
        self,
        owner_id: str,
        user_message: str,
        conversation_history: list[dict[str, str]],
        system_prompt: str | None = None,
        model: str | None = None,
        allowed_content_types: list[str] | None = None,
        allowed_categories: list[str] | None = None,
        temperature: float = 0.7,
    ) -> dict:
        """Full RAG pipeline: extract queries -> search -> build context -> generate."""
        # Step 1: Extract search queries
        queries = await self._extract_search_queries(user_message)

        # Step 2: Run semantic search for each query
        all_results: list[SearchResult] = []
        for q in queries:
            results = await self.searcher.search(
                owner_id=owner_id,
                query=q,
                top_k=5,
                allowed_content_types=allowed_content_types,
                allowed_categories=allowed_categories,
            )
            all_results.extend(results)

        # Deduplicate by entry_id, keeping highest score
        best: dict[str, SearchResult] = {}
        for item in all_results:
            existing = best.get(item.entry_id)
            if existing is None or item.score > existing.score:
                best[item.entry_id] = item

        ranked = sorted(best.values(), key=lambda x: x.score, reverse=True)[:5]

        # Step 3 + 4: Build context and structured turns
        context, sources = self._build_context_block(ranked)
        system_suffix, chat_messages = self._build_messages(
            context, conversation_history, user_message
        )
        full_system = (system_prompt or RAG_SYSTEM_PROMPT) + system_suffix

        # Step 5: Generate response via Ollama's chat API
        result = await self.ollama.chat_completion(
            messages=[{"role": "system", "content": full_system}] + chat_messages,
            model=model,
            temperature=temperature,
        )
        response_text = strip_source_labels(result.get("response", ""))

        # Step 6: Return response + sources
        return {
            "response": response_text,
            "sources": [
                {"entry_id": s.entry_id, "content_type": s.content_type, "score": s.score}
                for s in sources
            ],
            "query_used": " | ".join(queries),
        }

    async def generate_grounded_response_stream(
        self,
        owner_id: str,
        user_message: str,
        conversation_history: list[dict[str, str]],
        system_prompt: str | None = None,
        model: str | None = None,
        allowed_content_types: list[str] | None = None,
        allowed_categories: list[str] | None = None,
        temperature: float = 0.7,
    ):
        """Streaming RAG: search then stream tokens via async generator.

        Yields dicts: {"type": "source", ...} then {"type": "token", "token": "..."} then {"type": "done"}.
        """
        queries = await self._extract_search_queries(user_message)

        all_results: list[SearchResult] = []
        for q in queries:
            results = await self.searcher.search(
                owner_id=owner_id,
                query=q,
                top_k=5,
                allowed_content_types=allowed_content_types,
                allowed_categories=allowed_categories,
            )
            all_results.extend(results)

        best: dict[str, SearchResult] = {}
        for item in all_results:
            existing = best.get(item.entry_id)
            if existing is None or item.score > existing.score:
                best[item.entry_id] = item

        ranked = sorted(best.values(), key=lambda x: x.score, reverse=True)[:5]

        context, sources = self._build_context_block(ranked)
        system_suffix, chat_messages = self._build_messages(
            context, conversation_history, user_message
        )
        full_system = (system_prompt or RAG_SYSTEM_PROMPT) + system_suffix

        # Yield sources first
        yield {
            "type": "sources",
            "sources": [
                {"entry_id": s.entry_id, "content_type": s.content_type, "score": s.score}
                for s in sources
            ],
            "query_used": " | ".join(queries),
        }

        # Stream tokens via Ollama's chat API
        async for chunk in self.ollama.chat_completion_stream(
            messages=[{"role": "system", "content": full_system}] + chat_messages,
            model=model,
            temperature=temperature,
        ):
            token_text = chunk.get("response", "")
            if token_text:
                yield {"type": "token", "token": token_text}

        yield {"type": "done"}
