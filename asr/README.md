# RuFlow ASR Sidecar

Local ASR runner for RuFlow. It loads `gigaam-v3-e2e-rnnt` through `onnx-asr` and prints exactly one JSON object to stdout.

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

The first run may download model files from Hugging Face into the local Hugging Face cache.
