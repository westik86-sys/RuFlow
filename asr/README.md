# RuFlow ASR Sidecar

Local ASR runner for RuFlow. It loads `gigaam-v3-e2e-rnnt` through `onnx-asr` and prints exactly one JSON object to stdout.
Long WAV files are split into 25-second chunks before recognition, then all
recognized segments are joined into one transcript.

```sh
cd asr
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
python runner.py ../samples/test.wav
```

Preload/check the model before launching RuFlow:

```sh
python runner.py /absolute/path/to/test.wav
```

If Hugging Face download fails with a corporate/self-signed SSL certificate during local development, either add the corporate CA to Python's trust store or run a one-off insecure prewarm:

```sh
RUFLOW_HF_INSECURE=1 python runner.py /absolute/path/to/test.wav
```

Smoke test:

```sh
python smoke_test.py ../samples/test.wav
```

The Windows app downloads the default model into
`%LOCALAPPDATA%\RuFlow\Models\gigaam-v3-e2e-rnnt` on first launch. Direct
`asr/runner.py` usage without `RUFLOW_GIGAAM_MODEL_DIR` uses the standard
Hugging Face cache.

Optional environment variables:

- `RUFLOW_ASR_MODEL` - `onnx-asr` model name;
- `RUFLOW_GIGAAM_MODEL_DIR` - local model directory;
- `RUFLOW_ASR_CHUNK_SECONDS` - ASR chunk size in seconds; default is `25`, set
  to `0` to disable chunking.
