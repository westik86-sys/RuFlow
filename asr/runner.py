#!/usr/bin/env python3
import contextlib
import json
import os
import re
import sys
import tempfile
import time
import traceback
import wave
from pathlib import Path
from typing import Any


DEFAULT_MODEL_NAME = "gigaam-v3-e2e-rnnt"
MODEL_NAME = DEFAULT_MODEL_NAME
DEFAULT_ASR_CHUNK_SECONDS = 25.0
DASH_SPACING_RE = re.compile(r"\s*—\s*")


def duration_ms(started: float) -> int:
    return int((time.perf_counter() - started) * 1000)


def emit(payload: dict[str, Any]) -> None:
    stream = sys.stdout if sys.stdout is not None else sys.stderr
    if stream is None:
        return
    print(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), file=stream, flush=True)


def selected_model_name() -> str:
    return os.environ.get("RUFLOW_ASR_MODEL", DEFAULT_MODEL_NAME).strip() or DEFAULT_MODEL_NAME


def ok_payload(text: str, started: float, model_name: str | None = None) -> dict[str, Any]:
    return {
        "ok": True,
        "text": text,
        "duration_ms": duration_ms(started),
        "model": model_name or selected_model_name(),
    }


def error_payload(message: str, started: float, model_name: str | None = None) -> dict[str, Any]:
    return {
        "ok": False,
        "error": message,
        "duration_ms": duration_ms(started),
        "model": model_name or selected_model_name(),
    }


def normalize_transcript_text(text: str) -> str:
    return DASH_SPACING_RE.sub(" — ", text.strip()).strip()


def normalize_text(result: Any) -> str:
    if isinstance(result, str):
        return normalize_transcript_text(result)

    text = getattr(result, "text", None)
    if isinstance(text, str):
        return normalize_transcript_text(text)

    if isinstance(result, (list, tuple)):
        return normalize_transcript_text(" ".join(part for part in (normalize_text(item) for item in result) if part))

    return normalize_transcript_text(str(result)) if result is not None else ""


def selected_chunk_seconds() -> float:
    raw_value = os.environ.get("RUFLOW_ASR_CHUNK_SECONDS", str(DEFAULT_ASR_CHUNK_SECONDS)).strip()
    try:
        return max(0.0, float(raw_value))
    except ValueError:
        return DEFAULT_ASR_CHUNK_SECONDS


def split_wav_for_asr(wav_path: Path, chunk_seconds: float, chunks_dir: Path) -> list[Path]:
    if chunk_seconds <= 0:
        return [wav_path]

    with wave.open(str(wav_path), "rb") as source:
        framerate = int(source.getframerate())
        frame_count = int(source.getnframes())
        if framerate <= 0 or frame_count <= 0:
            return [wav_path]

        frames_per_chunk = max(1, int(framerate * chunk_seconds))
        if frame_count <= frames_per_chunk:
            return [wav_path]

        channels = source.getnchannels()
        sample_width = source.getsampwidth()
        compression_type = source.getcomptype()
        compression_name = source.getcompname()
        chunk_paths: list[Path] = []
        chunk_index = 0

        while True:
            frames = source.readframes(frames_per_chunk)
            if not frames:
                break

            chunk_path = chunks_dir / f"{wav_path.stem}-chunk-{chunk_index:04d}.wav"
            with wave.open(str(chunk_path), "wb") as chunk:
                chunk.setnchannels(channels)
                chunk.setsampwidth(sample_width)
                chunk.setframerate(framerate)
                chunk.setcomptype(compression_type, compression_name)
                chunk.writeframes(frames)

            chunk_paths.append(chunk_path)
            chunk_index += 1

    return chunk_paths or [wav_path]


def user_facing_error(error: Exception) -> str:
    message = str(error) or error.__class__.__name__
    lower_message = message.lower()

    if "certificate_verify_failed" in lower_message or "self-signed certificate" in lower_message:
        return (
            "не удалось скачать модель с Hugging Face: SSL-сертификат не прошел проверку. "
            "Если это корпоративная сеть, добавьте корпоративный CA в Python trust store "
            "или для локального dev запустите с RUFLOW_HF_INSECURE=1."
        )

    if (
        "cannot find the appropriate snapshot folder" in lower_message
        or "cannot find an appropriate cached snapshot folder" in lower_message
        or "locate the files on the hub" in lower_message
    ):
        return (
            "модель еще не скачана и Hugging Face недоступен. "
            "Проверьте интернет или заранее скачайте модель."
        )

    if "connecterror" in lower_message or "connection" in lower_message:
        return "не удалось подключиться к Hugging Face для загрузки модели. Проверьте интернет и proxy/SSL."

    return message


def configure_huggingface() -> None:
    if os.environ.get("RUFLOW_HF_INSECURE") != "1":
        return

    import httpx
    import huggingface_hub

    huggingface_hub.set_client_factory(lambda: httpx.Client(verify=False))


@contextlib.contextmanager
def redirect_stdout_to_stderr():
    stdout = sys.stdout
    stderr = sys.stderr
    if stdout is None or stderr is None:
        fallback = stderr or stdout
        if fallback is None:
            with open(os.devnull, "w", encoding="utf-8") as null_stream:
                with contextlib.redirect_stdout(null_stream), contextlib.redirect_stderr(null_stream):
                    yield
        else:
            with contextlib.redirect_stdout(fallback), contextlib.redirect_stderr(fallback):
                yield
        return

    try:
        stdout.flush()
        stderr.flush()
        stdout_fd = stdout.fileno()
        stderr_fd = stderr.fileno()
        saved_stdout_fd = os.dup(stdout_fd)
    except Exception:
        with contextlib.redirect_stdout(stderr):
            yield
        return

    try:
        os.dup2(stderr_fd, stdout_fd)
        with contextlib.redirect_stdout(stderr):
            yield
    finally:
        stdout.flush()
        stderr.flush()
        os.dup2(saved_stdout_fd, stdout_fd)
        os.close(saved_stdout_fd)


def recognize(wav_path: Path, model_name: str | None = None) -> str:
    model_name = model_name or selected_model_name()
    chunk_seconds = selected_chunk_seconds()

    with redirect_stdout_to_stderr():
        configure_huggingface()

        import onnx_asr

        model_path = os.environ.get("RUFLOW_GIGAAM_MODEL_DIR")
        model_path_arg = str(Path(model_path).expanduser()) if model_path else None
        model = onnx_asr.load_model(
            model_name,
            path=model_path_arg,
            providers=["CPUExecutionProvider"],
        )
        with tempfile.TemporaryDirectory(prefix="ruflow-asr-chunks-") as tmp:
            chunks = split_wav_for_asr(wav_path, chunk_seconds, Path(tmp))
            result = model.recognize(chunks) if len(chunks) > 1 else model.recognize(chunks[0])

    return normalize_text(result)


def main() -> int:
    started = time.perf_counter()
    model_name = selected_model_name()

    try:
        if len(sys.argv) != 2:
            emit(error_payload("usage: runner.py /absolute/path/to/audio.wav", started, model_name))
            return 0

        wav_path = Path(sys.argv[1]).expanduser()
        if not wav_path.is_file():
            emit(error_payload(f"audio file not found: {wav_path}", started, model_name))
            return 0

        text = recognize(wav_path, model_name)
        if not text:
            emit(error_payload("model returned empty transcript", started, model_name))
            return 0

        emit(ok_payload(text, started, model_name))
        return 0
    except Exception as error:
        if sys.stderr is not None:
            traceback.print_exc(file=sys.stderr)
        emit(error_payload(user_facing_error(error), started, model_name))
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
