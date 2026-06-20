# RuFlow

RuFlow is a Russian dictation tool. The original app is a native macOS menu bar
app built with Swift, AppKit, AVFoundation, and Xcode.

This repository now also contains a Windows adapter in `windows/`. It reuses the
same local ASR runner from `asr/runner.py`, but replaces the macOS-only shell
with Python code for Windows mouse-button double-click dictation, microphone
recording, clipboard copy, optional clipboard paste, and an animated cursor
popover.

## Windows quick start

For end users, download `RuFlowSetup-x64.exe` from GitHub Releases and run it.
The installer is a normal per-user Windows installer. It installs RuFlow into
`%LOCALAPPDATA%\Programs\RuFlow`, creates Start Menu and desktop shortcuts,
registers uninstall metadata, and can launch RuFlow after installation.

Requirements:

- Windows 10 or Windows 11
- A working microphone

For development from source:

```bat
scripts\setup_windows.bat
```

Run:

```bat
scripts\run_windows.bat
```

Plain launch opens a compact RuFlow control window for assigning the recording
binding. Click the binding field and press any sequence of keyboard keys or
mouse buttons, for example `Enter + Enter` or `Mouse X1 + Mouse X1`. Save and
launch to start the background listener, or pass `--background` for immediate
startup from scripts.

Press the saved binding once to start recording. A small popover appears near
the cursor while recording and follows the cursor. Its waveform keeps moving in
silence and expands with the microphone level. Press the same binding again to
stop and transcribe; small cursor toasts show recognition progress and
completion. After successful recognition, double-click the left mouse button to
paste the copied text into the focused field, or use `Ctrl+V`. Press `Esc` while
recording to cancel.

RuFlow also shows a tray icon near the Windows clock. Use its `Настройки` menu
item to change the binding. The `Настройки RuFlow` Start Menu shortcut opens
the same settings window.

Release builds can bundle the ONNX ASR model in the app directory, so the
installed app works offline after installation. Development builds still fall
back to `%LOCALAPPDATA%\RuFlow\Models` or the standard Hugging Face cache when a
bundled model is not present.

Build a release installer:

```bat
scripts\build_windows_release.bat
```

The build outputs `dist\windows\RuFlowSetup-x64.exe` and
`dist\windows\RuFlow-portable-x64.zip`. Signing is enabled when
`RUFLOW_SIGN_CERT_PATH` points to a `.pfx` certificate; otherwise the build
continues unsigned.

See `windows/README.md` for options, troubleshooting, and current limitations.

## macOS

The macOS app remains an Xcode project under `RuFlow.xcodeproj`. The ASR sidecar
setup is documented in `asr/README.md`.
