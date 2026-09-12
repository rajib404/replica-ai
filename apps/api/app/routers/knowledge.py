import asyncio
import logging
import mimetypes
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, UploadFile, status
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.ai_client import AIServiceClient, get_ai_client
from app.core.auth_guard import AuthContext, require_auth, require_role
from app.core.database import async_session, get_db
from app.models.knowledge import (
    ContentType,
    IngestAcceptedResponse,
    IngestCompletedResponse,
    KnowledgeEntry,
    KnowledgeEntryResponse,
    KnowledgeListResponse,
    TaskStatusResponse,
    TextIngestRequest,
)
from app.services.family_access import resolve_family_scope

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/knowledge", tags=["knowledge"])


async def _auto_persist(ai: AIServiceClient, task_id: str, owner_id: str) -> None:
    """Background: poll AI service until task completes, then write entry to DB.

    This makes file uploads reliable — the client does not need to poll
    GET /api/knowledge/tasks/{task_id} for the entry to appear.
    """
    for _ in range(150):  # poll up to 5 minutes (150 × 2 s)
        await asyncio.sleep(2)
        try:
            task = await ai.get_task_status(task_id)
        except Exception:
            continue

        task_status = task.get("status")
        if task_status == "failed":
            logger.warning("Ingest task %s failed: %s", task_id, task.get("error"))
            return
        if task_status != "completed":
            continue

        result = task.get("result") or {}
        entry_id = result.get("entry_id")
        if not entry_id:
            return

        async with async_session() as db:
            existing = await db.execute(
                select(KnowledgeEntry).where(KnowledgeEntry.id == entry_id)
            )
            if existing.scalar_one_or_none() is not None:
                return  # already persisted (e.g. client polled first)

            path = result.get("original_content_path") or ""
            if "/audio/" in path:
                ct = ContentType.audio
            elif "/video/" in path:
                ct = ContentType.video
            elif "/image/" in path:
                ct = ContentType.image
            elif "/document/" in path:
                ct = ContentType.document
            else:
                ct = ContentType.text

            entry = KnowledgeEntry(
                id=entry_id,
                owner_id=owner_id,
                content_type=ct,
                original_content_path=result.get("original_content_path"),
                original_language=result.get("language"),
                english_translation=result.get("english_translation"),
                embedding_id=result.get("embedding_id"),
                category=result.get("category"),
                metadata_=result.get("metadata"),
            )
            db.add(entry)
            await db.commit()
            logger.info("Auto-persisted entry %s (task %s)", entry_id, task_id)
        return

    logger.warning("Auto-persist for task %s timed out", task_id)

# Size limits
AUDIO_MAX_SIZE = 50 * 1024 * 1024  # 50 MB
VIDEO_MAX_SIZE = 500 * 1024 * 1024  # 500 MB
DOC_MAX_SIZE = 20 * 1024 * 1024  # 20 MB
IMAGE_MAX_SIZE = 10 * 1024 * 1024  # 10 MB

AUDIO_EXTENSIONS = {".wav", ".mp3", ".m4a", ".ogg", ".flac", ".webm"}
VIDEO_EXTENSIONS = {".mp4", ".mov", ".avi", ".mkv", ".webm"}
DOC_EXTENSIONS = {".pdf", ".docx", ".txt", ".csv"}
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".heic", ".heif"}


def _validate_extension(filename: str, allowed: set[str], label: str) -> None:
    ext = Path(filename).suffix.lower()
    if ext not in allowed:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported {label} format '{ext}'. Allowed: {', '.join(sorted(allowed))}",
        )


# -- Transcription (synchronous, auth-gated) --


class TranscribeResponse(BaseModel):
    text: str
    language: str


@router.post("/transcribe", response_model=TranscribeResponse)
async def transcribe_audio(
    file: UploadFile,
    auth: AuthContext = Depends(require_role("owner")),
    ai: AIServiceClient = Depends(get_ai_client),
) -> TranscribeResponse:
    """Transcribe an audio file and return the text + detected language."""
    _validate_extension(file.filename or "", AUDIO_EXTENSIONS, "audio")

    data = await file.read()
    if len(data) > AUDIO_MAX_SIZE:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Audio file exceeds {AUDIO_MAX_SIZE // (1024 * 1024)}MB limit",
        )

    result = await ai.transcribe(data, file.filename or "audio.m4a")
    return TranscribeResponse(text=result["text"], language=result["language"])


# -- Text ingest (synchronous) --


@router.post("/text", status_code=201, response_model=IngestCompletedResponse)
async def ingest_text(
    body: TextIngestRequest,
    auth: AuthContext = Depends(require_role("owner")),
    ai: AIServiceClient = Depends(get_ai_client),
    db: AsyncSession = Depends(get_db),
) -> IngestCompletedResponse:
    """Ingest text: AI service processes, API writes to DB."""
    result = await ai.ingest_text(
        owner_id=auth.subject_id,
        text=body.text,
        language=body.language,
    )

    entry = KnowledgeEntry(
        id=result["entry_id"],
        owner_id=auth.subject_id,
        content_type=ContentType.text,
        original_language=result.get("language"),
        english_translation=result.get("english_translation"),
        embedding_id=result.get("embedding_id"),
        category=result.get("category"),
        metadata_=result.get("metadata"),
    )
    db.add(entry)
    await db.commit()

    return IngestCompletedResponse(entry_id=result["entry_id"])


