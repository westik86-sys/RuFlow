import json
import os
import sys
import threading
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))

import ruflow_windows as rw
from installer import looks_like_ruflow_install
from ruflow_windows import (
    ASRError,
    BindingSequenceLoop,
    DOUBLE_CLICK_SECONDS,
    DEFAULT_MODEL_NAME,
    DictationController,
    MouseXButtonLoop,
    bundled_model_dir,
    default_user_config,
    default_model_dir,
    download_model_command,
    ensure_model_available,
    binding_token_from_vk_code,
    format_binding_sequence,
    format_for_insertion,
    format_hotkey_for_ui,
    hotkey_from_key_event,
    load_user_config,
    normalize_tk_key_name,
    parse_asr_stdout,
    parse_binding_sequence,
    parse_hotkey,
    parse_mouse_button,
    pcm16_audio_level,
    safe_model_dir_name,
    sanitize_user_config,
    save_user_config,
    sentence_count,
    settings_command,
    should_show_control_window,
    should_show_model_download_status,
)


class TextFormattingTests(unittest.TestCase):
    def test_removes_final_period_from_single_sentence(self) -> None:
        self.assertEqual(format_for_insertion("Привет мир."), "Привет мир")

    def test_keeps_final_period_for_multiple_sentences(self) -> None:
        self.assertEqual(format_for_insertion("Привет. Пока."), "Привет. Пока.")

    def test_keeps_ellipsis(self) -> None:
        self.assertEqual(format_for_insertion("Ну..."), "Ну...")

    def test_counts_sentence_endings(self) -> None:
        self.assertEqual(sentence_count("Раз. Два! Три?"), 3)


class AudioLevelTests(unittest.TestCase):
    def test_silence_level_is_zero(self) -> None:
        self.assertEqual(pcm16_audio_level(b"\x00\x00" * 128), 0.0)

    def test_loud_pcm_has_high_level(self) -> None:
        loud_sample = int(22000).to_bytes(2, "little", signed=True)
        self.assertGreater(pcm16_audio_level(loud_sample * 128), 0.8)


class PopoverUiTests(unittest.TestCase):
    def test_recording_popover_stays_compact_with_two_pixel_bars(self) -> None:
        width, height = rw.PopoverPresenter.RECORDING_SIZE
        self.assertGreaterEqual(width, 180)
        self.assertLessEqual(width, 200)
        self.assertLessEqual(height, 46)
        self.assertEqual(rw.PopoverPresenter.WAVE_BAR_WIDTH, 2)

    def test_popover_uses_solid_panel_background(self) -> None:
        self.assertFalse(hasattr(rw.PopoverPresenter, "TRANSPARENT_COLOR"))
        self.assertEqual(rw.PopoverPresenter.PANEL_BG, "#171a1f")

    def test_result_badge_matches_paste_ready_duration(self) -> None:
        self.assertEqual(int(rw.RESULT_PASTE_SECONDS * 1000), 20_000)


class HotkeyParsingTests(unittest.TestCase):
    def test_parses_default_hotkey(self) -> None:
        hotkey = parse_hotkey("ctrl+alt+space")
        self.assertEqual(hotkey.modifiers, ("ctrl", "alt"))
        self.assertEqual(hotkey.key, "space")

    def test_rejects_missing_modifier(self) -> None:
        with self.assertRaises(ValueError):
            parse_hotkey("space")

    def test_rejects_duplicate_modifier(self) -> None:
        with self.assertRaises(ValueError):
            parse_hotkey("ctrl+ctrl+space")

    def test_builds_hotkey_from_key_event_state(self) -> None:
        self.assertEqual(hotkey_from_key_event("F9", "", 0x0004 | 0x0001), "ctrl+shift+f9")

    def test_builds_hotkey_from_pressed_modifier_keys(self) -> None:
        self.assertEqual(hotkey_from_key_event("space", " ", 0, {"ctrl", "alt"}), "ctrl+alt+space")

    def test_ignores_plain_key_without_modifier(self) -> None:
        self.assertIsNone(hotkey_from_key_event("a", "a", 0))

    def test_normalizes_tk_key_aliases(self) -> None:
        self.assertEqual(normalize_tk_key_name("Escape"), "esc")
        self.assertEqual(normalize_tk_key_name("Prior"), "pageup")

    def test_formats_hotkey_for_ui_with_spacing(self) -> None:
        self.assertEqual(format_hotkey_for_ui("ctrl+shift+f9"), "Ctrl + Shift + F9")

    def test_formats_hotkey_for_ui_from_loose_input(self) -> None:
        self.assertEqual(format_hotkey_for_ui("alt s"), "Alt + S")
        self.assertEqual(format_hotkey_for_ui("control+option+space"), "Ctrl + Alt + Space")


