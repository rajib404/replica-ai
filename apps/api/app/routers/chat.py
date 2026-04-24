import json
import logging
import uuid

import redis.asyncio as aioredis
from fastapi import APIRouter, Depends, HTTPException, Request, WebSocket, WebSocketDisconnect, status
from jose import JWTError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.ai_client import AIServiceClient, get_ai_client
from app.core.auth_guard import AuthContext, require_auth
from app.core.database import get_db
from app.core.redis import get_redis
from app.core.security import decode_token
from app.models.chat import (
    ChatMessageRequest,
    ChatMessageResponse,
    MessageHistoryResponse,
    MessageResponse,
    MessageRole,
    ParticipantType,
    ThreadListResponse,
    ThreadResponse,
    WSChatMessage,
    WSError,
    WSLearning,
    WSResponseDone,
    WSResponseToken,
)
from app.models.identity import (
    ChallengeLevel,
    ChallengeResponse,
    WSChallenge,
    WSChallengeResult,
    WSLockout,
)
from app.models.knowledge import ContentType, KnowledgeEntry
from app.models.owner import Owner
from app.services.conversation import ConversationManager
from app.services.identity_guard import IdentityGuard, get_identity_guard
from app.services.multilingual import LanguageEngine
from app.services.personality import EmotionalSupport, PersonalityTracker

logger = logging.getLogger(__name__)

router = APIRouter(tags=["chat"])


# -- Dependency factories --


def _get_conversation_manager() -> ConversationManager:
    return ConversationManager()


def _get_identity_guard_dep() -> IdentityGuard:
    return get_identity_guard()


# -- Helpers --


async def _resolve_owner(owner_id: str, db: AsyncSession) -> Owner | None:
    result = await db.execute(select(Owner).where(Owner.id == owner_id))
    return result.scalar_one_or_none()


def _authenticate_token(token: str) -> dict:
    """Validate a JWT and return the payload."""
    try:
        payload = decode_token(token)
    except JWTError as e:
        raise ValueError(f"Invalid token: {e}") from e
    if payload.get("type") != "access":
        raise ValueError("Token type must be 'access'")
    return payload


async def _ingest_owner_text(
    owner_id: str,
    text: str,
    ai: AIServiceClient,
    db: AsyncSession,
    r: aioredis.Redis | None = None,
) -> bool:
    """Ingest owner message as knowledge via AI service.

    Uses LanguageEngine for detection and pre-translation (cached in Redis)
    before forwarding to the AI service for embedding.
    """
    try:
        # Detect language via LanguageEngine
        detection = await LanguageEngine.detect_language(text, ai)
        lang = detection["language_code"]

        # Pre-translate if non-English using LanguageEngine (with Redis cache)
        english_translation: str | None = None
        if lang != "en":
            tr = await LanguageEngine.translate(text, lang, "en", r=r, ai=ai)
            english_translation = tr["translated_text"]

        result = await ai.ingest_text(
            owner_id=owner_id,
            text=text,
            language=lang,
            english_translation=english_translation,
        )
        # Persist the entry to DB
        entry = KnowledgeEntry(
            id=result["entry_id"],
            owner_id=owner_id,
            content_type=ContentType.text,
            original_language=result.get("language"),
            english_translation=result.get("english_translation"),
            embedding_id=result.get("embedding_id"),
            metadata_=result.get("metadata"),
        )
        db.add(entry)
        await db.flush()
        return True
    except Exception:
        logger.exception("Knowledge ingestion failed for owner message")
        return False