# -- Audio ingest (background via AI service) --


@router.post("/audio", status_code=202, response_model=IngestAcceptedResponse)
async def ingest_audio(
    file: UploadFile,
    background_tasks: BackgroundTasks,
    auth: AuthContext = Depends(require_role("owner")),
    ai: AIServiceClient = Depends(get_ai_client),
) -> IngestAcceptedResponse:
    _validate_extension(file.filename or "", AUDIO_EXTENSIONS, "audio")

    data = await file.read()
    if len(data) > AUDIO_MAX_SIZE:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Audio file exceeds {AUDIO_MAX_SIZE // (1024*1024)}MB limit",
        )

    result = await ai.ingest_audio(auth.subject_id, data, file.filename or "audio")
    background_tasks.add_task(_auto_persist, ai, result["task_id"], auth.subject_id)
    return IngestAcceptedResponse(task_id=result["task_id"])


# -- Video ingest (background via AI service) --


@router.post("/video", status_code=202, response_model=IngestAcceptedResponse)
async def ingest_video(
    file: UploadFile,
    background_tasks: BackgroundTasks,
    auth: AuthContext = Depends(require_role("owner")),
    ai: AIServiceClient = Depends(get_ai_client),
) -> IngestAcceptedResponse:
    _validate_extension(file.filename or "", VIDEO_EXTENSIONS, "video")

    data = await file.read()
    if len(data) > VIDEO_MAX_SIZE:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Video file exceeds {VIDEO_MAX_SIZE // (1024*1024)}MB limit",
        )

    result = await ai.ingest_video(auth.subject_id, data, file.filename or "video")
    background_tasks.add_task(_auto_persist, ai, result["task_id"], auth.subject_id)
    return IngestAcceptedResponse(task_id=result["task_id"])


# -- Document ingest (background via AI service) --


@router.post("/document", status_code=202, response_model=IngestAcceptedResponse)
async def ingest_document(
    file: UploadFile,
    background_tasks: BackgroundTasks,
    auth: AuthContext = Depends(require_role("owner")),
    ai: AIServiceClient = Depends(get_ai_client),
) -> IngestAcceptedResponse:
    _validate_extension(file.filename or "", DOC_EXTENSIONS, "document")

    data = await file.read()
    if len(data) > DOC_MAX_SIZE:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Document exceeds {DOC_MAX_SIZE // (1024*1024)}MB limit",
        )

    result = await ai.ingest_document(auth.subject_id, data, file.filename or "document")
    background_tasks.add_task(_auto_persist, ai, result["task_id"], auth.subject_id)
    return IngestAcceptedResponse(task_id=result["task_id"])


# -- Image ingest (background via AI service) --


@router.post("/image", status_code=202, response_model=IngestAcceptedResponse)
async def ingest_image(
    file: UploadFile,
    background_tasks: BackgroundTasks,
    auth: AuthContext = Depends(require_role("owner")),
    ai: AIServiceClient = Depends(get_ai_client),
) -> IngestAcceptedResponse:
    _validate_extension(file.filename or "", IMAGE_EXTENSIONS, "image")

    data = await file.read()
    if len(data) > IMAGE_MAX_SIZE:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Image exceeds {IMAGE_MAX_SIZE // (1024*1024)}MB limit",
        )

    result = await ai.ingest_image(auth.subject_id, data, file.filename or "image.jpg")
    background_tasks.add_task(_auto_persist, ai, result["task_id"], auth.subject_id)
    return IngestAcceptedResponse(task_id=result["task_id"])


# -- Task status polling --


@router.get("/tasks/{task_id}", response_model=TaskStatusResponse)
async def get_task_status(
    task_id: str,
    auth: AuthContext = Depends(require_auth),
    ai: AIServiceClient = Depends(get_ai_client),
    db: AsyncSession = Depends(get_db),
) -> TaskStatusResponse:
    """Poll task status from AI service.

    If the task is completed and has a result with entry_id, also persist the
    KnowledgeEntry to PostgreSQL if it doesn't exist yet.
    """
    task = await ai.get_task_status(task_id)

    if task.get("owner_id") != auth.subject_id:
        raise HTTPException(status_code=404, detail="Task not found")

    # Auto-persist completed entries to DB
    if task.get("status") == "completed" and task.get("result"):
        result = task["result"]
        entry_id = result.get("entry_id")
        if entry_id:
            existing = await db.execute(
                select(KnowledgeEntry).where(KnowledgeEntry.id == entry_id)
            )
            if existing.scalar_one_or_none() is None:
                # Infer content type from stored path
                ct = ContentType.text
                if result.get("original_content_path"):
                    path = result["original_content_path"]
                    if "/audio/" in path:
                        ct = ContentType.audio
                    elif "/video/" in path:
                        ct = ContentType.video
                    elif "/image/" in path:
                        ct = ContentType.image
                    elif "/document/" in path:
                        ct = ContentType.document

                entry = KnowledgeEntry(
                    id=entry_id,
                    owner_id=auth.subject_id,
                    content_type=ct,
                    original_content_path=result.get("original_content_path"),
                    original_language=result.get("language"),
                    english_translation=result.get("english_translation"),
                    embedding_id=result.get("embedding_id"),
                    category=result.get("category"),
                    metadata_=result.get("metadata"),
                )
                db.add(entry)
                await db.commit()

    return TaskStatusResponse(**task)


