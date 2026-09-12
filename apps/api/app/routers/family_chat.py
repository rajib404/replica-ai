"""Family chat endpoints: REST + WebSocket for family members, monitoring for owners."""

import json
import logging
import uuid

import redis.asyncio as aioredis
from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect
from jose import JWTError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.ai_client import AIServiceClient, get_ai_client
from app.core.auth_guard import AuthContext, require_role
from app.core.database import get_db
from app.core.redis import get_redis
from app.core.security import decode_token
from app.models.chat import (
    ConversationThread,
    MessageRole,
    WSError,
    WSResponseDone,
    WSResponseToken,
)
from app.models.family_chat import (
    ActiveSessionsResponse,
    ConversationLogMessage,
    ConversationLogResponse,
    FamilyAnalyticsResponse,
    FamilyAssetListResponse,
    FamilyChatMessageRequest,
    FamilyChatMessageResponse,
    FamilyMemberAnalytics,
    FamilySessionInfoResponse,
    FamilySessionSummary,
    InterveneResponse,
    InterveneSendRequest,
)
from app.models.owner import AccessRule
from app.services.conversation import ConversationManager, strip_source_labels
from app.services.family_access import list_family_assets, resolve_family_scope
from app.services.family_chat import FAMILY_CHAT_TEMPERATURE, FamilyConversationHandler

logger = logging.getLogger(__name__)

router = APIRouter(tags=["family-chat"])

handler = FamilyConversationHandler()


# ─── Family member auth (thin wrapper over the shared AuthContext) ──


async def _require_family_member(
    auth: AuthContext = Depends(require_role("family_member")),
) -> AuthContext:
    """Require a family_member JWT and return its resolved AuthContext.

    `auth.subject_id` is the owner's id, `auth.rule_id`/`auth.access_level`/
    `auth.grantee_name` are the session's scoping claims (see auth_guard.py).
    """
    return auth


# ─── Family Member Chat (REST) ──────────────────────────


@router.post("/api/family/chat", response_model=FamilyChatMessageResponse)
async def family_send_message(
    body: FamilyChatMessageRequest,
    auth: AuthContext = Depends(_require_family_member),
    db: AsyncSession = Depends(get_db),
    r: aioredis.Redis = Depends(get_redis),
    ai: AIServiceClient = Depends(get_ai_client),
) -> FamilyChatMessageResponse:
    """Send a chat message as a family member (non-streaming)."""
    rule_result = await db.execute(
        select(AccessRule).where(AccessRule.id == auth.rule_id)
    )
    rule = rule_result.scalar_one_or_none()

    response_text, msg_id, thread_id, sources = await handler.process_family_message(
        owner_id=auth.subject_id,
        grantee_name=auth.grantee_name or "Family Member",
        relation=rule.grantee_relation if rule else None,
        access_level=auth.access_level or "limited",
        rule_id=auth.rule_id or "",
        topic_restrictions=rule.topic_restrictions if rule else None,
        time_restrictions=rule.time_restrictions if rule else None,
        text=body.message,
        thread_id=body.thread_id,
        db=db,
        r=r,
        ai=ai,
    )

    return FamilyChatMessageResponse(
        thread_id=thread_id,
        message_id=msg_id,
        response=response_text,
        sources=sources,
    )


# ─── Family Session Info ─────────────────────────────────


@router.get("/api/family/chat/session", response_model=FamilySessionInfoResponse)
async def family_session_info(
    auth: AuthContext = Depends(_require_family_member),
    db: AsyncSession = Depends(get_db),
) -> FamilySessionInfoResponse:
    """Get session info for the current family member (owner name, access level, etc.)."""
    info = await handler.get_family_session_info(
        owner_id=auth.subject_id,
        grantee_name=auth.grantee_name or "Family Member",
        access_level=auth.access_level or "limited",
        rule_id=auth.rule_id or "",
        db=db,
    )
    return FamilySessionInfoResponse(**info)


# ─── Family Assets (read-only, scoped by access rule) ────


@router.get("/api/family/assets", response_model=FamilyAssetListResponse)
async def family_list_assets(
    auth: AuthContext = Depends(_require_family_member),
    db: AsyncSession = Depends(get_db),
) -> FamilyAssetListResponse:
    """List the owner's knowledge entries this family member is allowed to see."""
    entries = await list_family_assets(auth, db)
    return FamilyAssetListResponse(entries=entries, total=len(entries))