async def _process_message(
    owner_id: str,
    participant_type: ParticipantType,
    participant_name: str,
    text: str,
    thread_id: str | None,
    db: AsyncSession,
    r: aioredis.Redis,
    ai: AIServiceClient,
    conv: ConversationManager,
) -> tuple[str, str, str, list[dict], bool]:
    """Core message processing shared by REST and WebSocket.

    Returns (response_text, message_id, thread_id, sources, is_learning).
    """
    thread = await conv.get_or_create_thread(
        owner_id=owner_id,
        participant_type=participant_type,
        participant_name=participant_name,
        db=db,
        thread_id=thread_id,
    )

    # Detect language of the incoming message
    detection = await LanguageEngine.detect_language(text, ai)
    detected_lang = detection["language_code"]

    # Save user message with detected language
    user_msg = await conv.save_message(
        thread_id=thread.id,
        role=MessageRole.user,
        content=text,
        language=detected_lang,
        db=db,
    )

    # If owner is speaking, also ingest as knowledge
    is_learning = False
    if participant_type == ParticipantType.owner and len(text) > 20:
        is_learning = await _ingest_owner_text(owner_id, text, ai, db, r)

    # Load conversation context
    context = await conv.load_context(thread.id, db, r)

    # Detect emotion (best-effort, non-blocking for flow)
    emotion_detection = await EmotionalSupport.detect_emotion(text, ai)
    await EmotionalSupport.log_emotion(owner_id, emotion_detection, db, message_id=user_msg.id)

    # Build system prompt with language awareness
    owner = await _resolve_owner(owner_id, db)
    owner_name = owner.name if owner else "the owner"
    owner_lang = owner.preferred_language if owner else "en"
    base_prompt = conv.build_system_prompt(
        owner_name=owner_name,
        language=owner_lang,
        participant_type=participant_type,
        participant_name=participant_name,
    )
    # Append language-switching instructions if user language differs
    lang_prompt = LanguageEngine.build_language_system_prompt(detected_lang)

    # Append personality prompt (learned traits)
    personality_prompt = ""
    profile = await PersonalityTracker.get_profile(owner_id, db)
    if profile and profile.messages_analyzed > 0:
        if participant_type == ParticipantType.family_member:
            # Legacy mode: family members experience the owner's personality
            personality_prompt = PersonalityTracker.get_personality_prompt(profile)
        else:
            # Owner mode: use personality to stay consistent
            personality_prompt = PersonalityTracker.get_personality_prompt(profile)

    # Append emotional support prompt
    emotion_prompt = EmotionalSupport.get_support_prompt(
        emotion_detection["emotion"], emotion_detection["intensity"]
    )

    system_prompt = base_prompt
    if lang_prompt:
        system_prompt += f"\n\n{lang_prompt}"
    if personality_prompt:
        system_prompt += f"\n\n{personality_prompt}"
    if emotion_prompt:
        system_prompt += f"\n\n{emotion_prompt}"

    # Call AI service RAG generate (non-streaming)
    rag_result = await ai.rag_generate(
        owner_id=owner_id,
        message=text,
        conversation_history=context,
        system_prompt=system_prompt,
    )

    response_text = rag_result.get("response", "")
    sources = rag_result.get("sources", [])

    # Save assistant response
    assistant_msg = await conv.save_message(
        thread_id=thread.id,
        role=MessageRole.assistant,
        content=response_text,
        db=db,
    )

    await db.commit()

    # Trigger summarization check (best-effort)
    try:
        await conv.maybe_summarize(thread.id, db, r, ai)
    except Exception:
        logger.exception("Summarization check failed")

    # Trigger personality analysis if threshold reached (best-effort)
    if participant_type == ParticipantType.owner:
        try:
            if await PersonalityTracker.should_analyze(owner_id, db):
                await PersonalityTracker.analyze_message_batch(owner_id, db, ai)
                await db.commit()
        except Exception:
            logger.exception("Personality analysis check failed")

        # Auto fine-tune trigger check (best-effort, never blocks chat)
        try:
            from app.services.fine_tuner import FineTuner

            await FineTuner.maybe_auto_trigger(owner_id, db)
        except Exception:
            logger.exception("Fine-tune auto-trigger check failed")

    return response_text, assistant_msg.id, thread.id, sources, is_learning


# -- REST endpoint --


@router.post("/api/chat/message", response_model=ChatMessageResponse)
async def send_message(
    body: ChatMessageRequest,
    request: Request,
    auth: AuthContext = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
    r: aioredis.Redis = Depends(get_redis),
    ai: AIServiceClient = Depends(get_ai_client),
    conv: ConversationManager = Depends(_get_conversation_manager),
    guard: IdentityGuard = Depends(_get_identity_guard_dep),
) -> ChatMessageResponse:
    """Send a chat message and get a full (non-streaming) response."""
    participant_type = (
        ParticipantType.owner if auth.role == "owner" else ParticipantType.family_member
    )
    participant_name = auth.role

    # Identity guard check
    client_ip = request.client.host if request.client else None
    guard_result = await guard.check(
        owner_id=auth.subject_id,
        message=body.message,
        role=auth.role,
        db=db,
        r=r,
        client_ip=client_ip,
    )

    if guard_result.challenge_level == ChallengeLevel.lockout:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Session locked due to suspicious activity. Please re-authenticate.",
        )

    if guard_result.challenge_level in (ChallengeLevel.soft, ChallengeLevel.hard):
        challenge = guard_result.challenge
        raise HTTPException(
            status_code=428,
            detail={
                "challenge_required": True,
                "challenge_id": challenge.challenge_id if challenge else "",
                "challenge_type": guard_result.challenge_level.value,
                "question": challenge.question if challenge else None,
                "methods": challenge.methods if challenge else [],
                "timeout_seconds": challenge.timeout_seconds if challenge else 60,
                "suspicion_score": guard_result.suspicion_score,
            },
        )

    response_text, msg_id, thread_id, sources, is_learning = await _process_message(
        owner_id=auth.subject_id,
        participant_type=participant_type,
        participant_name=participant_name,
        text=body.message,
        thread_id=body.thread_id,
        db=db,
        r=r,
        ai=ai,
        conv=conv,
    )

    return ChatMessageResponse(
        thread_id=thread_id,
        message_id=msg_id,
        response=response_text,
        sources=sources,
        is_learning=is_learning,
    )


