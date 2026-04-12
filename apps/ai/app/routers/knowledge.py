import uuid
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, UploadFile, status
import redis.asyncio as aioredis

from app.core.redis import get_redis
from app.core.task_tracker import create_task, get_task
from app.models.knowledge import (
    IngestAcceptedResponse,
    IngestResult,
    TaskStatusResponse,
    TextIngestRequest,
)
from app.services.knowledge import KnowledgeIngestor

router = APIRouter()

# Size limits
AUDIO_MAX_SIZE = 50 * 1024 * 1024  # 50 MB
VIDEO_MAX_SIZE = 500 * 1024 * 1024  # 500 MB
DOC_MAX_SIZE = 20 * 1024 * 1024  # 20 MB

AUDIO_EXTENSIONS = {".wav", ".mp3", ".m4a", ".ogg", ".flac", ".webm"}
VIDEO_EXTENSIONS = {".mp4", ".mov", ".avi", ".mkv", ".webm"}
DOC_EXTENSIONS = {".pdf", ".docx", ".txt", ".csv"}

_ingestor = KnowledgeIngestor()


def _validate_extension(filename: str, allowed: set[str], label: str) -> None:
    ext = Path(filename).suffix.lower()
    if ext not in allowed:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported {label} format '{ext}'. Allowed: {', '.join(sorted(allowed))}",
        )


# -- Text ingest (synchronous) --


@router.post("/ingest/text", status_code=201, response_model=IngestResult)
async def ingest_text(body: TextIngestRequest) -> IngestResult:
    """Sync: detect lang, translate, embed, store in Qdrant. Returns processed result."""
    result = await _ingestor.ingest_text(
        owner_id=body.owner_id,
        text=body.text,
        language=body.language,
        english_translation=body.english_translation,
    )
    return IngestResult(**result)


# -- Audio ingest (background) --


@router.post("/ingest/audio", status_code=202, response_model=IngestAcceptedResponse)
async def ingest_audio(
    owner_id: str,
    file: UploadFile,
    background_tasks: BackgroundTasks,
    r: aioredis.Redis = Depends(get_redis),
) -> IngestAcceptedResponse:
    """Async: transcribe, translate, embed, store. Returns task_id."""
    _validate_extension(file.filename or "", AUDIO_EXTENSIONS, "audio")

    data = await file.read()
    if len(data) > AUDIO_MAX_SIZE:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Audio file exceeds {AUDIO_MAX_SIZE // (1024*1024)}MB limit",
        )

    task_id = str(uuid.uuid4())
    await create_task(r, task_id, owner_id)

    background_tasks.add_task(
        _ingestor.ingest_audio_background,
        owner_id, task_id, data, file.filename or "audio", r,
    )
    return IngestAcceptedResponse(task_id=task_id)


# -- Video ingest (background) --


@router.post("/ingest/video", status_code=202, response_model=IngestAcceptedResponse)
async def ingest_video(
    owner_id: str,
    file: UploadFile,
    background_tasks: BackgroundTasks,
    r: aioredis.Redis = Depends(get_redis),
) -> IngestAcceptedResponse:
    """Async: extract audio, transcribe, keyframes, embed, store. Returns task_id."""
    _validate_extension(file.filename or "", VIDEO_EXTENSIONS, "video")

    data = await file.read()
    if len(data) > VIDEO_MAX_SIZE:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Video file exceeds {VIDEO_MAX_SIZE // (1024*1024)}MB limit",
        )

    task_id = str(uuid.uuid4())
    await create_task(r, task_id, owner_id)

    background_tasks.add_task(
        _ingestor.ingest_video_background,
        owner_id, task_id, data, file.filename or "video", r,
    )
    return IngestAcceptedResponse(task_id=task_id)


# -- Document ingest (background) --


@router.post("/ingest/document", status_code=202, response_model=IngestAcceptedResponse)
async def ingest_document(
    owner_id: str,
    file: UploadFile,
    background_tasks: BackgroundTasks,
    r: aioredis.Redis = Depends(get_redis),
) -> IngestAcceptedResponse:
    """Async: extract text, chunk, translate, embed, store. Returns task_id."""
    _validate_extension(file.filename or "", DOC_EXTENSIONS, "document")

    data = await file.read()
    if len(data) > DOC_MAX_SIZE:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Document exceeds {DOC_MAX_SIZE // (1024*1024)}MB limit",
        )

    task_id = str(uuid.uuid4())
    await create_task(r, task_id, owner_id)

    background_tasks.add_task(
        _ingestor.ingest_document_background,
        owner_id, task_id, data, file.filename or "document", r,
    )
    return IngestAcceptedResponse(task_id=task_id)


# -- Task status polling --


@router.get("/tasks/{task_id}", response_model=TaskStatusResponse)
async def get_task_status(
    task_id: str,
    r: aioredis.Redis = Depends(get_redis),
) -> TaskStatusResponse:
    """Poll background task status."""
    task = await get_task(r, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    return TaskStatusResponse(**task)
