"""Voice chat: WebSocket endpoint (STT → LLM → TTS) and REST endpoints for voice settings/voices."""

import json
import logging
import uuid

import redis.asyncio as aioredis
from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect, status
from jose import JWTError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.ai_client import AIServiceClient, get_ai_client
from app.core.auth_guard import AuthContext, require_auth, require_role
from app.core.config import settings
from app.core.database import get_db
from app.core.security import decode_token
from app.models.chat import MessageRole, ParticipantType
from app.models.owner import Owner
from app.models.voice_chat import (
    UpdateVoiceSettingsRequest,
    VoiceInfo,
    VoiceListResponse,
    VoiceSettings,
    VoiceSettingsResponse,
    WSVoiceAudioOut,
    WSVoiceDone,
    WSVoiceError,
    WSVoiceResponseText,
    WSVoiceStatus,
    WSVoiceTranscript,
)
from app.services.conversation import ConversationManager
from app.services.multilingual import LanguageEngine
from app.services.personality import EmotionalSupport, PersonalityTracker
from app.services.voice_chat import RealTimeSTT, TTSEngine

logger = logging.getLogger(__name__)

router = APIRouter(tags=["voice-chat"])


# ─── REST endpoints ──────────────────────────────────────


@router.get("/api/voice/voices", response_model=VoiceListResponse)
async def list_voices(
    auth: AuthContext = Depends(require_auth),
) -> VoiceListResponse:
    """List available TTS voices."""
    voices = TTSEngine.list_voices()
    return VoiceListResponse(
        voices=[VoiceInfo(**v) for v in voices]
    )


@router.get("/api/voice/settings", response_model=VoiceSettingsResponse)
async def get_voice_settings(
    auth: AuthContext = Depends(require_role("owner")),
    db: AsyncSession = Depends(get_db),
) -> VoiceSettingsResponse:
    """Get the owner's voice chat settings."""
    result = await db.execute(
        select(VoiceSettings).where(VoiceSettings.owner_id == auth.subject_id)
    )
    vs = result.scalar_one_or_none()
    if not vs:
        return VoiceSettingsResponse(
            voice_id=settings.tts_default_voice,
            speed=1.0,
            auto_play=True,
            output_format=settings.voice_output_format,
        )
    return VoiceSettingsResponse(
        voice_id=vs.voice_id,
        speed=vs.speed,
        auto_play=vs.auto_play,
        output_format=vs.output_format,
    )


@router.put("/api/voice/settings", response_model=VoiceSettingsResponse)
async def update_voice_settings(
    body: UpdateVoiceSettingsRequest,
    auth: AuthContext = Depends(require_role("owner")),
    db: AsyncSession = Depends(get_db),
) -> VoiceSettingsResponse:
    """Update the owner's voice chat settings."""
    result = await db.execute(
        select(VoiceSettings).where(VoiceSettings.owner_id == auth.subject_id)
    )
    vs = result.scalar_one_or_none()

    if not vs:
        vs = VoiceSettings(
            id=str(uuid.uuid4()),
            owner_id=auth.subject_id,
        )
        db.add(vs)

    if body.voice_id is not None:
        vs.voice_id = body.voice_id
    if body.speed is not None:
        vs.speed = body.speed
    if body.auto_play is not None:
        vs.auto_play = body.auto_play
    if body.output_format is not None:
        vs.output_format = body.output_format

    await db.commit()
    await db.refresh(vs)

    return VoiceSettingsResponse(
        voice_id=vs.voice_id,
        speed=vs.speed,
        auto_play=vs.auto_play,
        output_format=vs.output_format,
    )


# ─── Helpers ──────────────────────────────────────────────


def _authenticate_token(token: str) -> dict:
    """Validate a JWT and return the payload."""
    try:
        payload = decode_token(token)
    except JWTError as e:
        raise ValueError(f"Invalid token: {e}") from e
    if payload.get("type") != "access":
        raise ValueError("Token type must be 'access'")
    return payload


async def _resolve_owner(owner_id: str, db: AsyncSession) -> Owner | None:
    result = await db.execute(select(Owner).where(Owner.id == owner_id))
    return result.scalar_one_or_none()


async def _load_voice_settings(owner_id: str, db: AsyncSession) -> VoiceSettings | None:
    result = await db.execute(
        select(VoiceSettings).where(VoiceSettings.owner_id == owner_id)
    )
    return result.scalar_one_or_none()


# ─── WebSocket voice chat ────────────────────────────────