# -- Challenge response endpoint --


@router.post("/api/chat/challenge")
async def respond_to_challenge(
    body: ChallengeResponse,
    auth: AuthContext = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
    r: aioredis.Redis = Depends(get_redis),
    guard: IdentityGuard = Depends(_get_identity_guard_dep),
) -> dict:
    """Respond to an identity challenge (soft or hard)."""
    result = await guard.evaluate_challenge(
        owner_id=auth.subject_id,
        response=body,
        db=db,
        r=r,
    )
    return result.model_dump()


# -- Thread & history endpoints --


@router.get("/api/chat/threads", response_model=ThreadListResponse)
async def list_threads(
    page: int = 1,
    page_size: int = 20,
    auth: AuthContext = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
    conv: ConversationManager = Depends(_get_conversation_manager),
) -> ThreadListResponse:
    threads, total = await conv.list_threads(
        owner_id=auth.subject_id, db=db, page=page, page_size=page_size
    )
    return ThreadListResponse(
        threads=[ThreadResponse.model_validate(t) for t in threads],
        total=total,
    )


@router.get("/api/chat/threads/{thread_id}/messages", response_model=MessageHistoryResponse)
async def get_thread_messages(
    thread_id: str,
    limit: int = 50,
    before: str | None = None,
    auth: AuthContext = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
    conv: ConversationManager = Depends(_get_conversation_manager),
) -> MessageHistoryResponse:
    messages, has_more = await conv.get_messages(
        thread_id=thread_id,
        owner_id=auth.subject_id,
        db=db,
        limit=limit,
        before_id=before,
    )
    return MessageHistoryResponse(
        messages=[MessageResponse.model_validate(m) for m in messages],
        thread_id=thread_id,
        has_more=has_more,
    )


# -- WebSocket endpoint --


