"""Voice chat services: Speech-to-Text (STT) and Text-to-Speech (TTS).

STT uses faster-whisper running locally on CPU.
TTS uses Piper via the Wyoming protocol (Docker container).
"""

import asyncio
import io
import logging
import struct
import wave
from typing import AsyncGenerator

import numpy as np
import soundfile as sf
from faster_whisper import WhisperModel
from pydub import AudioSegment

from app.core.config import settings

logger = logging.getLogger(__name__)

# ─── Audio helpers ────────────────────────────────────────


def _convert_to_wav_16k(audio_bytes: bytes, input_format: str = "webm") -> np.ndarray:
    """Convert any supported audio format to 16kHz mono float32 numpy array."""
    try:
        seg = AudioSegment.from_file(io.BytesIO(audio_bytes), format=input_format)
    except Exception:
        # Fallback: try raw detection
        seg = AudioSegment.from_file(io.BytesIO(audio_bytes))

    # Convert to mono 16kHz
    seg = seg.set_channels(1).set_frame_rate(settings.stt_sample_rate)

    # Export as WAV and read with soundfile
    wav_buf = io.BytesIO()
    seg.export(wav_buf, format="wav")
    wav_buf.seek(0)
    data, _ = sf.read(wav_buf, dtype="float32")
    return data


def _reduce_noise(audio: np.ndarray, sr: int) -> np.ndarray:
    """Apply noise reduction. Fails gracefully if noisereduce not available."""
    try:
        import noisereduce as nr
        return nr.reduce_noise(y=audio, sr=sr, prop_decrease=0.6)
    except ImportError:
        logger.warning("noisereduce not installed, skipping noise reduction")
        return audio
    except Exception:
        logger.exception("Noise reduction failed, using original audio")
        return audio


def _numpy_to_wav_bytes(audio: np.ndarray, sample_rate: int) -> bytes:
    """Convert float32 numpy array to WAV bytes (16-bit PCM)."""
    # Clip and convert to int16
    audio_int16 = np.clip(audio * 32767, -32768, 32767).astype(np.int16)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(audio_int16.tobytes())
    return buf.getvalue()


def _wav_to_mp3_bytes(wav_bytes: bytes) -> bytes:
    """Convert WAV bytes to MP3 bytes using pydub."""
    seg = AudioSegment.from_wav(io.BytesIO(wav_bytes))
    buf = io.BytesIO()
    seg.export(buf, format="mp3", bitrate="64k")
    return buf.getvalue()


# ─── STT: RealTimeSTT ────────────────────────────────────


class RealTimeSTT:
    """Speech-to-Text using faster-whisper on CPU."""

    _model: WhisperModel | None = None

    @classmethod
    def _get_model(cls) -> WhisperModel:
        if cls._model is None:
            logger.info(
                "Loading faster-whisper model: %s (%s)",
                settings.stt_model_size,
                settings.stt_compute_type,
            )
            cls._model = WhisperModel(
                settings.stt_model_size,
                device="cpu",
                compute_type=settings.stt_compute_type,
            )
        return cls._model

    @classmethod
    async def transcribe_file(
        cls,
        audio_bytes: bytes,
        input_format: str = "webm",
        language: str | None = None,
    ) -> dict:
        """Transcribe a complete audio file.

        Returns dict with keys: text, language, segments, duration.
        """
        loop = asyncio.get_event_loop()

        def _do_transcribe() -> dict:
            # Convert to 16kHz mono
            audio = _convert_to_wav_16k(audio_bytes, input_format)

            # Noise reduction
            audio = _reduce_noise(audio, settings.stt_sample_rate)

            model = cls._get_model()
            segments, info = model.transcribe(
                audio,
                language=language,
                beam_size=5,
                vad_filter=True,
                vad_parameters={"threshold": settings.voice_vad_threshold},
            )

            seg_list = []
            full_text = ""
            for segment in segments:
                seg_list.append({
                    "start": segment.start,
                    "end": segment.end,
                    "text": segment.text.strip(),
                })
                full_text += segment.text

            return {
                "text": full_text.strip(),
                "language": info.language,
                "language_probability": info.language_probability,
                "duration": info.duration,
                "segments": seg_list,
            }

        return await loop.run_in_executor(None, _do_transcribe)

    @classmethod
    async def transcribe_stream(
        cls,
        audio_chunks: list[bytes],
        input_format: str = "webm",
        language: str | None = None,
    ) -> AsyncGenerator[dict, None]:
        """Transcribe accumulated audio chunks, yielding partial results.

        For push-to-talk: accumulate chunks, then call with is_final=True.
        Yields dicts: {"text": str, "is_final": bool, "confidence": float}
        """
        if not audio_chunks:
            return

        # Combine all chunks into single audio
        combined = b"".join(audio_chunks)

        # Transcribe the combined audio
        result = await cls.transcribe_file(combined, input_format, language)

        # Yield the final result
        yield {
            "text": result["text"],
            "is_final": True,
            "confidence": result.get("language_probability", 0.0),
        }