@router.websocket("/ws/voice/{owner_id}")
async def websocket_voice_chat(
    websocket: WebSocket,
    owner_id: str,
    token: str | None = None,
) -> None:
    """Voice chat WebSocket: audio_in → STT → RAG + LLM → TTS → audio_out.

    Authentication via query param `?token=...` or first message `{"type":"auth","token":"..."}`.

    Protocol:
    1. Client authenticates (query param or JSON auth message)
    2. Client sends JSON control message {"type":"audio","format":"webm","is_final":false}
    3. Client sends binary audio frames
    4. Client sends control {"type":"audio","format":"webm","is_final":true} when done
    5. Server responds with: status → transcript → response_text → audio_out (binary) → done
    """
    await websocket.accept()

    # ── Authentication ──
    auth_payload: dict | None = None

    if token:
        try:
            auth_payload = _authenticate_token(token)
        except ValueError as e:
            await websocket.send_json(WSVoiceError(detail=str(e)).model_dump())
            await websocket.close(code=4001)
            return

    if auth_payload is None:
        try:
            raw = await websocket.receive_text()
            data = json.loads(raw)
            if data.get("type") != "auth" or "token" not in data:
                await websocket.send_json(WSVoiceError(detail="First message must be auth").model_dump())
                await websocket.close(code=4001)
                return
            auth_payload = _authenticate_token(data["token"])
        except (ValueError, json.JSONDecodeError) as e:
            await websocket.send_json(WSVoiceError(detail=str(e)).model_dump())
            await websocket.close(code=4001)
            return

    subject_id = auth_payload["sub"]
    role = auth_payload.get("role", "owner")

    if role == "owner" and subject_id != owner_id:
        await websocket.send_json(WSVoiceError(detail="Token owner mismatch").model_dump())
        await websocket.close(code=4003)
        return

    participant_type = ParticipantType.owner if role == "owner" else ParticipantType.family_member
    participant_name = role

    await websocket.send_json({"type": "auth_ok", "owner_id": owner_id})

    # ── Build dependencies ──
    from app.core.database import async_session
    from app.core.redis import redis_client

    ai = get_ai_client()
    conv = ConversationManager()
    current_thread_id: str | None = None

    # ── Message loop ──
    try:
        while True:
            audio_chunks: list[bytes] = []
            audio_format = "webm"
            total_audio_size = 0

            # Wait for audio control message or text
            raw = await websocket.receive_text()

            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                await websocket.send_json(WSVoiceError(detail="Invalid JSON").model_dump())
                continue

            msg_type = data.get("type", "")

            # Handle text message (typed while in voice mode)
            if msg_type == "message":
                text = data.get("text", "").strip()
                if not text:
                    continue
                thread_id = data.get("thread_id") or current_thread_id
                async with async_session() as db:
                    await _handle_text_exchange(
                        websocket=websocket,
                        owner_id=owner_id,
                        text=text,
                        thread_id=thread_id,
                        participant_type=participant_type,
                        participant_name=participant_name,
                        db=db,
                        r=redis_client,
                        ai=ai,
                        conv=conv,
                    )
                continue

            if msg_type != "audio":
                await websocket.send_json(WSVoiceError(detail=f"Unknown type: {msg_type}").model_dump())
                continue

            audio_format = data.get("format", "webm")
            is_final = data.get("is_final", False)

            # Listen for binary audio frames
            await websocket.send_json(WSVoiceStatus(status="listening").model_dump())

            if not is_final:
                # Receive binary audio chunks until final control message
                while True:
                    message = await websocket.receive()

                    if "bytes" in message and message["bytes"]:
                        chunk = message["bytes"]
                        total_audio_size += len(chunk)
                        if total_audio_size > settings.voice_max_audio_mb * 1024 * 1024:
                            await websocket.send_json(
                                WSVoiceError(detail="Audio too large").model_dump()
                            )
                            break
                        audio_chunks.append(chunk)

                    elif "text" in message and message["text"]:
                        try:
                            ctrl = json.loads(message["text"])
                            if ctrl.get("type") == "audio" and ctrl.get("is_final"):
                                break
                            if ctrl.get("type") == "cancel":
                                audio_chunks.clear()
                                break
                        except json.JSONDecodeError:
                            pass
            else:
                # is_final=True with no preceding chunks — expect binary right after
                message = await websocket.receive()
                if "bytes" in message and message["bytes"]:
                    audio_chunks.append(message["bytes"])

            if not audio_chunks:
                continue

            combined_audio = b"".join(audio_chunks)

            # ── STT ──
            await websocket.send_json(WSVoiceStatus(status="transcribing").model_dump())

            try:
                result = await RealTimeSTT.transcribe_file(
                    combined_audio, input_format=audio_format
                )
                transcript_text = result["text"]
            except Exception:
                logger.exception("STT transcription failed")
                await websocket.send_json(
                    WSVoiceError(detail="Failed to transcribe audio").model_dump()
                )
                continue

            if not transcript_text.strip():
                await websocket.send_json(
                    WSVoiceTranscript(text="", is_final=True, confidence=0.0).model_dump()
                )
                continue

            # Send transcript
            await websocket.send_json(
                WSVoiceTranscript(
                    text=transcript_text,
                    is_final=True,
                    confidence=result.get("language_probability", 0.0),
                ).model_dump()
            )

            # ── LLM + TTS ──
            await websocket.send_json(WSVoiceStatus(status="thinking").model_dump())

            thread_id = data.get("thread_id") or current_thread_id

            async with async_session() as db:
                response_text, msg_id, new_thread_id, sources, is_learning = await _process_voice_message(
                    owner_id=owner_id,
                    text=transcript_text,
                    thread_id=thread_id,
                    participant_type=participant_type,
                    participant_name=participant_name,
                    db=db,
                    r=redis_client,
                    ai=ai,
                    conv=conv,
                )
                current_thread_id = new_thread_id

                # Send response text
                await websocket.send_json(
                    WSVoiceResponseText(
                        text=response_text,
                        message_id=msg_id,
                        thread_id=new_thread_id,
                        sources=sources,
                        is_learning=is_learning,
                    ).model_dump()
                )

                # ── TTS ──
                await websocket.send_json(WSVoiceStatus(status="speaking").model_dump())

                # Load voice settings
                vs = await _load_voice_settings(owner_id, db)
                voice_id = vs.voice_id if vs else settings.tts_default_voice
                speed = vs.speed if vs else 1.0
                out_format = vs.output_format if vs else settings.voice_output_format

            try:
                tts_result = await TTSEngine.synthesize(
                    text=response_text,
                    voice_id=voice_id,
                    speed=speed,
                    output_format=out_format,
                )

                # Send audio metadata
                await websocket.send_json(
                    WSVoiceAudioOut(
                        format=tts_result["format"],
                        sample_rate=tts_result["sample_rate"],
                        duration_ms=tts_result["duration_ms"],
                        text=response_text,
                    ).model_dump()
                )

                # Send audio as binary frame
                await websocket.send_bytes(tts_result["audio_bytes"])

            except Exception:
                logger.exception("TTS synthesis failed")
                await websocket.send_json(
                    WSVoiceError(detail="Failed to synthesize speech").model_dump()
                )

            # Done
            await websocket.send_json(
                WSVoiceDone(
                    message_id=msg_id,
                    thread_id=current_thread_id or "",
                ).model_dump()
            )

    except WebSocketDisconnect:
        logger.info("Voice WebSocket disconnected for owner %s", owner_id)
    except Exception:
        logger.exception("Voice WebSocket error for owner %s", owner_id)
        try:
            await websocket.send_json(WSVoiceError(detail="Internal error").model_dump())
            await websocket.close(code=1011)
        except Exception:
            pass


