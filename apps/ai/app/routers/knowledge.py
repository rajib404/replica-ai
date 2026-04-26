import asyncio
import mimetypes
import tempfile
import uuid
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, UploadFile, status
from fastapi.responses import Response
from pydantic import BaseModel
import redis.asyncio as aioredis

from app.core.redis import get_redis
from app.core.storage import get_storage
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
IMAGE_MAX_SIZE = 10 * 1024 * 1024  # 10 MB
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".heic", ".heif"}

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


# -- Image ingest (background) --


@router.post("/ingest/image", status_code=202, response_model=IngestAcceptedResponse)
async def ingest_image(
    owner_id: str,
    file: UploadFile,
    background_tasks: BackgroundTasks,
    r: aioredis.Redis = Depends(get_redis),
) -> IngestAcceptedResponse:
    """Async: save image file, generate embedding from filename+metadata. Returns task_id."""
    _validate_extension(file.filename or "", IMAGE_EXTENSIONS, "image")

    data = await file.read()
    if len(data) > IMAGE_MAX_SIZE:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Image exceeds {IMAGE_MAX_SIZE // (1024*1024)}MB limit",
        )

    task_id = str(uuid.uuid4())
    await create_task(r, task_id, owner_id)

    background_tasks.add_task(
        _ingestor.ingest_image_background,
        owner_id, task_id, data, file.filename or "image.jpg", r,
    )
    return IngestAcceptedResponse(task_id=task_id)


# -- Synchronous transcription --


class TranscribeResponse(BaseModel):
    text: str
    language: str


@router.post("/transcribe", response_model=TranscribeResponse)
async def transcribe_audio(file: UploadFile) -> TranscribeResponse:
    """Synchronous: transcribe audio and return the text + detected language."""
    _validate_extension(file.filename or "", AUDIO_EXTENSIONS, "audio")

    data = await file.read()
    if len(data) > AUDIO_MAX_SIZE:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Audio file exceeds {AUDIO_MAX_SIZE // (1024 * 1024)}MB limit",
        )

    suffix = Path(file.filename or "audio.m4a").suffix or ".m4a"
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp.write(data)
        tmp_path = tmp.name

    try:
        loop = asyncio.get_event_loop()
        text, language = await loop.run_in_executor(None, _ingestor._transcribe_audio, tmp_path)
    finally:
        Path(tmp_path).unlink(missing_ok=True)

    return TranscribeResponse(text=text, language=language)


# -- File serving (internal — called by API service, not exposed to internet) --


@router.get("/storage/{path:path}", response_class=Response)
async def serve_storage_file(path: str) -> Response:
    """Serve a stored file by its relative path. Internal use only."""
    storage = get_storage()
    # Guard against path traversal
    base = (storage._base).resolve()
    target = (base / path).resolve()
    if not str(target).startswith(str(base)):
        raise HTTPException(status_code=400, detail="Invalid path")
    try:
        data = storage.read_file(path)
    except (FileNotFoundError, OSError):
        raise HTTPException(status_code=404, detail="File not found")
    mime_type = mimetypes.guess_type(path)[0] or "application/octet-stream"
    filename = Path(path).name
    return Response(
        content=data,
        media_type=mime_type,
        headers={"Content-Disposition": f'inline; filename="{filename}"'},
    )


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
