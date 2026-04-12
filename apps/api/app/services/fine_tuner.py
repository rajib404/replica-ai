"""Fine-tuning service: training data generation, model versioning, evaluation, rollback.

CPU-only environments cannot run real LoRA fine-tuning, so this service implements
"pseudo fine-tuning" via Ollama Modelfile customisation: a large system prompt
constructed from the owner's training pairs is baked into a new derived model.
The same training data path can be reused later for true LoRA fine-tuning when
GPU resources are available.
"""

import asyncio
import json
import logging
import os
import re
from datetime import UTC, datetime
from difflib import SequenceMatcher

from cuid2 import cuid_wrapper
from sqlalchemy import func as sa_func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.ai_client import get_ai_client
from app.core.config import settings
from app.models.chat import ConversationThread, Message, MessageRole, ParticipantType
from app.models.finetune import (
    EvaluationMetric,
    EvaluationResult,
    EvaluationSample,
    TrainingDataSourceStats,
    TrainingDataStats,
    TrainingPair,
)
from app.models.owner import (
    FineTuneConfig,
    ModelVersion,
    Owner,
    PersonalityProfile,
)

logger = logging.getLogger(__name__)
generate_cuid = cuid_wrapper()


# ─── Helpers ─────────────────────────────────────────────


def _utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _model_name_for(owner_id: str, version: int) -> str:
    return f"replica-{owner_id[:12]}-v{version}"


def _is_meaningful(text: str | None) -> bool:
    if not text:
        return False
    cleaned = text.strip()
    return len(cleaned) >= settings.finetune_min_owner_message_chars


def _looks_like_question(text: str) -> bool:
    return text.strip().endswith("?") or any(
        text.lower().startswith(w) for w in ("what", "who", "when", "where", "why", "how", "is ", "are ", "do ", "did ", "can ", "could ")
    )


def _ensure_data_dir() -> str:
    path = settings.finetune_data_dir
    os.makedirs(path, exist_ok=True)
    return path


# ─── TrainingDataGenerator ──────────────────────────────


