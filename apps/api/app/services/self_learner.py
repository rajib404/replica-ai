"""Self-learning service: knowledge gap analysis, autonomous learning, maintenance."""

import logging
from datetime import UTC, datetime, timedelta

from cuid2 import cuid_wrapper
from sqlalchemy import func as sa_func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.ai_client import get_ai_client
from app.core.config import settings
from app.models.learning import (
    ConsolidationResult,
    KnowledgeGap,
    KnowledgeGapsResponse,
    LearnTopicResponse,
    LearnTopicSource,
    StaleKnowledgeEntry,
    StaleKnowledgeResponse,
)
from app.models.owner import LearningConfig, LearningLog, Owner
from app.services.web_browser import WebBrowser

logger = logging.getLogger(__name__)
generate_cuid = cuid_wrapper()

DEPTH_SEARCH_MAP = {"shallow": 2, "moderate": 4, "deep": 8}
DEPTH_SYNTHESIS_TOKENS = {"shallow": 256, "moderate": 512, "deep": 1024}


class SelfLearner:
    """Autonomous knowledge acquisition and maintenance for a replica."""

    @staticmethod
    async def identify_knowledge_gaps(
        owner_id: str, db: AsyncSession
    ) -> KnowledgeGapsResponse:
        """Analyse existing knowledge to find topics the replica knows little about.

        Uses the local LLM to examine recent conversations and knowledge entries
        then proposes gaps with suggested search queries.
        """
        ai = get_ai_client()

        # 1. Get a snapshot of what we know (sample recent entries via RAG)
        try:
            knowledge_sample = await ai.rag_search(
                owner_id, "What topics do I know about?", top_k=20
            )
        except Exception:
            knowledge_sample = {"results": []}

        results = knowledge_sample.get("results", [])
        total_entries = len(results)

        # Build a summary of known topics
        known_topics: list[str] = []
        for r in results:
            text = r.get("text", r.get("content", ""))[:200]
            if text:
                known_topics.append(text)

        known_summary = "\n".join(f"- {t}" for t in known_topics[:15])

        # 2. Ask the LLM to identify gaps
        prompt = (
            "You are analysing a personal AI replica's knowledge base. "
            "Below is a sample of what it currently knows:\n\n"
            f"{known_summary}\n\n"
            "Based on this sample, identify 3-5 knowledge gaps — important topics "
            "about the owner that are missing or under-represented. "
            "For each gap provide:\n"
            '- "topic": short name\n'
            '- "reason": why this matters\n'
            '- "priority": low/medium/high\n'
            '- "suggested_queries": 2 web search queries to fill this gap\n\n'
            "Respond ONLY with a JSON array of objects. No markdown fences."
        )

        try:
            gen = await ai.generate(prompt, temperature=0.4, max_tokens=1024)
            raw = gen.get("text", gen.get("response", "[]"))
            import json
            gaps_data = json.loads(raw)
            gaps = [KnowledgeGap(**g) for g in gaps_data]
        except Exception as exc:
            logger.warning("Failed to parse knowledge gaps: %s", exc)
            gaps = [
                KnowledgeGap(
                    topic="General background",
                    reason="Could not analyse knowledge — try adding more entries first.",
                    priority="medium",
                    suggested_queries=["personal interests", "daily routines"],
                )
            ]

        # Get last analysis timestamp
        row = await db.execute(
            select(LearningLog.created_at)
            .where(LearningLog.owner_id == owner_id)
            .order_by(LearningLog.created_at.desc())
            .limit(1)
        )
        last_log = row.scalar_one_or_none()

        return KnowledgeGapsResponse(
            gaps=gaps,
            total_entries=total_entries,
            last_analysis_at=last_log.isoformat() if last_log else None,
        )

    @staticmethod
    async def learn_topic(
        owner_id: str, topic: str, depth: str, db: AsyncSession
    ) -> LearnTopicResponse:
        """Research a topic using web search and ingest the findings.

        Steps:
        1. Search the web for the topic
        2. Summarise each source
        3. Synthesise a comprehensive knowledge entry
        4. Ingest into the knowledge base
        """
        ai = get_ai_client()
        max_results = DEPTH_SEARCH_MAP.get(depth, 4)
        synthesis_tokens = DEPTH_SYNTHESIS_TOKENS.get(depth, 512)
        sources: list[LearnTopicSource] = []
        snippets: list[str] = []

        # 1. Web search
        try:
            search_results = await WebBrowser.search_web(
                owner_id, topic, db, max_results=max_results, summarize_top=0
            )
            for sr in search_results.get("results", [])[:max_results]:
                url = sr.get("url", sr.get("href", ""))
                title = sr.get("title", "")
                snippet = sr.get("body", sr.get("snippet", ""))
                if snippet:
                    snippets.append(f"[{title}] {snippet}")
                    sources.append(LearnTopicSource(url=url, title=title, type="web_search"))
        except Exception as exc:
            logger.warning("Web search failed for topic '%s': %s", topic, exc)

        # 2. Browse top results for fuller content
        for source in sources[:min(3, max_results)]:
            if not source.url:
                continue
            try:
                page = await WebBrowser.browse(owner_id, source.url, db, summarize=True)
                summary = page.get("summary", "")
                if summary:
                    snippets.append(f"[{source.title}] {summary}")
            except Exception:
                pass

        # 3. Check existing knowledge for context
        try:
            existing = await ai.rag_search(owner_id, topic, top_k=3)
            for r in existing.get("results", []):
                text = r.get("text", r.get("content", ""))[:300]
                if text:
                    snippets.append(f"[Existing knowledge] {text}")
                    sources.append(LearnTopicSource(type="rag", title="Existing knowledge"))
        except Exception:
            pass

        # 4. Synthesise
        combined = "\n\n".join(snippets[:15])
        synthesis_prompt = (
            f"You are a personal AI replica learning about: {topic}\n\n"
            f"Research depth: {depth}\n\n"
            "Below are snippets from various sources:\n\n"
            f"{combined}\n\n"
            "Synthesise this information into a clear, well-organised knowledge entry. "
            "Focus on facts and key insights. Write in third person about the owner's interests. "
            "Format as plain text paragraphs."
        )

        try:
            gen = await ai.generate(
                synthesis_prompt, temperature=0.3, max_tokens=synthesis_tokens
            )
            synthesis = gen.get("text", gen.get("response", ""))
        except Exception as exc:
            logger.error("Synthesis failed for topic '%s': %s", topic, exc)
            synthesis = f"Research notes on {topic}:\n" + "\n".join(snippets[:5])

        # 5. Ingest into knowledge base
        entries_created = 0
        if synthesis.strip():
            try:
                await ai.ingest_text(
                    owner_id,
                    text=f"[Self-learned: {topic}] {synthesis}",
                    language="en",
                )
                entries_created = 1
            except Exception as exc:
                logger.error("Ingest failed for topic '%s': %s", topic, exc)

        # 6. Log the learning event
        summary_text = synthesis[:500] if synthesis else None
        log_entry = LearningLog(
            id=generate_cuid(),
            owner_id=owner_id,
            topic=topic,
            depth=depth,
            sources_used=[s.model_dump() for s in sources],
            entries_created=entries_created,
            summary=summary_text,
            status="completed" if entries_created > 0 else "failed",
            error_message=None if entries_created > 0 else "No content synthesised",
        )
        db.add(log_entry)
        await db.commit()

        return LearnTopicResponse(
            topic=topic,
            depth=depth,
            sources_used=sources,
            entries_created=entries_created,
            summary=summary_text or "",
        )

    @staticmethod
    async def daily_learning_routine(owner_id: str, db: AsyncSession) -> int:
        """Run the daily autonomous learning routine.

        1. Identify knowledge gaps
        2. Pick top-N topics (respecting preferences)
        3. Learn each topic
        Returns the number of topics successfully learned.
        """
        # Load preferences
        row = await db.execute(
            select(LearningConfig).where(LearningConfig.owner_id == owner_id)
        )
        config = row.scalar_one_or_none()
        if not config or not config.enabled:
            return 0

        depth = config.depth or "moderate"
        ignore = set(config.ignore_topics or [])
        auto_topics = list(config.auto_topics or [])
        max_topics = settings.learning_daily_max_topics

        # Combine auto-topics with gap analysis
        topics_to_learn: list[str] = []

        # Auto-topics first (owner-specified)
        for t in auto_topics:
            if t.lower() not in {i.lower() for i in ignore}:
                topics_to_learn.append(t)

        # Fill remaining slots with gap analysis
        if len(topics_to_learn) < max_topics:
            try:
                gaps = await SelfLearner.identify_knowledge_gaps(owner_id, db)
                for gap in gaps.gaps:
                    if gap.topic.lower() not in {i.lower() for i in ignore}:
                        if gap.topic not in topics_to_learn:
                            topics_to_learn.append(gap.topic)
                    if len(topics_to_learn) >= max_topics:
                        break
            except Exception as exc:
                logger.warning("Gap analysis failed for %s: %s", owner_id, exc)

        topics_to_learn = topics_to_learn[:max_topics]

        learned = 0
        learned_topics: list[str] = []
        for topic in topics_to_learn:
            try:
                result = await SelfLearner.learn_topic(owner_id, topic, depth, db)
                if result.entries_created > 0:
                    learned += 1
                    learned_topics.append(topic)
            except Exception as exc:
                logger.error("Failed to learn topic '%s' for %s: %s", topic, owner_id, exc)
                # Log the failure
                log_entry = LearningLog(
                    id=generate_cuid(),
                    owner_id=owner_id,
                    topic=topic,
                    depth=depth,
                    sources_used=[],
                    entries_created=0,
                    status="failed",
                    error_message=str(exc)[:500],
                )
                db.add(log_entry)
                await db.commit()

        # Notify the owner via Web Push when new learning entries land.
        if learned > 0:
            try:
                from app.services.push import get_push_service

                preview = ", ".join(learned_topics[:3])
                more = (
                    f" and {len(learned_topics) - 3} more"
                    if len(learned_topics) > 3
                    else ""
                )
                await get_push_service().send_to_owner(
                    owner_id=owner_id,
                    title="New learning report",
                    body=f"Your replica learned about {preview}{more}.",
                    db=db,
                    data={"url": "/dashboard/learning"},
                    tag="learning-report",
                )
            except Exception as exc:
                logger.warning("Push notification failed for %s: %s", owner_id, exc)

        return learned

    @staticmethod
    async def review_stale_knowledge(
        owner_id: str, db: AsyncSession
    ) -> StaleKnowledgeResponse:
        """Find knowledge entries older than the configured threshold."""
        threshold_days = settings.learning_stale_knowledge_days
        cutoff = datetime.now(UTC).replace(tzinfo=None) - timedelta(days=threshold_days)

        # Import here to avoid circular dependency
        from app.models.owner import EmotionLog  # noqa: F811 — nearby model

        # Query knowledge entries from AI service via RAG search for stale content
        ai = get_ai_client()
        stale_entries: list[StaleKnowledgeEntry] = []

        try:
            # Use a broad query to get all entries, then filter by date
            all_knowledge = await ai.rag_search(
                owner_id, "everything I know", top_k=100
            )
            results = all_knowledge.get("results", [])

            for r in results:
                created = r.get("created_at", r.get("metadata", {}).get("created_at"))
                if not created:
                    continue
                try:
                    if isinstance(created, str):
                        entry_date = datetime.fromisoformat(created.replace("Z", "+00:00")).replace(tzinfo=None)
                    else:
                        entry_date = created
                    if entry_date < cutoff:
                        age = (datetime.now(UTC).replace(tzinfo=None) - entry_date).days
                        stale_entries.append(StaleKnowledgeEntry(
                            entry_id=r.get("id", r.get("entry_id", "")),
                            content_type=r.get("content_type", "text"),
                            age_days=age,
                            relevance_score=r.get("score"),
                        ))
                except (ValueError, TypeError):
                    pass

            total_entries = len(results)
        except Exception as exc:
            logger.warning("Stale knowledge review failed for %s: %s", owner_id, exc)
            total_entries = 0

        return StaleKnowledgeResponse(
            stale_entries=stale_entries,
            total_entries=total_entries,
            threshold_days=threshold_days,
        )

    @staticmethod
    async def consolidate_knowledge(
        owner_id: str, db: AsyncSession
    ) -> ConsolidationResult:
        """Find groups of similar knowledge entries and merge them.

        Uses vector search to find clusters of similar entries, then asks the
        LLM to consolidate each group into a single, comprehensive entry.
        """
        ai = get_ai_client()
        threshold = settings.learning_consolidation_threshold

        # 1. Get a broad sample of knowledge
        try:
            sample = await ai.rag_search(owner_id, "all topics", top_k=50)
            results = sample.get("results", [])
        except Exception:
            return ConsolidationResult(
                groups_found=0, entries_consolidated=0,
                new_entries_created=0, summary="Failed to retrieve knowledge entries.",
            )

        if len(results) < threshold:
            return ConsolidationResult(
                groups_found=0, entries_consolidated=0,
                new_entries_created=0,
                summary=f"Not enough entries to consolidate (have {len(results)}, need {threshold}).",
            )

        # 2. Ask LLM to identify clusters
        texts = []
        for i, r in enumerate(results[:30]):
            text = r.get("text", r.get("content", ""))[:150]
            if text:
                texts.append(f"{i}: {text}")

        cluster_prompt = (
            "Below are numbered knowledge entries. Identify groups of entries "
            "that cover the same or very similar topic and could be merged.\n\n"
            + "\n".join(texts)
            + "\n\nRespond with a JSON array of groups. Each group is an object with:\n"
            '- "topic": merged topic name\n'
            '- "indices": list of entry numbers to merge\n'
            "Only include groups with 2+ entries. Respond ONLY with JSON array."
        )

        try:
            gen = await ai.generate(cluster_prompt, temperature=0.2, max_tokens=512)
            raw = gen.get("text", gen.get("response", "[]"))
            import json
            groups = json.loads(raw)
        except Exception:
            return ConsolidationResult(
                groups_found=0, entries_consolidated=0,
                new_entries_created=0, summary="Could not identify entry clusters.",
            )

        # 3. Consolidate each group
        groups_found = len(groups)
        entries_consolidated = 0
        new_entries_created = 0

        for group in groups[:5]:  # limit to 5 groups per run
            indices = group.get("indices", [])
            topic = group.get("topic", "Unknown")
            group_texts = []

            for idx in indices:
                if 0 <= idx < len(results):
                    text = results[idx].get("text", results[idx].get("content", ""))
                    if text:
                        group_texts.append(text)

            if len(group_texts) < 2:
                continue

            # Merge via LLM
            merge_prompt = (
                f"Consolidate these {len(group_texts)} knowledge entries about '{topic}' "
                "into a single, comprehensive entry. Remove duplicates, keep all unique facts.\n\n"
                + "\n---\n".join(group_texts[:10])
            )

            try:
                gen = await ai.generate(merge_prompt, temperature=0.3, max_tokens=768)
                merged = gen.get("text", gen.get("response", ""))
                if merged.strip():
                    await ai.ingest_text(
                        owner_id,
                        text=f"[Consolidated: {topic}] {merged}",
                        language="en",
                    )
                    new_entries_created += 1
                    entries_consolidated += len(group_texts)
            except Exception as exc:
                logger.warning("Consolidation failed for group '%s': %s", topic, exc)

        summary = (
            f"Found {groups_found} groups of similar entries. "
            f"Consolidated {entries_consolidated} entries into {new_entries_created} new entries."
        )

        return ConsolidationResult(
            groups_found=groups_found,
            entries_consolidated=entries_consolidated,
            new_entries_created=new_entries_created,
            summary=summary,
        )

    @staticmethod
    async def get_learning_report(
        owner_id: str, db: AsyncSession, page: int = 1, page_size: int = 20
    ) -> tuple[list[LearningLog], int]:
        """Fetch paginated learning logs for the owner."""
        # Count
        count_row = await db.execute(
            select(sa_func.count())
            .select_from(LearningLog)
            .where(LearningLog.owner_id == owner_id)
        )
        total = count_row.scalar_one()

        # Fetch
        offset = (page - 1) * page_size
        rows = await db.execute(
            select(LearningLog)
            .where(LearningLog.owner_id == owner_id)
            .order_by(LearningLog.created_at.desc())
            .offset(offset)
            .limit(page_size)
        )
        logs = list(rows.scalars().all())

        return logs, total

    @staticmethod
    async def get_preferences(owner_id: str, db: AsyncSession) -> LearningConfig | None:
        """Get learning preferences for the owner."""
        row = await db.execute(
            select(LearningConfig).where(LearningConfig.owner_id == owner_id)
        )
        return row.scalar_one_or_none()

    @staticmethod
    async def upsert_preferences(
        owner_id: str,
        db: AsyncSession,
        *,
        enabled: bool | None = None,
        auto_topics: list[str] | None = None,
        ignore_topics: list[str] | None = None,
        depth: str | None = None,
        schedule_hour_utc: int | None = None,
        max_daily_web_searches: int | None = None,
        use_external_llm: bool | None = None,
    ) -> LearningConfig:
        """Create or update learning preferences."""
        row = await db.execute(
            select(LearningConfig).where(LearningConfig.owner_id == owner_id)
        )
        config = row.scalar_one_or_none()

        if config is None:
            config = LearningConfig(
                id=generate_cuid(),
                owner_id=owner_id,
            )
            db.add(config)

        if enabled is not None:
            config.enabled = enabled
        if auto_topics is not None:
            config.auto_topics = auto_topics
        if ignore_topics is not None:
            config.ignore_topics = ignore_topics
        if depth is not None:
            config.depth = depth
        if schedule_hour_utc is not None:
            config.schedule_hour_utc = schedule_hour_utc
        if max_daily_web_searches is not None:
            config.max_daily_web_searches = max_daily_web_searches
        if use_external_llm is not None:
            config.use_external_llm = use_external_llm

        await db.commit()
        await db.refresh(config)
        return config