# ─── TTS: TTSEngine ──────────────────────────────────────

# Available voices (built-in with Piper Wyoming container)
PIPER_VOICES = [
    {
        "voice_id": "en_US-lessac-medium",
        "name": "Lessac (US English)",
        "language": "en",
        "gender": "male",
        "description": "Clear American English male voice",
    },
    {
        "voice_id": "en_US-amy-medium",
        "name": "Amy (US English)",
        "language": "en",
        "gender": "female",
        "description": "Warm American English female voice",
    },
    {
        "voice_id": "en_GB-alba-medium",
        "name": "Alba (British English)",
        "language": "en",
        "gender": "female",
        "description": "British English female voice",
    },
    {
        "voice_id": "es_ES-sharvard-medium",
        "name": "Sharvard (Spanish)",
        "language": "es",
        "gender": "male",
        "description": "Spanish male voice",
    },
    {
        "voice_id": "fr_FR-siwis-medium",
        "name": "Siwis (French)",
        "language": "fr",
        "gender": "female",
        "description": "French female voice",
    },
    {
        "voice_id": "de_DE-thorsten-medium",
        "name": "Thorsten (German)",
        "language": "de",
        "gender": "male",
        "description": "German male voice",
    },
    {
        "voice_id": "zh_CN-huayan-medium",
        "name": "Huayan (Chinese)",
        "language": "zh",
        "gender": "female",
        "description": "Mandarin Chinese female voice",
    },
]


class TTSEngine:
    """Text-to-Speech using Piper via the Wyoming protocol."""

    @staticmethod
    def list_voices() -> list[dict]:
        """Return available TTS voices."""
        return PIPER_VOICES

    @staticmethod
    async def synthesize(
        text: str,
        voice_id: str | None = None,
        speed: float = 1.0,
        output_format: str = "mp3",
    ) -> dict:
        """Synthesize text to audio using Piper via Wyoming protocol.

        Returns dict with keys: audio_bytes, format, sample_rate, duration_ms.
        """
        voice = voice_id or settings.tts_default_voice

        try:
            audio_bytes = await _piper_wyoming_synthesize(text, voice)
        except Exception:
            logger.exception("Piper TTS failed, using fallback silence")
            # Return 1 second of silence as fallback
            silence = np.zeros(settings.tts_sample_rate, dtype=np.float32)
            audio_bytes = _numpy_to_wav_bytes(silence, settings.tts_sample_rate)

        # Apply speed adjustment if not 1.0
        if speed != 1.0 and 0.5 <= speed <= 2.0:
            try:
                seg = AudioSegment.from_wav(io.BytesIO(audio_bytes))
                # Change speed by adjusting frame rate then converting back
                adjusted = seg._spawn(
                    seg.raw_data,
                    overrides={"frame_rate": int(seg.frame_rate * speed)},
                )
                adjusted = adjusted.set_frame_rate(seg.frame_rate)
                wav_buf = io.BytesIO()
                adjusted.export(wav_buf, format="wav")
                audio_bytes = wav_buf.getvalue()
            except Exception:
                logger.exception("Speed adjustment failed, using original")

        # Calculate duration
        try:
            seg = AudioSegment.from_wav(io.BytesIO(audio_bytes))
            duration_ms = len(seg)
        except Exception:
            duration_ms = 0

        # Convert to requested output format
        if output_format == "mp3":
            final_bytes = _wav_to_mp3_bytes(audio_bytes)
        else:
            final_bytes = audio_bytes

        return {
            "audio_bytes": final_bytes,
            "format": output_format,
            "sample_rate": settings.tts_sample_rate,
            "duration_ms": duration_ms,
        }