class BindingParsingTests(unittest.TestCase):
    def test_parses_repeated_keys(self) -> None:
        self.assertEqual(parse_binding_sequence("enter+enter+enter"), ("enter", "enter", "enter"))

    def test_formats_binding_as_tags(self) -> None:
        self.assertEqual(format_binding_sequence(["shift", "shift", "mouse:x1"]), ["Shift", "Shift", "Mouse X1"])

    def test_parses_mouse_aliases(self) -> None:
        self.assertEqual(parse_binding_sequence(["Mouse Button 4", "Mouse Button 4"]), ("mouse:x1", "mouse:x1"))

    def test_rejects_empty_binding(self) -> None:
        with self.assertRaises(ValueError):
            parse_binding_sequence([])

    def test_maps_vk_codes_to_binding_tokens(self) -> None:
        self.assertEqual(binding_token_from_vk_code(0x0D), "enter")
        self.assertEqual(binding_token_from_vk_code(0xA0), "shift")
        self.assertEqual(binding_token_from_vk_code(0x41), "a")
        self.assertEqual(binding_token_from_vk_code(0x70), "f1")


class MouseButtonParsingTests(unittest.TestCase):
    def test_parses_x1_aliases(self) -> None:
        self.assertEqual(parse_mouse_button("x1"), "x1")
        self.assertEqual(parse_mouse_button("back"), "x1")
        self.assertEqual(parse_mouse_button("Mouse Button 4"), "x1")

    def test_parses_x2_aliases(self) -> None:
        self.assertEqual(parse_mouse_button("x2"), "x2")
        self.assertEqual(parse_mouse_button("forward"), "x2")
        self.assertEqual(parse_mouse_button("mouse-button-5"), "x2")

    def test_rejects_unknown_mouse_button(self) -> None:
        with self.assertRaises(ValueError):
            parse_mouse_button("left")


