#!/usr/bin/env python3
import contextlib
import json
import os
import re
import sys
import time
import traceback
from pathlib import Path
from typing import Any


MODEL_NAME = "gigaam-v3-e2e-rnnt"
DASH_SPACING_RE = re.compile(r"\s*—\s*")
TERM_SEPARATOR_RE = r"(?:\s+|\s*[-—]\s*)"


def term_re(*variants: str) -> re.Pattern[str]:
    return re.compile(r"(?<!\w)(?:" + "|".join(variants) + r")(?!\w)", re.IGNORECASE)


TERM_REPLACEMENTS = [
    # Common technical abbreviations and formats.
    (
        term_re(
            "ллм",
            rf"л{TERM_SEPARATOR_RE}л{TERM_SEPARATOR_RE}м",
            rf"эл{TERM_SEPARATOR_RE}эл{TERM_SEPARATOR_RE}эм",
            rf"эль{TERM_SEPARATOR_RE}эль{TERM_SEPARATOR_RE}эм",
            "элэлэм",
            "эльэльэм",
        ),
        "LLM",
    ),
    (term_re("апи", rf"а{TERM_SEPARATOR_RE}пи{TERM_SEPARATOR_RE}ай", rf"эй{TERM_SEPARATOR_RE}пи{TERM_SEPARATOR_RE}ай", "api"), "API"),
    (term_re("джейсон", "джсон", "жсон", "json"), "JSON"),
    (term_re("ямл", "ямэл", "yaml"), "YAML"),
    (term_re(rf"икс{TERM_SEPARATOR_RE}эм{TERM_SEPARATOR_RE}эл", rf"экс{TERM_SEPARATOR_RE}эм{TERM_SEPARATOR_RE}эл", "xml"), "XML"),
    (term_re(rf"эйч{TERM_SEPARATOR_RE}ти{TERM_SEPARATOR_RE}ти{TERM_SEPARATOR_RE}пи{TERM_SEPARATOR_RE}эс", "хттпс", "https"), "HTTPS"),
    (term_re(rf"эйч{TERM_SEPARATOR_RE}ти{TERM_SEPARATOR_RE}ти{TERM_SEPARATOR_RE}пи", "хттп", "http"), "HTTP"),
    (term_re("урл", rf"ю{TERM_SEPARATOR_RE}эр{TERM_SEPARATOR_RE}эл", "url"), "URL"),
    (term_re(rf"эс{TERM_SEPARATOR_RE}ди{TERM_SEPARATOR_RE}кей", "сдк", "sdk"), "SDK"),
    (term_re(rf"си{TERM_SEPARATOR_RE}эл{TERM_SEPARATOR_RE}ай", "кли", "cli"), "CLI"),
    (term_re(rf"джей{TERM_SEPARATOR_RE}дабл{TERM_SEPARATOR_RE}ю{TERM_SEPARATOR_RE}ти", rf"джей{TERM_SEPARATOR_RE}даблью{TERM_SEPARATOR_RE}ти", "джвт", "jwt"), "JWT"),
    (term_re(rf"о{TERM_SEPARATOR_RE}аус", rf"оу{TERM_SEPARATOR_RE}аус", "оаут", "oauth"), "OAuth"),
    (term_re("рест", "rest"), "REST"),
    (term_re(rf"граф{TERM_SEPARATOR_RE}кью{TERM_SEPARATOR_RE}эл", "графкуэл", "graphql"), "GraphQL"),
    # AI products and tooling.
    (term_re(rf"оупен{TERM_SEPARATOR_RE}ай", rf"опен{TERM_SEPARATOR_RE}ай", rf"open{TERM_SEPARATOR_RE}ai", "openai"), "OpenAI"),
    (term_re(rf"чат{TERM_SEPARATOR_RE}жпт", rf"чат{TERM_SEPARATOR_RE}гпт", rf"chat{TERM_SEPARATOR_RE}gpt", "chatgpt"), "ChatGPT"),
    (term_re("жпт", "гпт", rf"джи{TERM_SEPARATOR_RE}пи{TERM_SEPARATOR_RE}ти", "gpt"), "GPT"),
    (term_re("клод", "claude"), "Claude"),
    (term_re("антропик", "anthropic"), "Anthropic"),
    (term_re("джемини", "gemini"), "Gemini"),
    (term_re("копайлот", rf"ко{TERM_SEPARATOR_RE}пилот", "copilot"), "Copilot"),
    (term_re("курсор", "cursor"), "Cursor"),
    (term_re("виспер", "whisper"), "Whisper"),
    (term_re(rf"хаггинг{TERM_SEPARATOR_RE}фейс", rf"хагинг{TERM_SEPARATOR_RE}фейс", rf"hugging{TERM_SEPARATOR_RE}face"), "Hugging Face"),
    (term_re(rf"ланг{TERM_SEPARATOR_RE}чейн", rf"лэнг{TERM_SEPARATOR_RE}чейн", "langchain"), "LangChain"),
    (term_re("раг", "рэг", rf"эр{TERM_SEPARATOR_RE}эй{TERM_SEPARATOR_RE}джи", "rag"), "RAG"),
    # Development platforms, infrastructure, and databases.
    (term_re(rf"гитхаб{TERM_SEPARATOR_RE}экшены", rf"github{TERM_SEPARATOR_RE}actions"), "GitHub Actions"),
    (term_re("гитхаб", rf"гит{TERM_SEPARATOR_RE}хаб", "github"), "GitHub"),
    (term_re("гитлаб", rf"гит{TERM_SEPARATOR_RE}лаб", "gitlab"), "GitLab"),
    (term_re("гит", "git"), "Git"),
    (term_re("докер", "docker"), "Docker"),
    (term_re("кубернетес", "кубер", "kubernetes"), "Kubernetes"),
    (term_re(rf"кей{TERM_SEPARATOR_RE}эйтс", "k8s"), "K8s"),
    (term_re("терраформ", "terraform"), "Terraform"),
    (term_re(rf"си{TERM_SEPARATOR_RE}ай{TERM_SEPARATOR_RE}си{TERM_SEPARATOR_RE}ди", rf"ci{TERM_SEPARATOR_RE}cd", "cicd"), "CI/CD"),
    (term_re("энжинкс", "инжинкс", "nginx"), "Nginx"),
    (term_re("редис", "redis"), "Redis"),
    (term_re("постгрескуэл", "постгрес", "postgresql", "postgres"), "PostgreSQL"),
    (term_re(rf"май{TERM_SEPARATOR_RE}эс{TERM_SEPARATOR_RE}кью{TERM_SEPARATOR_RE}эл", "mysql"), "MySQL"),
    (term_re(rf"монго{TERM_SEPARATOR_RE}дб", "mongodb"), "MongoDB"),
    (term_re("кафка", "kafka"), "Kafka"),
    (term_re(rf"рэббит{TERM_SEPARATOR_RE}эм{TERM_SEPARATOR_RE}кью", "rabbitmq"), "RabbitMQ"),
    # Languages and frameworks.
    (term_re("пайтон", "python"), "Python"),
    (term_re("тайпскрипт", "typescript"), "TypeScript"),
    (term_re("джаваскрипт", "яваскрипт", "javascript"), "JavaScript"),
    (term_re(rf"нод{TERM_SEPARATOR_RE}жс", rf"ноуд{TERM_SEPARATOR_RE}джей{TERM_SEPARATOR_RE}эс", rf"node{TERM_SEPARATOR_RE}js", r"node\.js"), "Node.js"),
    (term_re(rf"некст{TERM_SEPARATOR_RE}жс", rf"next{TERM_SEPARATOR_RE}js", r"next\.js"), "Next.js"),
    (term_re("реакт", "react"), "React"),
    (term_re("вью", "vue"), "Vue"),
    (term_re(rf"свифт{TERM_SEPARATOR_RE}ю{TERM_SEPARATOR_RE}ай", rf"swift{TERM_SEPARATOR_RE}ui", "swiftui"), "SwiftUI"),
    (term_re("свифт", "swift"), "Swift"),
    (term_re(rf"икс{TERM_SEPARATOR_RE}код", "xcode"), "Xcode"),
    (term_re("котлин", "kotlin"), "Kotlin"),
    (term_re("джава", "java"), "Java"),
    (term_re("раст", "rust"), "Rust"),
    (term_re("дотнет", "dotnet", r"\.net"), ".NET"),
    # Russian fintechs, banks, and payment products with conservative variants.
    (term_re(rf"озон{TERM_SEPARATOR_RE}банк", rf"ozon{TERM_SEPARATOR_RE}bank"), "Ozon Банк"),
    (term_re(rf"вб{TERM_SEPARATOR_RE}банк", rf"wb{TERM_SEPARATOR_RE}bank", rf"дабл{TERM_SEPARATOR_RE}ю{TERM_SEPARATOR_RE}би{TERM_SEPARATOR_RE}банк"), "WB Банк"),
    (term_re(rf"яндекс{TERM_SEPARATOR_RE}пэй", rf"yandex{TERM_SEPARATOR_RE}pay"), "Яндекс Pay"),
    (term_re(rf"яндекс{TERM_SEPARATOR_RE}банк", rf"yandex{TERM_SEPARATOR_RE}bank"), "Яндекс Банк"),
    (term_re("сбербанк", rf"сбер{TERM_SEPARATOR_RE}банк", "sberbank"), "Сбербанк"),
    (term_re("сбер", "sber"), "Сбер"),
    (term_re(rf"т{TERM_SEPARATOR_RE}банк", rf"ти{TERM_SEPARATOR_RE}банк", rf"t{TERM_SEPARATOR_RE}bank", "tbank"), "T-Банк"),
    (term_re("тинькофф", "тиньков", "tinkoff"), "Тинькофф"),
    (term_re("альфабанк", rf"альфа{TERM_SEPARATOR_RE}банк", rf"alfa{TERM_SEPARATOR_RE}bank", "alfabank"), "Альфа-Банк"),
    (term_re("втб", rf"в{TERM_SEPARATOR_RE}т{TERM_SEPARATOR_RE}б", rf"ви{TERM_SEPARATOR_RE}ти{TERM_SEPARATOR_RE}би", "vtb"), "ВТБ"),
    (term_re("газпромбанк", rf"газпром{TERM_SEPARATOR_RE}банк", "gazprombank"), "Газпромбанк"),
    (term_re("райффайзенбанк", "райфайзенбанк", rf"райффайзен{TERM_SEPARATOR_RE}банк", "raiffeisenbank"), "Райффайзенбанк"),
    (term_re(rf"ю{TERM_SEPARATOR_RE}мани", "юмани", "yoomoney"), "ЮMoney"),
    (term_re(rf"ю{TERM_SEPARATOR_RE}касса", "юкасса", rf"yoo{TERM_SEPARATOR_RE}kassa", "yookassa"), "ЮKassa"),
    (term_re("киви", "qiwi"), "QIWI"),
    (term_re(rf"клауд{TERM_SEPARATOR_RE}пейментс", rf"cloud{TERM_SEPARATOR_RE}payments", "cloudpayments"), "CloudPayments"),
    (term_re("робокасса", rf"робо{TERM_SEPARATOR_RE}касса", "robokassa"), "Robokassa"),
    (term_re(rf"банк{TERM_SEPARATOR_RE}точка", rf"точка{TERM_SEPARATOR_RE}банк"), "Банк Точка"),
    (term_re("модульбанк", rf"модуль{TERM_SEPARATOR_RE}банк"), "Модульбанк"),
    (term_re("совкомбанк", rf"совком{TERM_SEPARATOR_RE}банк"), "Совкомбанк"),
    (term_re("сбп", rf"с{TERM_SEPARATOR_RE}б{TERM_SEPARATOR_RE}п", rf"эс{TERM_SEPARATOR_RE}бэ{TERM_SEPARATOR_RE}пэ", "sbp"), "СБП"),
]


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


def normalize_transcript_text(text: str) -> str:
    text = DASH_SPACING_RE.sub(" — ", text.strip()).strip()
    return normalize_domain_terms(text)


def normalize_domain_terms(text: str) -> str:
    for pattern, replacement in TERM_REPLACEMENTS:
        text = pattern.sub(replacement, text)
    return text


def normalize_text(result: Any) -> str:
    if isinstance(result, str):
        return normalize_transcript_text(result)

    text = getattr(result, "text", None)
    if isinstance(text, str):
        return normalize_transcript_text(text)

    if isinstance(result, (list, tuple)) and result:
        return normalize_text(result[0])

    return normalize_transcript_text(str(result)) if result is not None else ""


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

        model_path = os.environ.get("RUFLOW_GIGAAM_MODEL_DIR")
        model_path_arg = str(Path(model_path).expanduser()) if model_path else None
        model = onnx_asr.load_model(
            MODEL_NAME,
            path=model_path_arg,
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