# ─── Family Chat WebSocket ───────────────────────────────


@router.websocket("/ws/family/chat/{owner_id}")
async def family_websocket_chat(
    websocket: WebSocket,
    owner_id: str,
    token: str | None = None,
) -> None:
    """WebSocket chat for family members with streaming responses."""
    await websocket.accept()

    # Authenticate
    auth_payload: dict | None = None
    if token:
        try:
            auth_payload = decode_token(token)
        except JWTError as e:
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
            auth_payload = decode_token(data["token"])
        except (ValueError, json.JSONDecodeError, JWTError) as e:
            await websocket.send_json(WSError(detail=str(e)).model_dump())
            await websocket.close(code=4001)
            return

    if auth_payload.get("type") != "access":
        await websocket.send_json(WSError(detail="Invalid token type").model_dump())
        await websocket.close(code=4001)
        return

    if auth_payload.get("role") != "family_member":
        await websocket.send_json(WSError(detail="Family member token required").model_dump())
        await websocket.close(code=4003)
        return

    subject_id = auth_payload["sub"]
    if subject_id != owner_id:
        await websocket.send_json(WSError(detail="Token owner mismatch").model_dump())
        await websocket.close(code=4003)
        return

    auth = AuthContext(
        subject_id=subject_id,
        role="family_member",
        rule_id=auth_payload.get("rule_id"),
        access_level=auth_payload.get("access_level", "limited"),
        grantee_name=auth_payload.get("grantee_name", "Family Member"),
    )
    grantee_name = auth.grantee_name or "Family Member"
    access_level = auth.access_level or "limited"
    rule_id = auth.rule_id or ""

    await websocket.send_json({
        "type": "auth_ok",
        "owner_id": owner_id,
        "grantee_name": grantee_name,
        "access_level": access_level,
    })

    # Build dependencies
    from app.core.database import async_session
    from app.core.redis import redis_client

    ai = get_ai_client()
    conv = ConversationManager()

    current_thread_id: str | None = None

    try:
        while True:
            raw = await websocket.receive_text()
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                await websocket.send_json(WSError(detail="Invalid JSON").model_dump())
                continue

            if data.get("type") != "message":
                await websocket.send_json(
                    WSError(detail=f"Unknown type: {data.get('type')}").model_dump()
                )
                continue

            text = data.get("text", "").strip()
            if not text:
                await websocket.send_json(WSError(detail="Empty message").model_dump())
                continue

            requested_thread_id = data.get("thread_id") or current_thread_id

            async with async_session() as db:
                r = redis_client

                # Load rule for topic restrictions
                rule_result = await db.execute(
                    select(AccessRule).where(AccessRule.id == rule_id)
                )
                rule = rule_result.scalar_one_or_none()
                topic_restrictions = rule.topic_restrictions if rule else None
                relation = rule.grantee_relation if rule else None

                # Prepare streaming (saves user msg, checks topic block)
                refusal, system_prompt, thread_id, _ = await handler.prepare_family_stream(
                    owner_id=owner_id,
                    grantee_name=grantee_name,
                    relation=relation,
                    access_level=access_level,
                    rule_id=rule_id,
                    topic_restrictions=topic_restrictions,
                    text=text,
                    thread_id=requested_thread_id,
                    db=db,
                    r=r,
                )
                current_thread_id = thread_id

                if refusal:
                    refusal_id = str(uuid.uuid4())
                    await websocket.send_json(
                        WSResponseToken(token=refusal, message_id=refusal_id).model_dump()
                    )
                    await websocket.send_json(
                        WSResponseDone(
                            message_id=refusal_id,
                            thread_id=thread_id,
                            sources=[],
                        ).model_dump()
                    )
                    continue

                # Stream response
                context = await conv.load_context(thread_id, db, r)
                assistant_msg_id = str(uuid.uuid4())
                full_response = ""
                sources: list[dict] = []
                scope = await resolve_family_scope(auth, db)

                try:
                    async for event in ai.rag_stream(
                        owner_id=owner_id,
                        message=text,
                        conversation_history=context,
                        system_prompt=system_prompt,
                        allowed_content_types=scope.allowed_content_types,
                        allowed_categories=scope.allowed_categories,
                        temperature=FAMILY_CHAT_TEMPERATURE,
                    ):
                        event_type = event.get("type", "")
                        if event_type == "sources":
                            sources = event.get("sources", [])
                        elif event_type == "token":
                            tok = event.get("token", "")
                            if tok:
                                full_response += tok
                                await websocket.send_json(
                                    WSResponseToken(
                                        token=tok,
                                        message_id=assistant_msg_id,
                                    ).model_dump()
                                )
                        elif event_type == "done":
                            pass
                except Exception:
                    logger.exception("Family streaming generation failed")
                    if not full_response:
                        full_response = "I'm sorry, I encountered an error."

                full_response = strip_source_labels(full_response)

                # Save assistant response
                assistant_msg = await conv.save_message(
                    thread_id=thread_id,
                    role=MessageRole.assistant,
                    content=full_response,
                    db=db,
                )
                assistant_msg_id = assistant_msg.id
                await db.commit()

                await websocket.send_json(
                    WSResponseDone(
                        message_id=assistant_msg_id,
                        thread_id=thread_id,
                        sources=sources,
                    ).model_dump()
                )

                try:
                    await conv.maybe_summarize(thread_id, db, r, ai)
                except Exception:
                    logger.exception("Family WS summarization failed")

    except WebSocketDisconnect:
        logger.info("Family WebSocket disconnected: %s for owner %s", grantee_name, owner_id)
    except Exception:
        logger.exception("Family WebSocket error for owner %s", owner_id)
        try:
            await websocket.send_json(WSError(detail="Internal error").model_dump())
            await websocket.close(code=1011)
        except Exception:
            pass