async def _process_voice_message(
    owner_id: str,
    text: str,
    thread_id: str | None,
    participant_type: ParticipantType,
    participant_name: str,
    db: AsyncSession,
    r: aioredis.Redis,
    ai: AIServiceClient,
    conv: ConversationManager,
) -> tuple[str, str, str, list[dict], bool]:
    """Process a voice message through the same pipeline as text chat.

    Returns (response_text, message_id, thread_id, sources, is_learning).
    """
    thread = await conv.get_or_create_thread(
        owner_id=owner_id,
        participant_type=participant_type,
        participant_name=participant_name,
        db=db,
        thread_id=thread_id,
    )

    # Detect language
    detection = await LanguageEngine.detect_language(text, ai)
    detected_lang = detection["language_code"]

    # Save user message
    user_msg = await conv.save_message(
        thread_id=thread.id,
        role=MessageRole.user,
        content=text,
        language=detected_lang,
        db=db,
    )

    # Ingest owner messages as knowledge
    is_learning = False
    if participant_type == ParticipantType.owner and len(text) > 20:
        try:
            english_translation: str | None = None
            if detected_lang != "en":
                tr = await LanguageEngine.translate(text, detected_lang, "en", r=r, ai=ai)
                english_translation = tr["translated_text"]
            await ai.ingest_text(
                owner_id=owner_id,
                text=text,
                language=detected_lang,
                english_translation=english_translation,
            )
            is_learning = True
        except Exception:
            logger.exception("Knowledge ingestion failed for voice message")

    # Load context
    context = await conv.load_context(thread.id, db, r)

    # Emotion detection
    emotion_detection = await EmotionalSupport.detect_emotion(text, ai)
    await EmotionalSupport.log_emotion(owner_id, emotion_detection, db, message_id=user_msg.id)

    # Build system prompt
    owner = await _resolve_owner(owner_id, db)
    owner_name = owner.name if owner else "the owner"
    owner_lang = owner.preferred_language if owner else "en"
    base_prompt = conv.build_system_prompt(
        owner_name=owner_name,
        language=owner_lang,
        participant_type=participant_type,
        participant_name=participant_name,
    )

    lang_prompt = LanguageEngine.build_language_system_prompt(detected_lang)

    personality_prompt = ""
    profile = await PersonalityTracker.get_profile(owner_id, db)
    if profile and profile.messages_analyzed > 0:
        personality_prompt = PersonalityTracker.get_personality_prompt(profile)

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

    # Voice-specific instruction: keep responses concise for speech
    system_prompt += (
        "\n\n[Voice Mode] The user is speaking via voice. Keep your response concise "
        "and conversational — aim for 1-3 sentences. Avoid markdown formatting, "
        "bullet points, or code blocks since the response will be spoken aloud."
    )

    # RAG generate (non-streaming for voice — need full text for TTS)
    rag_result = await ai.rag_generate(
        owner_id=owner_id,
        message=text,
        conversation_history=context,
        system_prompt=system_prompt,
    )

    response_text = rag_result.get("response", "")
    sources = rag_result.get("sources", [])

    # Save assistant message
    assistant_msg = await conv.save_message(
        thread_id=thread.id,
        role=MessageRole.assistant,
        content=response_text,
        db=db,
    )

    await db.commit()

    # Summarization check
    try:
        await conv.maybe_summarize(thread.id, db, r, ai)
    except Exception:
        logger.exception("Voice chat summarization check failed")

    # Personality analysis trigger
    if participant_type == ParticipantType.owner:
        try:
            if await PersonalityTracker.should_analyze(owner_id, db):
                await PersonalityTracker.analyze_message_batch(owner_id, db, ai)
                await db.commit()
        except Exception:
            logger.exception("Personality analysis check failed in voice chat")

    return response_text, assistant_msg.id, thread.id, sources, is_learning


