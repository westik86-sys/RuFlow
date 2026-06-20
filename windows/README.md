# RuFlow Windows Adapter

This is a Windows adapter for the macOS-first RuFlow app. It keeps the same ASR
engine (`asr/runner.py`, `gigaam-v3-e2e-rnnt`) and implements the Windows shell
in Python:

- global hold-to-talk hotkey fallback;
- global double-click mouse side button trigger;
- 16 kHz mono WAV recording from the default microphone;
- ASR subprocess call through the current Python environment;
- recognized text copied to the clipboard;
- optional text insertion through synthetic `Ctrl+V`;
- small animated cursor popover that follows the cursor during recording;
- microphone-level waveform inside the recording popover;
- compact cursor toasts for recognition progress, completion, and paste;
- left mouse double-click paste after successful recognition.

## Install from a release

Download `RuFlowSetup-x64.exe` from GitHub Releases and run it. The GUI
installer installs for the current Windows user, creates Start Menu and desktop
shortcuts, adds an uninstall entry to Windows Apps & Features, and can launch
RuFlow after setup.

During installation RuFlow downloads the ONNX ASR model to:

```text
%LOCALAPPDATA%\RuFlow\Models\gigaam-v3-e2e-rnnt
```

RuFlow starts with a compact control window where the trigger mode, side mouse
button, and global hotkey can be changed before starting the background listener.
To assign a hotkey, click the hotkey field and press the desired key combination;
the field is filled automatically. If the install-time model download fails, the
first background launch shows a small status window while the model download is
retried.

The model is not bundled into the installer because it is large and should stay
outside Git history and release source archives.

## Install

From the repository root:

```bat
scripts\setup_windows.bat
```

The script creates `.venv-win` and installs `windows\requirements.txt`, which
includes the shared ASR requirements from `asr\requirements.txt`.

## Run

```bat
scripts\run_windows.bat
```

Plain launch opens the RuFlow control window. Press `Запустить в фоне` to start
the background listener. To skip the window and start immediately:

```bat
scripts\run_windows.bat --background
```

Default controls:

- double-click the first side mouse button (`X1` / Back) to start recording;
- double-click the same button again to hide the recording popover and
  transcribe;
- single clicks still act as the normal Back button;
- wait for the `Распознано` toast;
- the result is copied to the clipboard;
- double-click the left mouse button to paste into the focused field, or paste
  it anywhere with `Ctrl+V`;
- press `Esc` while recording to cancel.

RuFlow shows a tray icon near the Windows clock. Use its `Настройки` menu item,
the `Настройки RuFlow` Start Menu shortcut, or this command to change the trigger
mode, side mouse button, or global hotkey without starting another listener:

```bat
scripts\run_windows.bat --settings
```

Settings are stored in:

```text
%APPDATA%\RuFlow\config.json
```

Use `Выйти из RuFlow` from the tray menu to stop the background mouse hook cleanly.

Recording has no default duration limit. It stops when you double-click the
mouse trigger again, press `Esc`, or set a custom `--max-duration`.
Long recordings are transcribed in 25-second ASR chunks and then joined back
into one clipboard text.

The installer downloads the model from Hugging Face into
`%LOCALAPPDATA%\RuFlow\Models`. First launch can still take a while if the
install-time download was skipped or failed and RuFlow has to retry it.

## Useful options

```bat
.venv-win\Scripts\python.exe windows\ruflow_windows.py --help
```

Examples:

```bat
scripts\run_windows.bat --background --mouse-button x2
scripts\run_windows.bat --background --trigger hotkey --hotkey ctrl+shift+f9
scripts\run_windows.bat --background --auto-paste
scripts\run_windows.bat --background --no-popover
scripts\run_windows.bat --background --pass-through-mouse-button
scripts\run_windows.bat --background --trigger hotkey --hotkey ctrl+shift+space
scripts\run_windows.bat --keep-recordings
scripts\run_windows.bat --list-devices
scripts\run_windows.bat --transcribe C:\Temp\sample.wav
scripts\run_windows.bat --model-dir C:\Models\gigaam-v3-e2e-rnnt
```

Environment variables supported by the ASR runner:

- `RUFLOW_ASR_MODEL` - `onnx-asr` model name. Default:
  `gigaam-v3-e2e-rnnt`.
- `RUFLOW_GIGAAM_MODEL_DIR` - local model directory;
- `RUFLOW_HF_INSECURE=1` - one-off local workaround for corporate/self-signed
  TLS inspection during Hugging Face download.
- `RUFLOW_ASR_CHUNK_SECONDS` - ASR chunk size for long recordings. Default:
  `25`. Set to `0` to disable chunking.

The upstream model is `ai-sage/GigaAM-v3`. This Windows build uses the ONNX
runtime variant from `istupakov/gigaam-v3-onnx` through `onnx-asr`, because it is
smaller and avoids bundling PyTorch/Transformers in the installer.

## Limitations

- The Windows app uses a compact Tk control window and tray menu, not a native
  WinUI shell.
- By default, recognized text intentionally remains in the clipboard for manual
  paste. Use `--auto-paste` only if you want direct insertion into the active
  window.
- The mouse side button is suppressed by default so Back/Forward does not fire
  on the dictation double-click. Single clicks are replayed as normal Back /
  Forward after the double-click window. Use `--pass-through-mouse-button` to
  disable this protection.
- The fallback hotkey path uses the `keyboard` package, which may require
  running the terminal as Administrator on some Windows setups.

## Build a Windows installer

For a release-quality GUI installer, install Inno Setup 6 and run:

```bat
scripts\build_windows_release.bat
```

Outputs:

- `dist\windows\RuFlow\RuFlow.exe` - portable app folder;
- `dist\windows\RuFlowSetup-x64.exe` - GUI per-user installer.
- `dist\windows\RuFlow-portable-x64.zip` - zipped portable app folder.

The release script signs `RuFlow.exe` and `RuFlowSetup-x64.exe` when these
environment variables are present:

- `RUFLOW_SIGN_CERT_PATH` - path to a `.pfx` code signing certificate;
- `RUFLOW_SIGN_CERT_PASSWORD` - certificate password;
- `RUFLOW_TIMESTAMP_URL` - optional timestamp server URL.

Without a certificate the build continues unsigned. Unsigned builds can trigger
Windows SmartScreen warnings.

`scripts\build_windows_installer.bat` is kept as a compatibility alias for the
same release build:

```bat
scripts\build_windows_installer.bat
```

## GitHub release automation

`.github/workflows/windows-release.yml` builds on `windows-latest`, installs Inno
Setup, runs the Windows and ASR tests, builds `RuFlowSetup-x64.exe`, uploads the
release artifacts, and publishes the installer when a `v*` tag is pushed.

To enable signing in GitHub Actions, add these repository secrets:

- `WINDOWS_SIGNING_CERT_BASE64` - base64-encoded `.pfx` certificate;
- `WINDOWS_SIGNING_CERT_PASSWORD` - certificate password.

Do not commit certificates, passwords, downloaded models, `dist/`, or build
outputs to Git.