class ModelDownloadConfigTests(unittest.TestCase):
    def test_safe_model_dir_name_replaces_path_separators(self) -> None:
        self.assertEqual(safe_model_dir_name("owner/model name"), "owner-model-name")

    def test_default_model_dir_uses_safe_model_name(self) -> None:
        self.assertEqual(default_model_dir("owner/model").name, "owner-model")

    def test_bundled_model_dir_uses_safe_model_name(self) -> None:
        self.assertEqual(bundled_model_dir("owner/model").name, "owner-model")

    def test_ensure_model_available_accepts_explicit_existing_dir(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            model_dir = Path(tmp)
            self.assertEqual(ensure_model_available("any/model", model_dir, hf_insecure=False), model_dir)

    def test_ensure_model_available_rejects_missing_explicit_dir(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            missing = Path(tmp) / "missing"
            with self.assertRaises(ASRError):
                ensure_model_available("any/model", missing, hf_insecure=False)

    def test_ensure_model_available_prefers_bundled_model(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            bundled_dir = Path(tmp) / "bundled"
            bundled_dir.mkdir()
            (bundled_dir / "config.json").write_text("{}", encoding="utf-8")
            with mock.patch.object(rw, "bundled_model_dir", return_value=bundled_dir):
                with mock.patch.object(rw, "download_asr_model") as download:
                    self.assertEqual(ensure_model_available(DEFAULT_MODEL_NAME, None, hf_insecure=False), bundled_dir)
                    download.assert_not_called()

    def test_download_model_command_returns_success_when_model_is_ready(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ready_dir = Path(tmp) / "model"
            ready_dir.mkdir()
            (ready_dir / "config.json").write_text("{}", encoding="utf-8")
            with mock.patch.object(rw, "default_model_dir", return_value=ready_dir):
                with mock.patch.object(rw, "download_asr_model") as download:
                    self.assertEqual(download_model_command(DEFAULT_MODEL_NAME, None, hf_insecure=False), 0)
                    download.assert_not_called()

    def test_download_model_command_downloads_to_explicit_missing_dir(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target_dir = Path(tmp) / "model"
            with mock.patch.object(rw, "download_asr_model") as download:
                self.assertEqual(download_model_command(DEFAULT_MODEL_NAME, target_dir, hf_insecure=False), 0)
                download.assert_called_once_with(DEFAULT_MODEL_NAME, target_dir, hf_insecure=False)

    def test_download_model_command_returns_error_when_download_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target_dir = Path(tmp) / "model"
            with mock.patch.object(rw, "default_model_dir", return_value=target_dir):
                with mock.patch.object(rw, "download_asr_model", side_effect=ASRError("download failed")):
                    self.assertEqual(download_model_command(DEFAULT_MODEL_NAME, None, hf_insecure=False), 1)

    def test_ensure_model_available_handles_missing_stderr(self) -> None:
        original_stdout = sys.stdout
        original_stderr = sys.stderr
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            model_dir = tmp_path / "model"
            with mock.patch.dict(os.environ, {"LOCALAPPDATA": str(tmp_path)}):
                with mock.patch.object(rw, "default_model_dir", return_value=model_dir):
                    with mock.patch.object(rw, "bundled_model_dir", return_value=tmp_path / "bundled-missing"):
                        with mock.patch.object(rw, "download_asr_model", side_effect=RuntimeError("download failed")):
                            try:
                                sys.stdout = None
                                sys.stderr = None
                                with self.assertRaisesRegex(ASRError, "download failed"):
                                    ensure_model_available(DEFAULT_MODEL_NAME, None, hf_insecure=False)
                            finally:
                                created_stdout = sys.stdout
                                created_stderr = sys.stderr
                                sys.stdout = original_stdout
                                sys.stderr = original_stderr
                                for stream in {created_stdout, created_stderr}:
                                    if stream is not None and stream not in {original_stdout, original_stderr}:
                                        stream.close()

    def test_model_download_status_shows_only_for_missing_gui_default_model(self) -> None:
        original_model_dir_has_files = rw.model_dir_has_files
        rw.model_dir_has_files = lambda _path: False
        try:
            self.assertTrue(
                should_show_model_download_status(
                    no_popover=False,
                    no_model_download=False,
                    transcribe=None,
                    requested_model_dir=None,
                    model_name=DEFAULT_MODEL_NAME,
                )
            )
            self.assertFalse(
                should_show_model_download_status(
                    no_popover=True,
                    no_model_download=False,
                    transcribe=None,
                    requested_model_dir=None,
                    model_name=DEFAULT_MODEL_NAME,
                )
            )
            self.assertFalse(
                should_show_model_download_status(
                    no_popover=False,
                    no_model_download=False,
                    transcribe="sample.wav",
                    requested_model_dir=None,
                    model_name=DEFAULT_MODEL_NAME,
                )
            )
        finally:
            rw.model_dir_has_files = original_model_dir_has_files

    def test_model_download_status_skips_existing_default_model(self) -> None:
        original_model_dir_has_files = rw.model_dir_has_files
        rw.model_dir_has_files = lambda _path: True
        try:
            self.assertFalse(
                should_show_model_download_status(
                    no_popover=False,
                    no_model_download=False,
                    transcribe=None,
                    requested_model_dir=None,
                    model_name=DEFAULT_MODEL_NAME,
                )
            )
        finally:
            rw.model_dir_has_files = original_model_dir_has_files


class UserConfigTests(unittest.TestCase):
    def test_sanitize_user_config_accepts_binding_sequence(self) -> None:
        config = sanitize_user_config(
            {
                "binding": ["Enter", "Enter", "Mouse Button 4"],
            }
        )
        self.assertEqual(config["binding"], ["enter", "enter", "mouse:x1"])

    def test_sanitize_user_config_migrates_old_hotkey_settings(self) -> None:
        config = sanitize_user_config(
            {
                "trigger": "hotkey",
                "hotkey": "ctrl alt space",
            }
        )
        self.assertEqual(config["binding"], ["ctrl", "alt", "space"])

    def test_sanitize_user_config_migrates_old_mouse_settings(self) -> None:
        config = sanitize_user_config(
            {
                "trigger": "mouse",
                "mouse_button": "Mouse Button 4",
            }
        )
        self.assertEqual(config["binding"], ["mouse:x1", "mouse:x1"])

    def test_sanitize_user_config_ignores_invalid_values(self) -> None:
        config = sanitize_user_config(
            {
                "binding": [],
            }
        )
        self.assertEqual(config, default_user_config())

    def test_save_and_load_user_config_roundtrip(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config_path = Path(tmp) / "config.json"
            save_user_config(
                {
                    "binding": ["enter", "enter", "enter"],
                },
                config_path,
            )
            self.assertEqual(
                load_user_config(config_path),
                {
                    "binding": ["enter", "enter", "enter"],
                },
            )

    def test_parser_defaults_use_user_config(self) -> None:
        original_load_user_config = rw.load_user_config
        rw.load_user_config = lambda: {
            "binding": ["enter", "enter", "mouse:x2"],
        }
        try:
            args = rw.build_arg_parser().parse_args([])
            self.assertEqual(args.binding, "enter+enter+mouse:x2")
        finally:
            rw.load_user_config = original_load_user_config

    def test_settings_command_opens_current_app_in_settings_mode(self) -> None:
        command = settings_command()
        self.assertGreaterEqual(len(command), 2)
        self.assertEqual(command[-1], "--settings")

    def test_control_window_shows_for_plain_launch_only(self) -> None:
        parser = rw.build_arg_parser()
        with tempfile.TemporaryDirectory() as tmp:
            missing_config = Path(tmp) / "config.json"
            self.assertTrue(should_show_control_window(parser.parse_args([]), [], missing_config))
            self.assertFalse(should_show_control_window(parser.parse_args(["--background"]), ["--background"], missing_config))
            self.assertFalse(should_show_control_window(parser.parse_args(["--settings"]), ["--settings"], missing_config))
            self.assertFalse(should_show_control_window(parser.parse_args(["--first-run"]), ["--first-run"], missing_config))
            self.assertFalse(should_show_control_window(parser.parse_args(["--download-model"]), ["--download-model"], missing_config))
            self.assertFalse(should_show_control_window(parser.parse_args(["--list-devices"]), ["--list-devices"], missing_config))
            self.assertFalse(
                should_show_control_window(
                    parser.parse_args(["--transcribe", "sample.wav"]),
                    ["--transcribe", "sample.wav"],
                    missing_config,
                )
            )

    def test_control_window_skips_plain_launch_when_config_exists(self) -> None:
        parser = rw.build_arg_parser()
        with tempfile.TemporaryDirectory() as tmp:
            config_path = Path(tmp) / "config.json"
            save_user_config({"binding": ["enter", "enter"]}, config_path)
            self.assertFalse(should_show_control_window(parser.parse_args([]), [], config_path))


class FakePresenter:
    def __init__(self) -> None:
        self.pasted: list[tuple[int, int] | None] = []

    def show_pasted(self, anchor: tuple[int, int] | None) -> None:
        self.pasted.append(anchor)

    def show_error(self, message: str) -> None:
        raise AssertionError(message)


class FakeController:
    def __init__(self) -> None:
        self.events: list[tuple[str, tuple[int, int] | None]] = []
        self.presenter = FakePresenter()
        self._recording = False
        self._paste_ready = False

    @property
    def is_recording(self) -> bool:
        return self._recording

    def begin_recording(self, anchor: tuple[int, int] | None = None) -> None:
        self._recording = True
        self.events.append(("begin", anchor))

    def finish_recording(self, anchor: tuple[int, int] | None = None) -> None:
        self._recording = False
        self.events.append(("finish", anchor))

    def cancel_recording(self) -> None:
        self._recording = False
        self.events.append(("cancel", None))

    def paste_last_result(self, anchor: tuple[int, int] | None = None) -> bool:
        if not self._paste_ready:
            return False
        self._paste_ready = False
        self.events.append(("paste", anchor))
        return True


class MouseDoubleClickTests(unittest.TestCase):
    def test_single_click_replays_mouse_button(self) -> None:
        original_replay = rw.replay_xbutton_click
        replayed: list[int] = []
        rw.replay_xbutton_click = replayed.append
        try:
            loop = MouseXButtonLoop(mouse_button="x1", controller=FakeController(), suppress=True)
            loop._handle_button_down((10, 10))
            loop._handle_button_up((10, 10))
            time.sleep(DOUBLE_CLICK_SECONDS + 0.08)
            self.assertEqual(replayed, [loop.XBUTTON1])
        finally:
            rw.replay_xbutton_click = original_replay

    def test_double_click_toggles_recording_without_replay(self) -> None:
        original_replay = rw.replay_xbutton_click
        replayed: list[int] = []
        rw.replay_xbutton_click = replayed.append
        controller = FakeController()
        loop = MouseXButtonLoop(mouse_button="x1", controller=controller, suppress=True)
        action_thread = threading.Thread(target=loop._run_actions, daemon=True)
        action_thread.start()
        try:
            loop._handle_button_down((10, 10))
            loop._handle_button_up((10, 10))
            loop._handle_button_down((12, 12))
            loop._handle_button_up((12, 12))
            time.sleep(0.08)
            self.assertEqual(controller.events, [("begin", (12, 12))])
            self.assertEqual(replayed, [])
        finally:
            loop.stop()
            rw.replay_xbutton_click = original_replay

    def test_double_click_trigger_starts_recording_even_when_result_is_ready(self) -> None:
        original_replay = rw.replay_xbutton_click
        replayed: list[int] = []
        rw.replay_xbutton_click = replayed.append
        controller = FakeController()
        controller._paste_ready = True
        loop = MouseXButtonLoop(mouse_button="x1", controller=controller, suppress=True)
        action_thread = threading.Thread(target=loop._run_actions, daemon=True)
        action_thread.start()
        try:
            loop._handle_button_down((20, 20))
            loop._handle_button_up((20, 20))
            loop._handle_button_down((22, 22))
            loop._handle_button_up((22, 22))
            time.sleep(0.08)
            self.assertEqual(controller.events, [("begin", (22, 22))])
            self.assertTrue(controller.is_recording)
            self.assertEqual(replayed, [])
        finally:
            loop.stop()
            rw.replay_xbutton_click = original_replay

    def test_left_double_click_pastes_ready_result(self) -> None:
        controller = FakeController()
        controller._paste_ready = True
        loop = MouseXButtonLoop(mouse_button="x1", controller=controller, suppress=True)
        action_thread = threading.Thread(target=loop._run_actions, daemon=True)
        action_thread.start()
        try:
            loop._handle_left_button_down((30, 30))
            loop._handle_left_button_up((30, 30))
            loop._handle_left_button_down((31, 31))
            loop._handle_left_button_up((31, 31))
            time.sleep(0.08)
            self.assertEqual(controller.events, [("paste", (31, 31))])
            self.assertFalse(controller.is_recording)
        finally:
            loop.stop()

    def test_left_double_click_does_not_start_recording(self) -> None:
        controller = FakeController()
        loop = MouseXButtonLoop(mouse_button="x1", controller=controller, suppress=True)
        action_thread = threading.Thread(target=loop._run_actions, daemon=True)
        action_thread.start()
        try:
            loop._handle_left_button_down((40, 40))
            loop._handle_left_button_up((40, 40))
            loop._handle_left_button_down((41, 41))
            loop._handle_left_button_up((41, 41))
            time.sleep(0.08)
            self.assertEqual(controller.events, [])
            self.assertFalse(controller.is_recording)
        finally:
            loop.stop()


class BindingSequenceLoopTests(unittest.TestCase):
    def test_single_key_binding_toggles_recording_on_repeated_presses(self) -> None:
        controller = FakeController()
        loop = BindingSequenceLoop(binding=("enter",), controller=controller)
        action_thread = threading.Thread(target=loop._run_actions, daemon=True)
        action_thread.start()
        try:
            loop._register_binding_event("enter", (10, 10))
            time.sleep(0.08)
            self.assertEqual(controller.events, [("begin", (10, 10))])

            loop._register_binding_event("enter", (11, 11))
            time.sleep(0.08)
            self.assertEqual(controller.events, [("begin", (10, 10)), ("finish", (11, 11))])
        finally:
            loop.stop()

    def test_held_key_repeat_is_ignored_until_key_up(self) -> None:
        controller = FakeController()
        loop = BindingSequenceLoop(binding=("enter",), controller=controller)
        action_thread = threading.Thread(target=loop._run_actions, daemon=True)
        action_thread.start()
        try:
            with loop._lock:
                loop._pressed_key_tokens.add("enter")

            loop._register_keyboard_token("enter", pressed=True, anchor=(10, 10))
            time.sleep(0.08)
            self.assertEqual(controller.events, [])

            loop._register_keyboard_token("enter", pressed=False, anchor=(10, 10))
            loop._register_keyboard_token("enter", pressed=True, anchor=(11, 11))
            time.sleep(0.08)
            self.assertEqual(controller.events, [("begin", (11, 11))])
        finally:
            loop.stop()

    def test_repeated_key_sequence_toggles_recording(self) -> None:
        controller = FakeController()
        loop = BindingSequenceLoop(binding=("enter", "enter", "enter"), controller=controller)
        action_thread = threading.Thread(target=loop._run_actions, daemon=True)
        action_thread.start()
        try:
            loop._register_binding_event("enter", (10, 10))
            loop._register_binding_event("enter", (11, 11))
            time.sleep(0.03)
            self.assertEqual(controller.events, [])

            loop._register_binding_event("enter", (12, 12))
            time.sleep(0.08)
            self.assertEqual(controller.events, [("begin", (12, 12))])

            loop._register_binding_event("enter", (13, 13))
            loop._register_binding_event("enter", (14, 14))
            loop._register_binding_event("enter", (15, 15))
            time.sleep(0.08)
            self.assertEqual(controller.events[-1], ("finish", (15, 15)))
        finally:
            loop.stop()

    def test_left_double_click_still_pastes_ready_result(self) -> None:
        controller = FakeController()
        controller._paste_ready = True
        loop = BindingSequenceLoop(binding=("mouse:x1", "mouse:x1"), controller=controller)
        action_thread = threading.Thread(target=loop._run_actions, daemon=True)
        action_thread.start()
        try:
            loop._handle_left_click_for_paste((30, 30))
            loop._handle_left_click_for_paste((31, 31))
            time.sleep(0.08)
            self.assertEqual(controller.events, [("paste", (31, 31))])
        finally:
            loop.stop()


class ControllerPasteTests(unittest.TestCase):
    def test_paste_last_result_sends_clipboard_and_clears_ready_state(self) -> None:
        original_set_clipboard = rw.set_clipboard_text
        original_send_ctrl_v = rw.send_ctrl_v
        calls: list[tuple[str, str | None]] = []
        rw.set_clipboard_text = lambda text: calls.append(("clipboard", text))
        rw.send_ctrl_v = lambda: calls.append(("paste", None))
        presenter = FakePresenter()
        controller = DictationController(
            trigger_name="Mouse X1",
            recorder=object(),
            presenter=presenter,
            python_executable=Path("python"),
            runner_path=Path("runner.py"),
            model_name=DEFAULT_MODEL_NAME,
            model_dir=None,
            hf_insecure=False,
            keep_recordings=False,
            auto_paste=False,
            copy_to_clipboard=True,
            max_duration_seconds=0.0,
            asr_timeout_seconds=None,
            asr_mode="subprocess",
        )
        try:
            with controller._lock:
                controller._state = "paste_ready"
                controller._last_result_text = "готовый текст"
                controller._paste_ready_until = time.monotonic() + 10

            self.assertTrue(controller.paste_last_result((30, 30)))
            self.assertEqual(calls, [("clipboard", "готовый текст"), ("paste", None)])
            self.assertEqual(presenter.pasted, [(30, 30)])
            self.assertFalse(controller.paste_last_result((31, 31)))
        finally:
            rw.set_clipboard_text = original_set_clipboard
            rw.send_ctrl_v = original_send_ctrl_v


class ASRParsingTests(unittest.TestCase):
    def test_parses_success_payload(self) -> None:
        result = parse_asr_stdout(
            json.dumps(
                {
                    "ok": True,
                    "text": "тест",
                    "duration_ms": 42,
                    "model": DEFAULT_MODEL_NAME,
                }
            )
        )
        self.assertEqual(result.text, "тест")
        self.assertEqual(result.duration_ms, 42)

    def test_rejects_error_payload(self) -> None:
        payload = json.dumps({"ok": False, "error": "boom", "duration_ms": 1, "model": DEFAULT_MODEL_NAME})
        with self.assertRaisesRegex(ASRError, "boom"):
            parse_asr_stdout(payload)

    def test_rejects_unexpected_model(self) -> None:
        payload = json.dumps({"ok": True, "text": "x", "duration_ms": 1, "model": "other"})
        with self.assertRaisesRegex(ASRError, "unexpected ASR model"):
            parse_asr_stdout(payload)

    def test_accepts_configured_model(self) -> None:
        result = parse_asr_stdout(
            json.dumps({"ok": True, "text": "x", "duration_ms": 1, "model": "gigaam-v3-e2e-ctc"}),
            expected_model="gigaam-v3-e2e-ctc",
        )
        self.assertEqual(result.model, "gigaam-v3-e2e-ctc")


class InstallerSafetyTests(unittest.TestCase):
    def test_inno_installer_creates_desktop_shortcut_unconditionally(self) -> None:
        iss = (Path(__file__).resolve().parents[1] / "installer" / "RuFlow.iss").read_text(encoding="utf-8")
        self.assertIn('Name: "{autodesktop}\\RuFlow"; Filename: "{app}\\RuFlow.exe"; WorkingDir: "{app}"', iss)
        self.assertNotIn("Tasks: desktopicon", iss)

    def test_inno_installer_uses_bundled_model_without_install_download(self) -> None:
        iss = (Path(__file__).resolve().parents[1] / "installer" / "RuFlow.iss").read_text(encoding="utf-8")
        self.assertIn("Локальная модель распознавания уже включена в установщик", iss)
        self.assertNotIn("'--download-model'", iss)
        self.assertNotIn("ModelDownloadFailed", iss)
        self.assertNotIn("RaiseException", iss)

    def test_inno_installer_postinstall_launches_ruflow(self) -> None:
        iss = (Path(__file__).resolve().parents[1] / "installer" / "RuFlow.iss").read_text(encoding="utf-8")
        self.assertIn('Filename: "{app}\\RuFlow.exe"; Parameters: "--first-run"', iss)
        self.assertIn('Description: "Открыть настройку RuFlow"', iss)
        self.assertIn("postinstall", iss)

    def test_accepts_partial_ruflow_install_without_marker(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            install_dir = Path(tmp) / "RuFlow"
            install_dir.mkdir()
            (install_dir / "RuFlowSetup.exe").write_text("", encoding="utf-8")

            self.assertTrue(looks_like_ruflow_install(install_dir))

    def test_rejects_directory_with_unexpected_top_level_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            install_dir = Path(tmp) / "RuFlow"
            install_dir.mkdir()
            (install_dir / "RuFlowSetup.exe").write_text("", encoding="utf-8")
            (install_dir / "notes.txt").write_text("do not delete", encoding="utf-8")

            self.assertFalse(looks_like_ruflow_install(install_dir))

    def test_rejects_non_ruflow_directory_name(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            install_dir = Path(tmp) / "Other"
            install_dir.mkdir()
            (install_dir / "RuFlowSetup.exe").write_text("", encoding="utf-8")

            self.assertFalse(looks_like_ruflow_install(install_dir))


if __name__ == "__main__":
    unittest.main()