async def _piper_wyoming_synthesize(text: str, voice: str) -> bytes:
    """Speak text via Piper's Wyoming protocol (TCP).

    Wyoming protocol:
    1. Send a Synthesize event with the text
    2. Receive AudioStart, AudioChunk(s), AudioStop events
    3. Combine audio chunks into WAV
    """
    reader, writer = await asyncio.open_connection(
        settings.piper_host, settings.piper_port
    )

    try:
        # Send synthesize request as Wyoming JSON event
        synth_event = {
            "type": "synthesize",
            "data": {"text": text, "voice": {"name": voice}},
        }
        await _wyoming_write_event(writer, synth_event)

        # Read response events
        audio_chunks: list[bytes] = []
        sample_rate = settings.tts_sample_rate
        sample_width = 2  # 16-bit
        channels = 1

        while True:
            event = await _wyoming_read_event(reader)
            if event is None:
                break

            event_type = event.get("type", "")

            if event_type == "audio-start":
                rate_info = event.get("data", {}).get("rate", settings.tts_sample_rate)
                if rate_info:
                    sample_rate = int(rate_info)
                width_info = event.get("data", {}).get("width", 2)
                if width_info:
                    sample_width = int(width_info)
                channels_info = event.get("data", {}).get("channels", 1)
                if channels_info:
                    channels = int(channels_info)

            elif event_type == "audio-chunk":
                payload = event.get("payload")
                if payload:
                    audio_chunks.append(payload)

            elif event_type == "audio-stop":
                break

        # Combine into WAV
        combined = b"".join(audio_chunks)
        buf = io.BytesIO()
        with wave.open(buf, "wb") as wf:
            wf.setnchannels(channels)
            wf.setsampwidth(sample_width)
            wf.setframerate(sample_rate)
            wf.writeframes(combined)

        return buf.getvalue()

    finally:
        writer.close()
        await writer.wait_closed()


async def _wyoming_write_event(writer: asyncio.StreamWriter, event: dict) -> None:
    """Write a Wyoming protocol event."""
    import json

    event_json = json.dumps(event).encode("utf-8")
    # Wyoming uses: header line (JSON) + newline + optional binary payload
    header = json.dumps({
        "type": event["type"],
        "data": event.get("data"),
        "data_length": 0,
        "payload_length": 0,
    }).encode("utf-8")
    writer.write(header + b"\n")
    await writer.drain()


async def _wyoming_read_event(reader: asyncio.StreamReader) -> dict | None:
    """Read a Wyoming protocol event."""
    import json

    try:
        header_line = await asyncio.wait_for(reader.readline(), timeout=30.0)
    except (asyncio.TimeoutError, ConnectionError):
        return None

    if not header_line:
        return None

    try:
        header = json.loads(header_line.decode("utf-8").strip())
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None

    payload_length = header.get("payload_length", 0)
    payload = None
    if payload_length > 0:
        payload = await reader.readexactly(payload_length)

    return {
        "type": header.get("type", ""),
        "data": header.get("data"),
        "payload": payload,
    }
