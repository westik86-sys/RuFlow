#!/usr/bin/env python3
import contextlib
import json
import os
import sys
import time
import traceback
from pathlib import Path
from typing import Any


MODEL_NAME = "gigaam-v3-e2e-rnnt"


def duration_ms(started: float) -> int:
    return int((time.perf_counter() - started) * 1000)


def emit(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), flush=True)


def ok_payload(text: str, started: float) -> dict[str, Any]:
    return {
        "ok": True,
        "text": text,
        "duration_ms": duration_ms(started),
        "model": MODEL_NAME,
    }


def error_payload(message: str, started: float) -> dict[str, Any]:
    return {
        "ok": False,
        "error": message,
        "duration_ms": duration_ms(started),
        "model": MODEL_NAME,
    }


def normalize_text(result: Any) -> str:
    if isinstance(result, str):
        return result.strip()

    text = getattr(result, "text", None)
    if isinstance(text, str):
        return text.strip()

    if isinstance(result, (list, tuple)) and result:
        return normalize_text(result[0])

    return str(result).strip() if result is not None else ""


def user_facing_error(error: Exception) -> str:
    message = str(error) or error.__class__.__name__
    lower_message = message.lower()

    if "certificate_verify_failed" in lower_message or "self-signed certificate" in lower_message:
        return (
            "не удалось скачать модель с Hugging Face: SSL-сертификат не прошел проверку. "
            "Если это корпоративная сеть, добавьте корпоративный CA в Python trust store "
            "или для локального dev запустите с RUFLOW_HF_INSECURE=1."
        )

    if "cannot find the appropriate snapshot folder" in lower_message or "locate the files on the hub" in lower_message:
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
    sys.stdout.flush()
    sys.stderr.flush()
    saved_stdout_fd = os.dup(sys.stdout.fileno())

    try:
        os.dup2(sys.stderr.fileno(), sys.stdout.fileno())
        with contextlib.redirect_stdout(sys.stderr):
            yield
    finally:
        sys.stdout.flush()
        sys.stderr.flush()
        os.dup2(saved_stdout_fd, sys.stdout.fileno())
        os.close(saved_stdout_fd)


def recognize(wav_path: Path) -> str:
    with redirect_stdout_to_stderr():
        configure_huggingface()

        import onnx_asr

        model = onnx_asr.load_model(
            MODEL_NAME,
            providers=["CPUExecutionProvider"],
        )
        result = model.recognize(wav_path)

    return normalize_text(result)


def main() -> int:
    started = time.perf_counter()

    try:
        if len(sys.argv) != 2:
            emit(error_payload("usage: runner.py /absolute/path/to/audio.wav", started))
            return 0

        wav_path = Path(sys.argv[1]).expanduser()
        if not wav_path.is_file():
            emit(error_payload(f"audio file not found: {wav_path}", started))
            return 0

        text = recognize(wav_path)
        if not text:
            emit(error_payload("model returned empty transcript", started))
            return 0

        emit(ok_payload(text, started))
        return 0
    except Exception as error:
        traceback.print_exc(file=sys.stderr)
        emit(error_payload(user_facing_error(error), started))
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
