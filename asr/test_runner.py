#!/usr/bin/env python3
import io
import os
import sys
import tempfile
import types
import unittest
import wave
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from runner import emit, normalize_text, recognize, redirect_stdout_to_stderr, split_wav_for_asr


class NormalizeTextTests(unittest.TestCase):
    def test_adds_missing_space_before_dash(self) -> None:
        self.assertEqual(normalize_text("Пример— это бла бла бла"), "Пример — это бла бла бла")

    def test_adds_missing_space_after_dash(self) -> None:
        self.assertEqual(normalize_text("Пример —это бла бла бла"), "Пример — это бла бла бла")

    def test_adds_missing_spaces_around_dash(self) -> None:
        self.assertEqual(normalize_text("Пример—это бла бла бла"), "Пример — это бла бла бла")

    def test_keeps_leading_dialogue_dash_at_start(self) -> None:
        self.assertEqual(normalize_text("— Пример"), "— Пример")

    def test_joins_all_segment_results(self) -> None:
        self.assertEqual(normalize_text(["Первый фрагмент.", "Второй фрагмент."]), "Первый фрагмент. Второй фрагмент.")

    def test_joins_result_objects(self) -> None:
        class Result:
            def __init__(self, text: str) -> None:
                self.text = text

        self.assertEqual(normalize_text([Result("Первый."), Result("Второй.")]), "Первый. Второй.")


class WavChunkingTests(unittest.TestCase):
    def test_splits_long_wav_into_chunks(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            wav_path = tmp_path / "long.wav"
            with wave.open(str(wav_path), "wb") as wav:
                wav.setnchannels(1)
                wav.setsampwidth(2)
                wav.setframerate(100)
                wav.writeframes(b"\x00\x00" * 250)

            chunks_dir = tmp_path / "chunks"
            chunks_dir.mkdir()
            chunks = split_wav_for_asr(wav_path, 1.0, chunks_dir)

            self.assertEqual(len(chunks), 3)
            self.assertTrue(all(chunk.is_file() for chunk in chunks))
            with wave.open(str(chunks[0]), "rb") as first:
                self.assertEqual(first.getnframes(), 100)
                self.assertEqual(first.getframerate(), 100)

    def test_keeps_short_wav_as_single_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            wav_path = Path(tmp) / "short.wav"
            with wave.open(str(wav_path), "wb") as wav:
                wav.setnchannels(1)
                wav.setsampwidth(2)
                wav.setframerate(100)
                wav.writeframes(b"\x00\x00" * 50)

            self.assertEqual(split_wav_for_asr(wav_path, 1.0, Path(tmp)), [wav_path])


class RecognizeChunkingTests(unittest.TestCase):
    def test_recognize_passes_long_wav_chunks_and_joins_results(self) -> None:
        original_module = sys.modules.get("onnx_asr")
        original_chunk_seconds = os.environ.get("RUFLOW_ASR_CHUNK_SECONDS")
        seen_waveforms: list[object] = []

        class FakeModel:
            def recognize(self, waveform: object) -> list[str] | str:
                seen_waveforms.append(waveform)
                if isinstance(waveform, list):
                    return [f"Фрагмент {index + 1}." for index, _item in enumerate(waveform)]
                return "Один фрагмент."

        fake_onnx_asr = types.SimpleNamespace(load_model=lambda *args, **kwargs: FakeModel())
        sys.modules["onnx_asr"] = fake_onnx_asr
        os.environ["RUFLOW_ASR_CHUNK_SECONDS"] = "1.0"

        try:
            with tempfile.TemporaryDirectory() as tmp:
                wav_path = Path(tmp) / "long.wav"
                with wave.open(str(wav_path), "wb") as wav:
                    wav.setnchannels(1)
                    wav.setsampwidth(2)
                    wav.setframerate(100)
                    wav.writeframes(b"\x00\x00" * 250)

                self.assertEqual(recognize(wav_path, "fake-model"), "Фрагмент 1. Фрагмент 2. Фрагмент 3.")
                self.assertIsInstance(seen_waveforms[0], list)
                self.assertEqual(len(seen_waveforms[0]), 3)
        finally:
            if original_module is None:
                sys.modules.pop("onnx_asr", None)
            else:
                sys.modules["onnx_asr"] = original_module
            if original_chunk_seconds is None:
                os.environ.pop("RUFLOW_ASR_CHUNK_SECONDS", None)
            else:
                os.environ["RUFLOW_ASR_CHUNK_SECONDS"] = original_chunk_seconds


class StreamSafetyTests(unittest.TestCase):
    def test_redirect_stdout_to_stderr_handles_missing_streams(self) -> None:
        original_stdout = sys.stdout
        original_stderr = sys.stderr
        try:
            sys.stdout = None
            sys.stderr = None
            with redirect_stdout_to_stderr():
                print("ignored")
        finally:
            sys.stdout = original_stdout
            sys.stderr = original_stderr

    def test_redirect_stdout_to_stderr_handles_streams_without_fileno(self) -> None:
        original_stdout = sys.stdout
        original_stderr = sys.stderr
        captured_stderr = io.StringIO()
        try:
            sys.stdout = io.StringIO()
            sys.stderr = captured_stderr
            with redirect_stdout_to_stderr():
                print("library noise")
        finally:
            sys.stdout = original_stdout
            sys.stderr = original_stderr

        self.assertIn("library noise", captured_stderr.getvalue())

    def test_emit_handles_missing_streams(self) -> None:
        original_stdout = sys.stdout
        original_stderr = sys.stderr
        try:
            sys.stdout = None
            sys.stderr = None
            emit({"ok": True})
        finally:
            sys.stdout = original_stdout
            sys.stderr = original_stderr


if __name__ == "__main__":
    unittest.main()
