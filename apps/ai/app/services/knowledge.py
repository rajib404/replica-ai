import asyncio
import logging
import tempfile
import uuid
from pathlib import Path

import redis.asyncio as aioredis

from app.core.qdrant import QdrantService, get_qdrant
from app.core.storage import FileStorage, get_storage
from app.core.task_tracker import TaskStatus, update_task
from app.services.llm_engine import OllamaClient

logger = logging.getLogger(__name__)

CHUNK_SIZE = 2000
CHUNK_OVERLAP = 200


class KnowledgeIngestor:
    """Orchestrates knowledge ingestion: extract -> translate -> embed -> store.

    Unlike the apps/api version, this does NOT write to PostgreSQL.
    It stores vectors in Qdrant (with content_preview in payload) and files on disk,
    then returns result dicts that the caller (main API) uses to create DB records.
    """

    def __init__(
        self,
        ollama: OllamaClient | None = None,
        qdrant: QdrantService | None = None,
        storage: FileStorage | None = None,
    ) -> None:
        self.ollama = ollama or OllamaClient()
        self.qdrant = qdrant or get_qdrant()
        self.storage = storage or get_storage()

    # -- Private helpers --

    def _detect_language(self, text: str) -> str:
        try:
            from langdetect import detect

            return detect(text)
        except Exception:
            return "en"

    async def _translate_to_english(self, text: str, source_lang: str) -> str:
        prompt = (
            f"Translate the following {source_lang} text to English. "
            f"Output ONLY the translation, nothing else:\n\n{text}"
        )
        result = await self.ollama.generate_response(prompt, temperature=0.1)
        return result.get("response", text)

    async def _generate_and_store_embedding(
        self,
        text: str,
        entry_id: str,
        owner_id: str,
        content_type: str,
        language: str,
        chunk_index: int = 0,
        content_preview: str | None = None,
    ) -> str:
        vector = await self.ollama.generate_embedding(text)
        await self.qdrant.ensure_collection(vector_size=len(vector))
        point_id = await self.qdrant.upsert_embedding(
            entry_id=entry_id,
            vector=vector,
            owner_id=owner_id,
            content_type=content_type,
            language=language,
            chunk_index=chunk_index,
            content_preview=content_preview,
        )
        return point_id

    def _chunk_text(self, text: str) -> list[str]:
        if len(text) <= CHUNK_SIZE:
            return [text]
        chunks: list[str] = []
        start = 0
        while start < len(text):
            end = start + CHUNK_SIZE
            chunks.append(text[start:end])
            start = end - CHUNK_OVERLAP
        return chunks

    def _transcribe_audio(self, file_path: str) -> tuple[str, str]:
        from faster_whisper import WhisperModel

        model = WhisperModel("base", device="cpu", compute_type="int8")
        segments, info = model.transcribe(file_path)
        text = " ".join(seg.text.strip() for seg in segments)
        language = info.language or "en"
        return text, language

    async def _extract_audio_from_video(self, video_path: str, out_path: str) -> None:
        proc = await asyncio.create_subprocess_exec(
            "ffmpeg", "-i", video_path, "-vn", "-acodec", "pcm_s16le",
            "-ar", "16000", "-ac", "1", out_path, "-y",
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        await proc.wait()
        if proc.returncode != 0:
            raise RuntimeError(f"ffmpeg audio extraction failed (code {proc.returncode})")

    async def _extract_keyframes(self, video_path: str, out_dir: str) -> list[str]:
        Path(out_dir).mkdir(parents=True, exist_ok=True)
        pattern = str(Path(out_dir) / "frame_%04d.jpg")
        proc = await asyncio.create_subprocess_exec(
            "ffmpeg", "-i", video_path, "-vf", "fps=1/30", pattern, "-y",
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        await proc.wait()
        frames = sorted(Path(out_dir).glob("frame_*.jpg"))
        return [str(f) for f in frames]

    def _extract_document_text(self, data: bytes, filename: str) -> str:
        ext = Path(filename).suffix.lower()

        if ext in (".txt", ".csv"):
            return data.decode("utf-8", errors="replace")

        if ext == ".pdf":
            from PyPDF2 import PdfReader
            import io

            reader = PdfReader(io.BytesIO(data))
            return "\n".join(page.extract_text() or "" for page in reader.pages)

        if ext == ".docx":
            from docx import Document
            import io

            doc = Document(io.BytesIO(data))
            return "\n".join(para.text for para in doc.paragraphs)

        raise ValueError(f"Unsupported document format: {ext}")

    # -- Public methods (return result dicts, never write to DB) --

    async def ingest_text(
        self,
        owner_id: str,
        text: str,
        language: str | None = None,
        english_translation: str | None = None,
    ) -> dict:
        """Synchronous text ingestion. Returns result dict for the caller to persist.

        If ``english_translation`` is provided (pre-translated by LanguageEngine),
        inline detection/translation is skipped.
        """
        entry_id = str(uuid.uuid4())

        lang = language or self._detect_language(text)
        if english_translation and lang != "en":
            english = english_translation
        elif lang != "en":
            english = await self._translate_to_english(text, lang)
        else:
            english = text

        content_preview = english[:300]

        embedding_id = await self._generate_and_store_embedding(
            text=english,
            entry_id=entry_id,
            owner_id=owner_id,
            content_type="text",
            language=lang,
            content_preview=content_preview,
        )

        return {
            "entry_id": entry_id,
            "language": lang,
            "english_translation": english if lang != "en" else None,
            "embedding_id": embedding_id,
            "content_preview": content_preview,
            "metadata": {"original_text": text[:500]},
        }

    async def ingest_audio_background(
        self,
        owner_id: str,
        task_id: str,
        audio_bytes: bytes,
        filename: str,
        r: aioredis.Redis,
    ) -> None:
        """Background task for audio ingestion."""
        entry_id = str(uuid.uuid4())
        try:
            await update_task(r, task_id, status=TaskStatus.processing, progress=10)

            rel_path = self.storage.save_file(
                owner_id, "audio", entry_id, filename, audio_bytes
            )

            await update_task(r, task_id, progress=30)

            with tempfile.NamedTemporaryFile(suffix=Path(filename).suffix, delete=True) as tmp:
                tmp.write(audio_bytes)
                tmp.flush()
                text, lang = self._transcribe_audio(tmp.name)

            await update_task(r, task_id, progress=60)

            english = text
            if lang != "en":
                english = await self._translate_to_english(text, lang)

            content_preview = english[:300]

            await update_task(r, task_id, progress=80)

            embedding_id = await self._generate_and_store_embedding(
                text=english,
                entry_id=entry_id,
                owner_id=owner_id,
                content_type="audio",
                language=lang,
                content_preview=content_preview,
            )

            await update_task(
                r, task_id,
                status=TaskStatus.completed,
                progress=100,
                result={
                    "entry_id": entry_id,
                    "language": lang,
                    "english_translation": english if lang != "en" else None,
                    "embedding_id": embedding_id,
                    "content_preview": content_preview,
                    "original_content_path": rel_path,
                    "metadata": {"filename": filename, "transcript": text[:500]},
                },
            )
        except Exception as exc:
            logger.exception("Audio ingestion failed for task %s", task_id)
            await update_task(r, task_id, status=TaskStatus.failed, error=str(exc))

    async def ingest_video_background(
        self,
        owner_id: str,
        task_id: str,
        video_bytes: bytes,
        filename: str,
        r: aioredis.Redis,
    ) -> None:
        """Background task for video ingestion."""
        entry_id = str(uuid.uuid4())
        try:
            await update_task(r, task_id, status=TaskStatus.processing, progress=10)

            rel_path = self.storage.save_file(
                owner_id, "video", entry_id, filename, video_bytes
            )

            await update_task(r, task_id, progress=20)

            with tempfile.TemporaryDirectory() as tmpdir:
                video_tmp = str(Path(tmpdir) / filename)
                Path(video_tmp).write_bytes(video_bytes)

                audio_tmp = str(Path(tmpdir) / "audio.wav")
                await self._extract_audio_from_video(video_tmp, audio_tmp)

                await update_task(r, task_id, progress=40)

                text, lang = self._transcribe_audio(audio_tmp)

                await update_task(r, task_id, progress=60)

                frames_dir = str(Path(tmpdir) / "frames")
                keyframes = await self._extract_keyframes(video_tmp, frames_dir)
                for frame_path in keyframes:
                    frame_filename = Path(frame_path).name
                    frame_data = Path(frame_path).read_bytes()
                    self.storage.save_file(
                        owner_id, "video", entry_id, frame_filename, frame_data
                    )

            await update_task(r, task_id, progress=80)

            english = text
            if lang != "en":
                english = await self._translate_to_english(text, lang)

            content_preview = english[:300]

            embedding_id = await self._generate_and_store_embedding(
                text=english,
                entry_id=entry_id,
                owner_id=owner_id,
                content_type="video",
                language=lang,
                content_preview=content_preview,
            )

            await update_task(
                r, task_id,
                status=TaskStatus.completed,
                progress=100,
                result={
                    "entry_id": entry_id,
                    "language": lang,
                    "english_translation": english if lang != "en" else None,
                    "embedding_id": embedding_id,
                    "content_preview": content_preview,
                    "original_content_path": rel_path,
                    "metadata": {
                        "filename": filename,
                        "transcript": text[:500],
                        "keyframes": len(keyframes),
                    },
                },
            )
        except Exception as exc:
            logger.exception("Video ingestion failed for task %s", task_id)
            await update_task(r, task_id, status=TaskStatus.failed, error=str(exc))

    async def ingest_document_background(
        self,
        owner_id: str,
        task_id: str,
        file_bytes: bytes,
        filename: str,
        r: aioredis.Redis,
    ) -> None:
        """Background task for document ingestion."""
        entry_id = str(uuid.uuid4())
        try:
            await update_task(r, task_id, status=TaskStatus.processing, progress=10)

            rel_path = self.storage.save_file(
                owner_id, "document", entry_id, filename, file_bytes
            )

            await update_task(r, task_id, progress=30)

            text = self._extract_document_text(file_bytes, filename)
            lang = self._detect_language(text)

            await update_task(r, task_id, progress=50)

            english = text
            if lang != "en":
                english = await self._translate_to_english(text, lang)

            await update_task(r, task_id, progress=70)

            chunks = self._chunk_text(english)
            content_preview = english[:300]
            first_embedding_id: str | None = None

            for i, chunk in enumerate(chunks):
                eid = await self._generate_and_store_embedding(
                    text=chunk,
                    entry_id=entry_id,
                    owner_id=owner_id,
                    content_type="document",
                    language=lang,
                    chunk_index=i,
                    content_preview=content_preview if i == 0 else None,
                )
                if i == 0:
                    first_embedding_id = eid

            await update_task(r, task_id, progress=90)

            await update_task(
                r, task_id,
                status=TaskStatus.completed,
                progress=100,
                result={
                    "entry_id": entry_id,
                    "language": lang,
                    "english_translation": english[:5000] if lang != "en" else None,
                    "embedding_id": first_embedding_id,
                    "content_preview": content_preview,
                    "original_content_path": rel_path,
                    "metadata": {"filename": filename, "chunks": len(chunks), "chars": len(text)},
                },
            )
        except Exception as exc:
            logger.exception("Document ingestion failed for task %s", task_id)
            await update_task(r, task_id, status=TaskStatus.failed, error=str(exc))

    async def delete_vectors(self, entry_id: str) -> None:
        """Delete all vectors for a knowledge entry from Qdrant."""
        await self.qdrant.delete_by_entry_id(entry_id)

    def delete_files(self, owner_id: str, content_type: str, entry_id: str) -> None:
        """Delete stored files for a knowledge entry."""
        self.storage.delete_entry_files(owner_id, content_type, entry_id)