@router.websocket("/ws/chat/{owner_id}")
async def websocket_chat(
    websocket: WebSocket,
    owner_id: str,
    token: str | None = None,
) -> None:
    """WebSocket chat with streaming responses.

    Authentication via query param `?token=...` or first message `{"type":"auth","token":"..."}`.
    """
    await websocket.accept()

    # Authentication phase
    auth_payload: dict | None = None

    if token:
        try:
            auth_payload = _authenticate_token(token)
        except ValueError as e:
            await websocket.send_json(WSError(detail=str(e)).model_dump())
            await websocket.close(code=4001)
            return

    if auth_payload is None:
        try:
            raw = await websocket.receive_text()
            data = json.loads(raw)
            if data.get("type") != "auth" or "token" not in data:
                await websocket.send_json(WSError(detail="First message must be auth").model_dump())
                await websocket.close(code=4001)
                return
            auth_payload = _authenticate_token(data["token"])
        except (ValueError, json.JSONDecodeError) as e:
            await websocket.send_json(WSError(detail=str(e)).model_dump())
            await websocket.close(code=4001)
            return

    subject_id = auth_payload["sub"]
    role = auth_payload.get("role", "owner")

    if role == "owner" and subject_id != owner_id:
        await websocket.send_json(WSError(detail="Token owner mismatch").model_dump())
        await websocket.close(code=4003)
        return

    participant_type = ParticipantType.owner if role == "owner" else ParticipantType.family_member
    participant_name = role

    await websocket.send_json({"type": "auth_ok", "owner_id": owner_id})

    # Build dependencies
    from app.core.database import async_session
    from app.core.redis import redis_client

    ai = get_ai_client()
    conv = ConversationManager()
    guard = get_identity_guard()

    current_thread_id: str | None = None
    pending_challenge_id: str | None = None

    # Message loop
    try:
        while True:
            raw = await websocket.receive_text()

            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                await websocket.send_json(WSError(detail="Invalid JSON").model_dump())
                continue

            msg_type = data.get("type", "message")

            # Handle challenge response
            if msg_type == "challenge_response":
                challenge_resp = ChallengeResponse(
                    challenge_id=data.get("challenge_id", ""),
                    answer=data.get("answer"),
                    method=data.get("method"),
                    value=data.get("value"),
                )
                async with async_session() as db:
                    result = await guard.evaluate_challenge(
                        owner_id=owner_id,
                        response=challenge_resp,
                        db=db,
                        r=redis_client,
                    )
                    await db.commit()

                await websocket.send_json(
                    WSChallengeResult(
                        passed=result.passed,
                        message=result.message,
                    ).model_dump()
                )

                if result.passed:
                    pending_challenge_id = None
                else:
                    if result.new_score >= 80:
                        await websocket.send_json(WSLockout().model_dump())
                        await websocket.close(code=4003)
                        return
                continue

            if msg_type != "message":
                await websocket.send_json(WSError(detail=f"Unknown type: {msg_type}").model_dump())
                continue

            if pending_challenge_id:
                await websocket.send_json(
                    WSError(detail="Please complete the pending challenge first.").model_dump()
                )
                continue

            text = data.get("text", "").strip()
            if not text:
                await websocket.send_json(WSError(detail="Empty message").model_dump())
                continue

            requested_thread_id = data.get("thread_id") or current_thread_id

            async with async_session() as db:
                r = redis_client

                # Identity guard check
                guard_result = await guard.check(
                    owner_id=owner_id,
                    message=text,
                    role=role,
                    db=db,
                    r=r,
                    session_id=str(id(websocket)),
                )

                if guard_result.challenge_level == ChallengeLevel.lockout:
                    await websocket.send_json(WSLockout().model_dump())
                    await websocket.close(code=4003)
                    return

                if guard_result.challenge_level in (ChallengeLevel.soft, ChallengeLevel.hard):
                    challenge = guard_result.challenge
                    if challenge:
                        pending_challenge_id = challenge.challenge_id
                        await websocket.send_json(
                            WSChallenge(
                                challenge_id=challenge.challenge_id,
                                challenge_type=challenge.challenge_type.value,
                                question=challenge.question,
                                methods=challenge.methods,
                                timeout_seconds=challenge.timeout_seconds,
                            ).model_dump()
                        )
                    continue

                # Normal message processing
                thread = await conv.get_or_create_thread(
                    owner_id=owner_id,
                    participant_type=participant_type,
                    participant_name=participant_name,
                    db=db,
                    thread_id=requested_thread_id,
                )
                current_thread_id = thread.id

                # Save user message
                await conv.save_message(
                    thread_id=thread.id,
                    role=MessageRole.user,
                    content=text,
                    db=db,
                )

                # Ingest owner messages as knowledge
                is_learning = False
                if participant_type == ParticipantType.owner and len(text) > 20:
                    is_learning = await _ingest_owner_text(owner_id, text, ai, db)
                    if is_learning:
                        await websocket.send_json(WSLearning().model_dump())

                # Load context
                context = await conv.load_context(thread.id, db, r)

                # Get owner info for system prompt
                owner = await _resolve_owner(owner_id, db)
                owner_name = owner.name if owner else "the owner"
                owner_lang = owner.preferred_language if owner else "en"

                system_prompt = conv.build_system_prompt(
                    owner_name=owner_name,
                    language=owner_lang,
                    participant_type=participant_type,
                    participant_name=participant_name,
                )

                # Stream response via AI service SSE
                assistant_msg_id = str(uuid.uuid4())
                full_response = ""
                sources: list[dict] = []

                try:
                    async for event in ai.rag_stream(
                        owner_id=owner_id,
                        message=text,
                        conversation_history=context,
                        system_prompt=system_prompt,
                    ):
                        event_type = event.get("type", "")
                        if event_type == "sources":
                            sources = event.get("sources", [])
                        elif event_type == "token":
                            token_text = event.get("token", "")
                            if token_text:
                                full_response += token_text
                                await websocket.send_json(
                                    WSResponseToken(
                                        token=token_text,
                                        message_id=assistant_msg_id,
                                    ).model_dump()
                                )
                        elif event_type == "done":
                            pass
                except Exception:
                    logger.exception("Streaming generation failed")
                    if not full_response:
                        full_response = "I'm sorry, I encountered an error generating a response."

                # Save assistant message using the same ID sent in token events
                await conv.save_message(
                    thread_id=thread.id,
                    role=MessageRole.assistant,
                    content=full_response,
                    db=db,
                    message_id=assistant_msg_id,
                )

                await db.commit()

                # Send done signal — include content so clients can display it
                # even when no token events were received (e.g. streaming error)
                await websocket.send_json(
                    WSResponseDone(
                        message_id=assistant_msg_id,
                        thread_id=thread.id,
                        sources=sources,
                        is_learning=is_learning,
                        content=full_response,
                    ).model_dump()
                )

                # Background summarization check
                try:
                    await conv.maybe_summarize(thread.id, db, r, ai)
                except Exception:
                    logger.exception("WS summarization check failed")

    except WebSocketDisconnect:
        logger.info("WebSocket disconnected for owner %s", owner_id)
    except Exception:
        logger.exception("WebSocket error for owner %s", owner_id)
        try:
            await websocket.send_json(WSError(detail="Internal error").model_dump())
            await websocket.close(code=1011)
        except Exception:
            pass