# ─── Owner Monitoring Endpoints ──────────────────────────


@router.get("/api/access/sessions", response_model=ActiveSessionsResponse)
async def get_active_sessions(
    auth: AuthContext = Depends(require_role("owner")),
    db: AsyncSession = Depends(get_db),
    r: aioredis.Redis = Depends(get_redis),
) -> ActiveSessionsResponse:
    """List all active family chat sessions for this owner."""
    sessions = await handler.get_active_sessions(auth.subject_id, r, db)
    return ActiveSessionsResponse(
        sessions=[FamilySessionSummary(**s) for s in sessions],
        total=len(sessions),
    )


@router.get("/api/access/sessions/{thread_id}/messages", response_model=ConversationLogResponse)
async def get_family_conversation_log(
    thread_id: str,
    limit: int = 50,
    before: str | None = None,
    auth: AuthContext = Depends(require_role("owner")),
    db: AsyncSession = Depends(get_db),
) -> ConversationLogResponse:
    """Read a family member's conversation log (owner only)."""
    conv = ConversationManager()
    messages, has_more = await conv.get_messages(
        thread_id=thread_id,
        owner_id=auth.subject_id,
        db=db,
        limit=limit,
        before_id=before,
    )

    thread_result = await db.execute(
        select(ConversationThread).where(
            ConversationThread.id == thread_id,
            ConversationThread.owner_id == auth.subject_id,
        )
    )
    thread = thread_result.scalar_one_or_none()
    grantee_name = thread.participant_name if thread else "Unknown"

    return ConversationLogResponse(
        thread_id=thread_id,
        grantee_name=grantee_name,
        messages=[
            ConversationLogMessage(
                id=m.id,
                role=m.role.value,
                content_text=m.content_text,
                language=m.language,
                created_at=m.created_at,
            )
            for m in messages
        ],
        has_more=has_more,
    )


@router.post("/api/access/sessions/{thread_id}/intervene", response_model=InterveneResponse)
async def owner_intervene(
    thread_id: str,
    body: InterveneSendRequest,
    auth: AuthContext = Depends(require_role("owner")),
    db: AsyncSession = Depends(get_db),
) -> InterveneResponse:
    """Owner sends a message into a family conversation (as the replica)."""
    try:
        msg_id, tid = await handler.owner_intervene(
            owner_id=auth.subject_id,
            thread_id=thread_id,
            message_text=body.message,
            db=db,
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e

    return InterveneResponse(message_id=msg_id, thread_id=tid)


@router.get("/api/access/analytics", response_model=FamilyAnalyticsResponse)
async def get_family_analytics(
    auth: AuthContext = Depends(require_role("owner")),
    db: AsyncSession = Depends(get_db),
) -> FamilyAnalyticsResponse:
    """Get family member analytics for this owner."""
    data = await handler.get_family_analytics(auth.subject_id, db)
    return FamilyAnalyticsResponse(
        members=[FamilyMemberAnalytics(**m) for m in data["members"]],
        total_family_messages=data["total_family_messages"],
        total_family_sessions=data["total_family_sessions"],
    )
