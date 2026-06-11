#!/usr/bin/env python3
import json
import subprocess
import sys
from pathlib import Path


MODEL_NAME = "gigaam-v3-e2e-rnnt"


def fail(message: str) -> int:
    print(message, file=sys.stderr)
    return 1


def main() -> int:
    if len(sys.argv) != 2:
        return fail("usage: smoke_test.py /path/to/audio.wav")

    runner_path = Path(__file__).with_name("runner.py")
    wav_path = Path(sys.argv[1]).expanduser()
    process = subprocess.run(
        [sys.executable, str(runner_path), str(wav_path)],
        capture_output=True,
        text=True,
        check=False,
    )

    if process.returncode != 0:
        return fail(f"runner.py exited with code {process.returncode}\n{process.stderr}")

    stdout = process.stdout.strip()
    if not stdout:
        return fail("runner.py stdout is empty")

    try:
        payload = json.loads(stdout)
    except json.JSONDecodeError as error:
        return fail(f"runner.py stdout is not valid JSON: {error}\nstdout={stdout!r}")

    if payload.get("model") != MODEL_NAME:
        return fail(f"unexpected model: {payload.get('model')!r}")

    if payload.get("ok") is True and not str(payload.get("text", "")).strip():
        return fail("successful ASR result has empty text")

    if payload.get("ok") is not True:
        return fail(f"ASR failed: {payload.get('error', 'unknown error')}")

    print(json.dumps(payload, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
