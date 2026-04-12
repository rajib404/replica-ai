"""Video call: WebSocket endpoint with face verification + voice chat (STT → LLM → TTS)."""

import json
import logging
import time

import redis.asyncio as aioredis
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.core.ai_client import get_ai_client
from app.core.config import settings
from app.core.security import decode_token
from app.models.chat import ParticipantType
from app.models.video_call import WSVideoCallStatus, WSVideoFaceResult
from app.models.voice_chat import (
    WSVoiceAudioOut,
    WSVoiceDone,
    WSVoiceError,
    WSVoiceResponseText,
    WSVoiceStatus,
    WSVoiceTranscript,
)
from app.routers.voice_chat import (
    _authenticate_token,
    _handle_text_exchange,
    _load_voice_settings,
    _process_voice_message,
    _resolve_owner,
)
from app.services.conversation import ConversationManager
from app.services.face_verify import get_face_manager
from app.services.voice_chat import RealTimeSTT, TTSEngine

logger = logging.getLogger(__name__)

router = APIRouter(tags=["video-call"])


@router.websocket("/ws/video/{owner_id}")
async def websocket_video_call(
    websocket: WebSocket,
    owner_id: str,
    token: str | None = None,
) -> None:
    """Video call WebSocket: face verification + audio_in → STT → RAG + LLM → TTS → audio_out.

    Authentication via query param `?token=...` or first message `{"type":"auth","token":"..."}`.

    Protocol:
    1. Client authenticates (query param or JSON auth message)
    2. Client sends JSON control messages:
       - {"type":"audio","format":"webm","is_final":false} + binary audio frames
       - {"type":"face_frame"} + binary JPEG frame
       - {"type":"message","text":"..."} for text input
    3. Server responds with: status, transcript, response_text, audio_out, face_result, done
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
    face_manager = get_face_manager()
    current_thread_id: str | None = None
    call_start = time.monotonic()
    face_verified = False

    # ── Message loop ──
    try:
        while True:
            audio_chunks: list[bytes] = []
            audio_format = "webm"
            total_audio_size = 0

            # Wait for control message
            raw = await websocket.receive_text()

            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                await websocket.send_json(WSVoiceError(detail="Invalid JSON").model_dump())
                continue

            msg_type = data.get("type", "")

            # ── Face frame ──
            if msg_type == "face_frame":
                # Next binary frame is the JPEG image
                message = await websocket.receive()
                if "bytes" not in message or not message["bytes"]:
                    await websocket.send_json(
                        WSVideoFaceResult(
                            verified=False, confidence=0.0, message="No image data received"
                        ).model_dump()
                    )
                    continue

                jpeg_data = message["bytes"]
                try:
                    async with async_session() as db:
                        result = await face_manager.verify_face(
                            owner_id=owner_id,
                            image=jpeg_data,
                            db=db,
                            source="video_call",
                        )
                    face_verified = result["verified"]
                    await websocket.send_json(
                        WSVideoFaceResult(
                            verified=result["verified"],
                            confidence=result["confidence"],
                            message=result["message"],
                        ).model_dump()
                    )
                except Exception:
                    logger.exception("Face verification failed during video call")
                    await websocket.send_json(
                        WSVideoFaceResult(
                            verified=False, confidence=0.0, message="Face verification error"
                        ).model_dump()
                    )
                continue

            # ── Video status request ──
            if msg_type == "video_status":
                elapsed = int(time.monotonic() - call_start)
                await websocket.send_json(
                    WSVideoCallStatus(
                        face_verified=face_verified,
                        call_duration_sec=elapsed,
                    ).model_dump()
                )
                continue

            # ── Text message ──
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

            # ── Audio message ──
            if msg_type != "audio":
                await websocket.send_json(WSVoiceError(detail=f"Unknown type: {msg_type}").model_dump())
                continue

            audio_format = data.get("format", "webm")
            is_final = data.get("is_final", False)

            # Listen for binary audio frames
            await websocket.send_json(WSVoiceStatus(status="listening").model_dump())

            if not is_final:
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
                logger.exception("STT transcription failed in video call")
                await websocket.send_json(
                    WSVoiceError(detail="Failed to transcribe audio").model_dump()
                )
                continue

            if not transcript_text.strip():
                await websocket.send_json(
                    WSVoiceTranscript(text="", is_final=True, confidence=0.0).model_dump()
                )
                continue

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
                logger.exception("TTS synthesis failed in video call")
                await websocket.send_json(
                    WSVoiceError(detail="Failed to synthesize speech").model_dump()
                )

            await websocket.send_json(
                WSVoiceDone(
                    message_id=msg_id,
                    thread_id=current_thread_id or "",
                ).model_dump()
            )

    except WebSocketDisconnect:
        logger.info("Video WebSocket disconnected for owner %s", owner_id)
    except Exception:
        logger.exception("Video WebSocket error for owner %s", owner_id)
        try:
            await websocket.send_json(WSVoiceError(detail="Internal error").model_dump())
            await websocket.close(code=1011)
        except Exception:
            pass