class TrainingDataGenerator:
    """Build supervised training pairs from owner conversations, knowledge, and personality."""

    @staticmethod
    async def generate_training_pairs(
        owner_id: str, db: AsyncSession
    ) -> tuple[list[TrainingPair], TrainingDataSourceStats]:
        """Generate (input, output) pairs for fine-tuning the owner's replica.

        Sources:
        1. Conversations — assistant turn paired with the preceding user turn.
           When the *owner* is the user (i.e. the owner is teaching the AI),
           the owner's reply becomes the desired *output*.
        2. Knowledge entries — converted to Q&A style pairs.
        3. Personality — phrases-and-idioms become style-matching examples.
        """
        pairs: list[TrainingPair] = []
        stats = TrainingDataSourceStats()
        max_pairs = settings.finetune_max_pairs

        # 1. Conversations: pair owner's user-turn → following assistant turn,
        #    and pair user-turn (any) → owner-authored response (when present).
        conv_pairs, filtered = await TrainingDataGenerator._pairs_from_conversations(
            owner_id, db, remaining=max_pairs - len(pairs)
        )
        pairs.extend(conv_pairs)
        stats.conversation_pairs = len(conv_pairs)
        stats.filtered_out += filtered

        # 2. Knowledge → Q&A
        if len(pairs) < max_pairs:
            kn_pairs = await TrainingDataGenerator._pairs_from_knowledge(
                owner_id, db, remaining=max_pairs - len(pairs)
            )
            pairs.extend(kn_pairs)
            stats.knowledge_pairs = len(kn_pairs)

        # 3. Personality → style examples
        if len(pairs) < max_pairs:
            pers_pairs = await TrainingDataGenerator._pairs_from_personality(
                owner_id, db, remaining=max_pairs - len(pairs)
            )
            pairs.extend(pers_pairs)
            stats.personality_pairs = len(pers_pairs)

        return pairs, stats

    @staticmethod
    async def _pairs_from_conversations(
        owner_id: str, db: AsyncSession, remaining: int
    ) -> tuple[list[TrainingPair], int]:
        """Extract conversational training pairs ordered chronologically."""
        if remaining <= 0:
            return [], 0

        result = await db.execute(
            select(Message, ConversationThread)
            .join(ConversationThread, Message.thread_id == ConversationThread.id)
            .where(
                ConversationThread.owner_id == owner_id,
                ConversationThread.participant_type == ParticipantType.owner,
                Message.content_text.isnot(None),
            )
            .order_by(ConversationThread.id, Message.created_at.asc())
        )
        rows = list(result.all())

        pairs: list[TrainingPair] = []
        filtered_out = 0
        prev_user_text: str | None = None
        current_thread: str | None = None

        for msg, thread in rows:
            if thread.id != current_thread:
                current_thread = thread.id
                prev_user_text = None

            text = (msg.content_text or "").strip()
            if not _is_meaningful(text):
                filtered_out += 1
                prev_user_text = None
                continue

            if msg.role == MessageRole.user:
                prev_user_text = text
            elif msg.role == MessageRole.assistant and prev_user_text:
                # We treat the owner-conversation assistant turn as a desired
                # output style example, paired with the preceding owner prompt.
                pairs.append(
                    TrainingPair(
                        input=prev_user_text,
                        output=text,
                        source="conversation",
                    )
                )
                prev_user_text = None

                if len(pairs) >= remaining:
                    break

        return pairs, filtered_out

    @staticmethod
    async def _pairs_from_knowledge(
        owner_id: str, db: AsyncSession, remaining: int
    ) -> list[TrainingPair]:
        """Convert knowledge entries into Q&A pairs via local LLM."""
        if remaining <= 0:
            return []

        from app.models.knowledge import KnowledgeEntry as KEModel  # local import

        result = await db.execute(
            select(KEModel)
            .where(KEModel.owner_id == owner_id)
            .order_by(KEModel.created_at.desc())
            .limit(min(remaining, 200))
        )
        entries = list(result.scalars().all())
        if not entries:
            return []

        ai = get_ai_client()
        pairs: list[TrainingPair] = []

        for entry in entries:
            text = (entry.english_translation or "").strip()
            if not text or len(text) < 60:
                continue

            prompt = (
                "Given the following statement about a person, write ONE concise "
                "question someone might ask whose factual answer is contained in "
                "the statement, then on a new line write the answer in the first "
                "person as if the person is responding.\n\n"
                f"Statement: {text[:600]}\n\n"
                "Format your output exactly as:\n"
                "Q: <question>\n"
                "A: <answer>\n"
            )

            try:
                gen = await ai.generate(prompt, temperature=0.4, max_tokens=256)
                raw = gen.get("text", gen.get("response", ""))
            except Exception as exc:
                logger.warning("Knowledge Q&A generation failed: %s", exc)
                continue

            q_match = re.search(r"Q:\s*(.+)", raw)
            a_match = re.search(r"A:\s*(.+)", raw, re.DOTALL)
            if not q_match or not a_match:
                continue

            question = q_match.group(1).strip()
            answer = a_match.group(1).strip()
            if len(question) < 5 or len(answer) < 5:
                continue

            pairs.append(
                TrainingPair(input=question, output=answer, source="knowledge")
            )

            if len(pairs) >= remaining:
                break

        return pairs

    @staticmethod
    async def _pairs_from_personality(
        owner_id: str, db: AsyncSession, remaining: int
    ) -> list[TrainingPair]:
        """Generate style-matching examples from learned personality phrases."""
        if remaining <= 0:
            return []

        result = await db.execute(
            select(PersonalityProfile).where(PersonalityProfile.owner_id == owner_id)
        )
        profile = result.scalar_one_or_none()
        if not profile:
            return []

        phrases = profile.phrases_and_idioms or []
        traits = profile.traits or {}

        pairs: list[TrainingPair] = []
        # Each phrase becomes a style demonstration
        for phrase in phrases[:remaining]:
            if not isinstance(phrase, str) or len(phrase) < 4:
                continue
            pairs.append(
                TrainingPair(
                    input=f"Say something using your typical phrasing.",
                    output=phrase.strip(),
                    source="personality",
                )
            )

        # Add a single trait-summary example if room remains
        if traits and len(pairs) < remaining:
            trait_lines = []
            traits_iter = traits if isinstance(traits, list) else traits.get("items", [])
            for t in traits_iter[:5]:
                if isinstance(t, dict):
                    name = t.get("name", "")
                    value = t.get("value", "")
                    if name and value:
                        trait_lines.append(f"- {name}: {value}")
            if trait_lines:
                pairs.append(
                    TrainingPair(
                        input="Describe yourself in a few sentences.",
                        output="I'd describe myself like this:\n" + "\n".join(trait_lines),
                        source="personality",
                    )
                )

        return pairs

    @staticmethod
    def format_for_ollama(
        pairs: list[TrainingPair], owner_name: str, language: str, output_path: str
    ) -> str:
        """Write training pairs to a JSONL file suitable for downstream tools.

        The format mirrors the OpenAI / HuggingFace SFT convention so the same
        file can be reused for true LoRA fine-tuning later. A `system` message
        is prepended to every example so the model learns the persona.
        """
        os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)

        system_prompt = (
            f"You are the personal AI replica of {owner_name}. "
            f"You speak {language}. You are warm, supportive, and reflect the owner's "
            f"personality, values, and style of speaking learned from past conversations."
        )

        with open(output_path, "w", encoding="utf-8") as f:
            for pair in pairs:
                example = {
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": pair.input},
                        {"role": "assistant", "content": pair.output},
                    ],
                    "source": pair.source,
                }
                f.write(json.dumps(example, ensure_ascii=False) + "\n")

        return output_path