# -- Knowledge entries CRUD --


@router.get("/entries", response_model=KnowledgeListResponse)
async def list_entries(
    page: int = 1,
    page_size: int = 20,
    content_type: ContentType | None = None,
    auth: AuthContext = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
) -> KnowledgeListResponse:
    scope = await resolve_family_scope(auth, db)
    base_filter = KnowledgeEntry.owner_id == auth.subject_id
    if content_type is not None:
        base_filter = base_filter & (KnowledgeEntry.content_type == content_type)
    if scope.allowed_content_types is not None:
        base_filter = base_filter & (
            KnowledgeEntry.content_type.in_(scope.allowed_content_types)
        )
    if scope.allowed_categories is not None:
        base_filter = base_filter & (
            KnowledgeEntry.category.in_(scope.allowed_categories)
            | KnowledgeEntry.category.is_(None)
        )

    total_result = await db.execute(
        select(func.count(KnowledgeEntry.id)).where(base_filter)
    )
    total = total_result.scalar() or 0

    result = await db.execute(
        select(KnowledgeEntry)
        .where(base_filter)
        .order_by(KnowledgeEntry.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    entries = list(result.scalars().all())

    return KnowledgeListResponse(
        entries=[KnowledgeEntryResponse.model_validate(e) for e in entries],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/entries/{entry_id}", response_model=KnowledgeEntryResponse)
async def get_entry(
    entry_id: str,
    auth: AuthContext = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
) -> KnowledgeEntryResponse:
    result = await db.execute(
        select(KnowledgeEntry).where(
            KnowledgeEntry.id == entry_id,
            KnowledgeEntry.owner_id == auth.subject_id,
        )
    )
    entry = result.scalar_one_or_none()
    if entry is None:
        raise HTTPException(status_code=404, detail="Entry not found")

    scope = await resolve_family_scope(auth, db)
    entry_category = entry.category.value if entry.category else None
    if not scope.permits(entry.content_type.value, entry_category):
        raise HTTPException(status_code=403, detail="Not permitted to view this entry")

    return KnowledgeEntryResponse.model_validate(entry)


@router.get("/entries/{entry_id}/file", response_class=Response)
async def get_entry_file(
    entry_id: str,
    auth: AuthContext = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
    ai: AIServiceClient = Depends(get_ai_client),
) -> Response:
    """Stream the original uploaded file for a knowledge entry."""
    result = await db.execute(
        select(KnowledgeEntry).where(
            KnowledgeEntry.id == entry_id,
            KnowledgeEntry.owner_id == auth.subject_id,
        )
    )
    entry = result.scalar_one_or_none()
    if entry is None:
        raise HTTPException(status_code=404, detail="Entry not found")

    scope = await resolve_family_scope(auth, db)
    entry_category = entry.category.value if entry.category else None
    if not scope.permits(entry.content_type.value, entry_category):
        raise HTTPException(status_code=403, detail="Not permitted to view this entry")

    if not entry.original_content_path:
        raise HTTPException(status_code=404, detail="No file for this entry")

    try:
        data, mime = await ai.get_file_bytes(entry.original_content_path)
    except Exception:
        raise HTTPException(status_code=404, detail="File not available")

    filename = Path(entry.original_content_path).name
    return Response(
        content=data,
        media_type=mime or (mimetypes.guess_type(filename)[0] or "application/octet-stream"),
        headers={
            "Content-Disposition": f'inline; filename="{filename}"',
            "Cache-Control": "private, max-age=3600",
        },
    )


@router.delete("/entries/{entry_id}", status_code=204)
async def delete_entry(
    entry_id: str,
    auth: AuthContext = Depends(require_role("owner")),
    ai: AIServiceClient = Depends(get_ai_client),
    db: AsyncSession = Depends(get_db),
) -> None:
    result = await db.execute(
        select(KnowledgeEntry).where(
            KnowledgeEntry.id == entry_id,
            KnowledgeEntry.owner_id == auth.subject_id,
        )
    )
    entry = result.scalar_one_or_none()
    if entry is None:
        raise HTTPException(status_code=404, detail="Entry not found")

    # Delete vectors from AI service
    try:
        await ai.delete_vectors(entry_id)
    except Exception:
        pass  # Best-effort

    await db.delete(entry)
    await db.commit()