async def _handle_text_exchange(
    websocket: WebSocket,
    owner_id: str,
    text: str,
    thread_id: str | None,
    participant_type: ParticipantType,
    participant_name: str,
    db: AsyncSession,
    r: aioredis.Redis,
    ai: AIServiceClient,
    conv: ConversationManager,
) -> None:
    """Handle a text message in voice mode — process and respond with TTS."""
    await websocket.send_json(WSVoiceStatus(status="thinking").model_dump())

    response_text, msg_id, new_thread_id, sources, is_learning = await _process_voice_message(
        owner_id=owner_id,
        text=text,
        thread_id=thread_id,
        participant_type=participant_type,
        participant_name=participant_name,
        db=db,
        r=r,
        ai=ai,
        conv=conv,
    )

    await websocket.send_json(
        WSVoiceResponseText(
            text=response_text,
            message_id=msg_id,
            thread_id=new_thread_id,
            sources=sources,
            is_learning=is_learning,
        ).model_dump()
    )

    # TTS
    await websocket.send_json(WSVoiceStatus(status="speaking").model_dump())

    vs = await _load_voice_settings(owner_id, db)
    voice_id = vs.voice_id if vs else settings.tts_default_voice
    speed = vs.speed if vs else 1.0
    out_format = vs.output_format if vs else settings.voice_output_format

    try:
        tts_result = await TTSEngine.synthesize(
            text=response_text,
            voice_id=voice_id,
            speed=speed,
            output_format=out_format,
        )

        await websocket.send_json(
            WSVoiceAudioOut(
                format=tts_result["format"],
                sample_rate=tts_result["sample_rate"],
                duration_ms=tts_result["duration_ms"],
                text=response_text,
            ).model_dump()
        )
        await websocket.send_bytes(tts_result["audio_bytes"])
    except Exception:
        logger.exception("TTS failed in text exchange")

    await websocket.send_json(
        WSVoiceDone(message_id=msg_id, thread_id=new_thread_id).model_dump()
    )