# ─── FineTuner ──────────────────────────────────────────


class FineTuner:
    """Lifecycle for owner-specific model versions."""

    @staticmethod
    async def get_config(owner_id: str, db: AsyncSession) -> FineTuneConfig:
        """Fetch or lazily create the per-owner fine-tune config."""
        row = await db.execute(
            select(FineTuneConfig).where(FineTuneConfig.owner_id == owner_id)
        )
        config = row.scalar_one_or_none()
        if config:
            return config

        config = FineTuneConfig(
            id=generate_cuid(),
            owner_id=owner_id,
            base_model=settings.finetune_default_base_model,
            trigger_message_count=settings.finetune_auto_trigger_messages,
        )
        db.add(config)
        await db.commit()
        await db.refresh(config)
        return config

    @staticmethod
    async def upsert_config(
        owner_id: str,
        db: AsyncSession,
        *,
        auto_approve: bool | None = None,
        auto_trigger_enabled: bool | None = None,
        base_model: str | None = None,
        trigger_message_count: int | None = None,
    ) -> FineTuneConfig:
        config = await FineTuner.get_config(owner_id, db)
        if auto_approve is not None:
            config.auto_approve = auto_approve
        if auto_trigger_enabled is not None:
            config.auto_trigger_enabled = auto_trigger_enabled
        if base_model is not None:
            config.base_model = base_model
        if trigger_message_count is not None:
            config.trigger_message_count = trigger_message_count
        await db.commit()
        await db.refresh(config)
        return config

    @staticmethod
    async def count_owner_messages(owner_id: str, db: AsyncSession) -> int:
        """Total number of meaningful owner-authored user messages."""
        row = await db.execute(
            select(sa_func.count(Message.id))
            .join(ConversationThread, Message.thread_id == ConversationThread.id)
            .where(
                ConversationThread.owner_id == owner_id,
                ConversationThread.participant_type == ParticipantType.owner,
                Message.role == MessageRole.user,
                Message.content_text.isnot(None),
            )
        )
        return int(row.scalar() or 0)

    # -- Training data generation --

    @staticmethod
    async def generate_training_data(
        owner_id: str, db: AsyncSession, save_to_disk: bool = True
    ) -> tuple[TrainingDataStats, str | None, list[TrainingPair]]:
        """Build training pairs and (optionally) write the JSONL file to disk."""
        owner_row = await db.execute(select(Owner).where(Owner.id == owner_id))
        owner = owner_row.scalar_one_or_none()
        if owner is None:
            raise ValueError(f"Owner {owner_id} not found")

        pairs, source_stats = await TrainingDataGenerator.generate_training_pairs(
            owner_id, db
        )

        total = len(pairs)
        holdout = max(1, int(total * settings.finetune_eval_holdout_ratio)) if total else 0

        path: str | None = None
        if save_to_disk and pairs:
            data_dir = _ensure_data_dir()
            path = os.path.join(data_dir, f"{owner_id}_training.jsonl")
            TrainingDataGenerator.format_for_ollama(
                pairs, owner.name, owner.preferred_language, path
            )

        stats = TrainingDataStats(
            owner_id=owner_id,
            total_pairs=total,
            sources=source_stats,
            sufficient=total >= settings.finetune_min_pairs,
            minimum_recommended=settings.finetune_min_pairs,
            holdout_size=holdout,
            sample_pairs=pairs[:5],
            generated_at=_utcnow().isoformat(),
        )

        return stats, path, pairs

    # -- Versioning helpers --

    @staticmethod
    async def _next_version_number(owner_id: str, db: AsyncSession) -> int:
        row = await db.execute(
            select(sa_func.max(ModelVersion.version)).where(
                ModelVersion.owner_id == owner_id
            )
        )
        current = row.scalar() or 0
        return int(current) + 1

    @staticmethod
    async def list_versions(owner_id: str, db: AsyncSession) -> list[ModelVersion]:
        rows = await db.execute(
            select(ModelVersion)
            .where(ModelVersion.owner_id == owner_id)
            .order_by(ModelVersion.version.desc())
        )
        return list(rows.scalars().all())

    @staticmethod
    async def get_active_version(
        owner_id: str, db: AsyncSession
    ) -> ModelVersion | None:
        row = await db.execute(
            select(ModelVersion)
            .where(
                ModelVersion.owner_id == owner_id,
                ModelVersion.is_active.is_(True),
            )
            .order_by(ModelVersion.version.desc())
            .limit(1)
        )
        return row.scalar_one_or_none()

    @staticmethod
    async def get_version(
        owner_id: str, version: int, db: AsyncSession
    ) -> ModelVersion | None:
        row = await db.execute(
            select(ModelVersion).where(
                ModelVersion.owner_id == owner_id,
                ModelVersion.version == version,
            )
        )
        return row.scalar_one_or_none()

    @staticmethod
    async def get_running_job(
        owner_id: str, db: AsyncSession
    ) -> ModelVersion | None:
        row = await db.execute(
            select(ModelVersion)
            .where(
                ModelVersion.owner_id == owner_id,
                ModelVersion.status.in_(("pending", "preparing", "training", "evaluating")),
            )
            .order_by(ModelVersion.started_at.desc())
            .limit(1)
        )
        return row.scalar_one_or_none()

    @staticmethod
    async def get_last_completed(
        owner_id: str, db: AsyncSession
    ) -> ModelVersion | None:
        row = await db.execute(
            select(ModelVersion)
            .where(
                ModelVersion.owner_id == owner_id,
                ModelVersion.status == "completed",
            )
            .order_by(ModelVersion.completed_at.desc())
            .limit(1)
        )
        return row.scalar_one_or_none()

    # -- Model creation --

    @staticmethod
    def _build_pseudo_finetune_prompt(
        owner_name: str, language: str, pairs: list[TrainingPair]
    ) -> str:
        """Bake a sample of pairs into a long system prompt for CPU-only mode."""
        examples = []
        # Sample evenly from each source so personality/knowledge aren't drowned out
        sources = ("personality", "knowledge", "conversation")
        per_source = 12
        for src in sources:
            chosen = [p for p in pairs if p.source == src][:per_source]
            for p in chosen:
                examples.append(f'User: "{p.input}"\nReply: "{p.output}"')

        example_block = "\n\n".join(examples)
        return (
            f"You are the personal AI replica of {owner_name}, speaking {language}. "
            "Answer in the owner's voice — match their tone, vocabulary, and cadence. "
            "When asked factual questions, answer in the first person from the owner's perspective. "
            "Keep responses warm, supportive, and consistent with the examples below.\n\n"
            "Reference style examples:\n\n"
            f"{example_block}"
        )

    @staticmethod
    async def create_fine_tuned_model(
        owner_id: str,
        db: AsyncSession,
        *,
        base_model: str | None = None,
        training_data_path: str | None = None,
        pairs: list[TrainingPair] | None = None,
    ) -> ModelVersion:
        """Create a new owner model version using Ollama Modelfile customisation.

        The function:
        - allocates the next version number,
        - persists a `ModelVersion` row with status='preparing',
        - calls the AI service to create the customised Ollama model,
        - marks the row 'completed' (or 'failed') on return,
        - rotates inactive versions older than `finetune_versions_to_keep`.
        """
        owner_row = await db.execute(select(Owner).where(Owner.id == owner_id))
        owner = owner_row.scalar_one_or_none()
        if owner is None:
            raise ValueError(f"Owner {owner_id} not found")

        if pairs is None:
            _, training_data_path, pairs = await FineTuner.generate_training_data(
                owner_id, db, save_to_disk=True
            )

        config = await FineTuner.get_config(owner_id, db)
        chosen_base = base_model or config.base_model

        version_number = await FineTuner._next_version_number(owner_id, db)
        model_name = _model_name_for(owner_id, version_number)

        version = ModelVersion(
            id=generate_cuid(),
            owner_id=owner_id,
            version=version_number,
            model_name=model_name,
            base_model=chosen_base,
            training_data_path=training_data_path,
            training_pair_count=len(pairs),
            status="preparing",
            is_active=False,
            progress={"stage": "preparing"},
        )
        db.add(version)
        await db.commit()
        await db.refresh(version)

        # Build the pseudo-fine-tune prompt and call the AI service.
        try:
            ai = get_ai_client()
            additions = FineTuner._build_pseudo_finetune_prompt(
                owner.name, owner.preferred_language, pairs
            )

            version.status = "training"
            version.progress = {"stage": "creating_model", "pairs": len(pairs)}
            await db.commit()

            await ai.create_model(
                owner_id=owner_id,
                owner_name=owner.name,
                language=owner.preferred_language,
                additions=additions,
                base_model=chosen_base,
            )

            version.status = "completed"
            version.completed_at = _utcnow()
            version.is_active = True
            version.progress = {"stage": "done", "pairs": len(pairs)}
            await db.commit()

            # Deactivate prior versions
            prior = await db.execute(
                select(ModelVersion).where(
                    ModelVersion.owner_id == owner_id,
                    ModelVersion.id != version.id,
                    ModelVersion.is_active.is_(True),
                )
            )
            for old in prior.scalars().all():
                old.is_active = False
            await db.commit()

            await FineTuner._prune_old_versions(owner_id, db)

        except Exception as exc:
            logger.exception("Fine-tune failed for owner %s", owner_id)
            version.status = "failed"
            version.error_message = str(exc)[:1000]
            version.completed_at = _utcnow()
            await db.commit()

        await db.refresh(version)
        return version

    @staticmethod
    async def _prune_old_versions(owner_id: str, db: AsyncSession) -> None:
        """Keep only the last N completed versions, delete the rest."""
        keep = settings.finetune_versions_to_keep
        rows = await db.execute(
            select(ModelVersion)
            .where(
                ModelVersion.owner_id == owner_id,
                ModelVersion.status == "completed",
            )
            .order_by(ModelVersion.version.desc())
        )
        completed = list(rows.scalars().all())
        if len(completed) <= keep:
            return

        for stale in completed[keep:]:
            try:
                if stale.training_data_path and os.path.exists(stale.training_data_path):
                    # Only delete the file if no newer version still references it
                    pass  # files are per-owner, kept for re-runs
                await db.delete(stale)
            except Exception:
                logger.exception("Failed to prune model version %s", stale.id)
        await db.commit()

    # -- Evaluation --

    @staticmethod
    async def evaluate_model(
        owner_id: str,
        db: AsyncSession,
        *,
        version: int | None = None,
    ) -> EvaluationResult:
        """Run held-out evaluation comparing the fine-tuned model vs base model."""
        if version is None:
            active = await FineTuner.get_active_version(owner_id, db)
            if not active:
                raise ValueError("No active model version to evaluate")
            target = active
        else:
            target = await FineTuner.get_version(owner_id, version, db)
            if not target:
                raise ValueError(f"Model version {version} not found")

        # Re-load training pairs (cheap with current setup) and slice the holdout
        _, _, pairs = await FineTuner.generate_training_data(
            owner_id, db, save_to_disk=False
        )
        if not pairs:
            raise ValueError("No training data available for evaluation")

        holdout_size = max(1, int(len(pairs) * settings.finetune_eval_holdout_ratio))
        holdout = pairs[-holdout_size:]

        ai = get_ai_client()
        finetuned_name = target.model_name
        base_name = target.base_model

        sims_finetuned: list[float] = []
        sims_base: list[float] = []
        samples: list[EvaluationSample] = []

        for pair in holdout[:20]:  # cap LLM calls
            try:
                ft_resp = await ai.generate(
                    pair.input, model=finetuned_name, temperature=0.3, max_tokens=256
                )
                ft_text = ft_resp.get("text", ft_resp.get("response", ""))
            except Exception:
                ft_text = ""

            try:
                base_resp = await ai.generate(
                    pair.input, model=base_name, temperature=0.3, max_tokens=256
                )
                base_text = base_resp.get("text", base_resp.get("response", ""))
            except Exception:
                base_text = ""

            ft_sim = SequenceMatcher(None, pair.output, ft_text).ratio()
            base_sim = SequenceMatcher(None, pair.output, base_text).ratio()
            sims_finetuned.append(ft_sim)
            sims_base.append(base_sim)

            samples.append(
                EvaluationSample(
                    input=pair.input,
                    expected=pair.output,
                    base_response=base_text[:500],
                    finetuned_response=ft_text[:500],
                    similarity_score=ft_sim,
                )
            )

        def _mean(xs: list[float]) -> float:
            return sum(xs) / len(xs) if xs else 0.0

        ft_avg = _mean(sims_finetuned)
        base_avg = _mean(sims_base)
        improvement = ft_avg - base_avg

        metrics = [
            EvaluationMetric(
                name="style_similarity",
                value=round(ft_avg, 4),
                description="Avg sequence similarity to owner's actual replies (fine-tuned).",
            ),
            EvaluationMetric(
                name="improvement_over_base",
                value=round(improvement, 4),
                description="Difference in similarity vs the base model.",
            ),
            EvaluationMetric(
                name="samples_evaluated",
                value=float(len(samples)),
                description="Number of held-out samples scored.",
            ),
        ]
        base_metrics = [
            EvaluationMetric(
                name="style_similarity",
                value=round(base_avg, 4),
                description="Same metric for the unmodified base model.",
            )
        ]

        # Persist metrics on the version row
        target.metrics = {
            "style_similarity_finetuned": round(ft_avg, 4),
            "style_similarity_base": round(base_avg, 4),
            "improvement_over_base": round(improvement, 4),
            "evaluated_at": _utcnow().isoformat(),
            "samples": len(samples),
        }
        await db.commit()

        summary = (
            f"Fine-tuned model scored {ft_avg:.3f} similarity vs {base_avg:.3f} for "
            f"the base model across {len(samples)} held-out samples "
            f"(improvement: {improvement:+.3f})."
        )

        return EvaluationResult(
            version_id=target.id,
            version=target.version,
            sample_count=len(samples),
            metrics=metrics,
            base_metrics=base_metrics,
            samples=samples[:5],
            summary=summary,
        )

    # -- Rollback --

    @staticmethod
    async def rollback(
        owner_id: str, db: AsyncSession, *, version: int
    ) -> tuple[bool, int | None, str]:
        """Restore a previous model version as active.

        We do not delete the currently-active model — it remains in history so
        the rollback itself can be undone.
        """
        target = await FineTuner.get_version(owner_id, version, db)
        if not target:
            return False, None, f"Version {version} not found"
        if target.status != "completed":
            return False, None, f"Version {version} is not in a completed state"

        # Deactivate all then reactivate the target
        rows = await db.execute(
            select(ModelVersion).where(ModelVersion.owner_id == owner_id)
        )
        for v in rows.scalars().all():
            v.is_active = v.id == target.id
            if v.id == target.id and v.status != "rolled_back":
                v.status = "completed"
        await db.commit()

        return True, target.version, f"Rolled back to version {target.version}"

    # -- Auto-trigger --

    @staticmethod
    async def maybe_auto_trigger(owner_id: str, db: AsyncSession) -> bool:
        """Check the owner's message count and start fine-tuning if eligible."""
        config = await FineTuner.get_config(owner_id, db)
        if not config.auto_trigger_enabled:
            return False

        # Don't double-up while a job is in flight
        running = await FineTuner.get_running_job(owner_id, db)
        if running:
            return False

        total = await FineTuner.count_owner_messages(owner_id, db)
        delta = total - config.last_trigger_message_total
        if delta < config.trigger_message_count:
            return False

        if not config.auto_approve:
            # Auto-approval is off — surface that we *would* trigger but require
            # the owner's manual confirmation. We update the counter so we don't
            # nag on every message.
            config.last_trigger_message_total = total
            await db.commit()
            return False

        config.last_trigger_message_total = total
        await db.commit()

        # Run fine-tuning in the background so we don't block whatever called us
        asyncio.create_task(FineTuner._background_fine_tune(owner_id))
        return True

    @staticmethod
    async def _background_fine_tune(owner_id: str) -> None:
        """Worker entry-point for asyncio.create_task background runs."""
        from app.core.database import async_session

        try:
            async with async_session() as db:
                await FineTuner.create_fine_tuned_model(owner_id, db)
        except Exception:
            logger.exception("Background fine-tune failed for owner %s", owner_id)
