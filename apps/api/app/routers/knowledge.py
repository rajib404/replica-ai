from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, UploadFile, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.ai_client import AIServiceClient, get_ai_client
from app.core.auth_guard import AuthContext, require_auth
from app.core.database import get_db
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

router = APIRouter(prefix="/api/knowledge", tags=["knowledge"])

# Size limits
AUDIO_MAX_SIZE = 50 * 1024 * 1024  # 50 MB
VIDEO_MAX_SIZE = 500 * 1024 * 1024  # 500 MB
DOC_MAX_SIZE = 20 * 1024 * 1024  # 20 MB

AUDIO_EXTENSIONS = {".wav", ".mp3", ".m4a", ".ogg", ".flac", ".webm"}
VIDEO_EXTENSIONS = {".mp4", ".mov", ".avi", ".mkv", ".webm"}
DOC_EXTENSIONS = {".pdf", ".docx", ".txt", ".csv"}


def _validate_extension(filename: str, allowed: set[str], label: str) -> None:
    ext = Path(filename).suffix.lower()
    if ext not in allowed:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported {label} format '{ext}'. Allowed: {', '.join(sorted(allowed))}",
        )


# -- Text ingest (synchronous) --


@router.post("/text", status_code=201, response_model=IngestCompletedResponse)
async def ingest_text(
    body: TextIngestRequest,
    auth: AuthContext = Depends(require_auth),
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
        metadata_=result.get("metadata"),
    )
    db.add(entry)
    await db.commit()

    return IngestCompletedResponse(entry_id=result["entry_id"])


# -- Audio ingest (background via AI service) --


@router.post("/audio", status_code=202, response_model=IngestAcceptedResponse)
async def ingest_audio(
    file: UploadFile,
    auth: AuthContext = Depends(require_auth),
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
    return IngestAcceptedResponse(task_id=result["task_id"])


# -- Video ingest (background via AI service) --


@router.post("/video", status_code=202, response_model=IngestAcceptedResponse)
async def ingest_video(
    file: UploadFile,
    auth: AuthContext = Depends(require_auth),
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
    return IngestAcceptedResponse(task_id=result["task_id"])


# -- Document ingest (background via AI service) --


@router.post("/document", status_code=202, response_model=IngestAcceptedResponse)
async def ingest_document(
    file: UploadFile,
    auth: AuthContext = Depends(require_auth),
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
                content_type_str = result.get("metadata", {}).get("filename", "")
                # Infer content type from task context
                ct = ContentType.text
                if result.get("original_content_path"):
                    path = result["original_content_path"]
                    if "/audio/" in path:
                        ct = ContentType.audio
                    elif "/video/" in path:
                        ct = ContentType.video
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
    base_filter = KnowledgeEntry.owner_id == auth.subject_id
    if content_type is not None:
        base_filter = base_filter & (KnowledgeEntry.content_type == content_type)

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
    return KnowledgeEntryResponse.model_validate(entry)


@router.delete("/entries/{entry_id}", status_code=204)
async def delete_entry(
    entry_id: str,
    auth: AuthContext = Depends(require_auth),
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
