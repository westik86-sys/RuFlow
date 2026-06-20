#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
import textwrap
import winreg
from pathlib import Path


APP_NAME = "RuFlow"
APP_VERSION = "0.1.0"
PUBLISHER = "RuFlow"
INSTALL_MARKER = ".ruflow-install"
UNINSTALL_REGISTRY_KEY = r"Software\Microsoft\Windows\CurrentVersion\Uninstall\RuFlow"
KNOWN_INSTALL_TOP_LEVEL_NAMES = {
    INSTALL_MARKER,
    "_internal",
    "RuFlow.exe",
    "RuFlowSetup.exe",
    "Uninstall RuFlow.bat",
}


class InstallerError(RuntimeError):
    pass


def default_install_dir() -> Path:
    local_app_data = os.environ.get("LOCALAPPDATA")
    if not local_app_data:
        return Path.home() / "AppData" / "Local" / "Programs" / APP_NAME
    return Path(local_app_data) / "Programs" / APP_NAME


def bundled_payload_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS) / "payload" / APP_NAME  # type: ignore[attr-defined]
    return Path(__file__).resolve().parents[1] / "dist" / "windows" / APP_NAME


def install(
    *,
    payload_dir: Path,
    install_dir: Path,
    create_shortcuts: bool,
    create_desktop_shortcut: bool,
    write_registry: bool,
    launch: bool,
) -> None:
    payload_dir = payload_dir.resolve()
    install_dir = install_dir.resolve()

    if not (payload_dir / "RuFlow.exe").is_file():
        raise InstallerError(f"payload is missing RuFlow.exe: {payload_dir}")

    prepare_install_dir(install_dir)
    shutil.copytree(payload_dir, install_dir, dirs_exist_ok=True)
    (install_dir / INSTALL_MARKER).write_text(f"{APP_NAME} {APP_VERSION}\n", encoding="utf-8")

    write_uninstaller(install_dir)

    if create_shortcuts:
        create_start_menu_shortcut(install_dir)
        if create_desktop_shortcut:
            create_desktop_shortcut_file(install_dir)

    if write_registry:
        write_uninstall_registry(install_dir)

    print(f"Installed {APP_NAME} to {install_dir}")
    if launch:
        subprocess.Popen([str(install_dir / "RuFlow.exe")], cwd=str(install_dir))


def uninstall(*, install_dir: Path, remove_shortcuts: bool, remove_registry: bool) -> None:
    install_dir = install_dir.resolve()

    if remove_shortcuts:
        remove_shortcut_paths()

    if remove_registry:
        remove_uninstall_registry()

    if install_dir.exists():
        assert_safe_install_dir(install_dir)
        try:
            shutil.rmtree(install_dir)
        except PermissionError:
            schedule_directory_removal(install_dir)

    print(f"Uninstalled {APP_NAME}")


def prepare_install_dir(install_dir: Path) -> None:
    if install_dir.exists():
        assert_safe_install_dir(install_dir)
        try:
            shutil.rmtree(install_dir)
        except PermissionError as error:
            raise InstallerError(
                f"could not replace {install_dir}. Close RuFlow.exe and run the installer again."
            ) from error
    install_dir.mkdir(parents=True, exist_ok=True)


def assert_safe_install_dir(install_dir: Path) -> None:
    marker = install_dir / INSTALL_MARKER

    if marker.is_file():
        return

    if install_dir == default_install_dir().resolve() and not any(install_dir.iterdir()):
        return

    if looks_like_ruflow_install(install_dir):
        return

    raise InstallerError(
        f"refusing to overwrite or remove a directory without {INSTALL_MARKER}: {install_dir}"
    )


def looks_like_ruflow_install(install_dir: Path) -> bool:
    if install_dir.name.lower() != APP_NAME.lower():
        return False

    try:
        entries = list(install_dir.iterdir())
    except OSError:
        return False

    if not entries:
        return True

    entry_names = {entry.name for entry in entries}
    if not entry_names.issubset(KNOWN_INSTALL_TOP_LEVEL_NAMES):
        return False

    return any(name in entry_names for name in ("RuFlow.exe", "RuFlowSetup.exe", "_internal"))


def write_uninstaller(install_dir: Path) -> None:
    if getattr(sys, "frozen", False):
        shutil.copy2(Path(sys.executable), install_dir / "RuFlowSetup.exe")
        return

    uninstall_bat = install_dir / "Uninstall RuFlow.bat"
    uninstall_bat.write_text(
        f'@echo off\r\n"{sys.executable}" "{Path(__file__).resolve()}" --uninstall --install-dir "{install_dir}"\r\n',
        encoding="utf-8",
    )


def create_start_menu_shortcut(install_dir: Path) -> None:
    start_menu_dir = (
        Path(os.environ["APPDATA"])
        / "Microsoft"
        / "Windows"
        / "Start Menu"
        / "Programs"
        / APP_NAME
    )
    start_menu_dir.mkdir(parents=True, exist_ok=True)
    create_shortcut(start_menu_dir / f"{APP_NAME}.lnk", install_dir / "RuFlow.exe", install_dir)
    create_shortcut(
        start_menu_dir / f"Uninstall {APP_NAME}.lnk",
        uninstall_command_target(install_dir),
        install_dir,
        arguments=f'--uninstall --install-dir "{install_dir}"',
    )


def create_desktop_shortcut_file(install_dir: Path) -> None:
    desktop = Path(os.environ["USERPROFILE"]) / "Desktop"
    if desktop.is_dir():
        create_shortcut(desktop / f"{APP_NAME}.lnk", install_dir / "RuFlow.exe", install_dir)


def create_shortcut(
    shortcut_path: Path,
    target_path: Path,
    working_dir: Path,
    *,
    arguments: str = "",
) -> None:
    script = textwrap.dedent(
        f"""
        $shell = New-Object -ComObject WScript.Shell
        $shortcut = $shell.CreateShortcut({ps_quote(str(shortcut_path))})
        $shortcut.TargetPath = {ps_quote(str(target_path))}
        $shortcut.Arguments = {ps_quote(arguments)}
        $shortcut.WorkingDirectory = {ps_quote(str(working_dir))}
        $shortcut.IconLocation = {ps_quote(str(target_path) + ',0')}
        $shortcut.Save()
        """
    ).strip()
    subprocess.run(
        ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def uninstall_command_target(install_dir: Path) -> Path:
    setup_exe = install_dir / "RuFlowSetup.exe"
    if setup_exe.is_file():
        return setup_exe
    return install_dir / "Uninstall RuFlow.bat"


def remove_shortcut_paths() -> None:
    candidates = [
        Path(os.environ.get("USERPROFILE", "")) / "Desktop" / f"{APP_NAME}.lnk",
        Path(os.environ.get("APPDATA", ""))
        / "Microsoft"
        / "Windows"
        / "Start Menu"
        / "Programs"
        / APP_NAME,
    ]
    for path in candidates:
        if not path.exists():
            continue
        if path.is_dir():
            shutil.rmtree(path)
        else:
            path.unlink()


def write_uninstall_registry(install_dir: Path) -> None:
    command = uninstall_command_string(install_dir)
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, UNINSTALL_REGISTRY_KEY) as key:
        winreg.SetValueEx(key, "DisplayName", 0, winreg.REG_SZ, APP_NAME)
        winreg.SetValueEx(key, "DisplayVersion", 0, winreg.REG_SZ, APP_VERSION)
        winreg.SetValueEx(key, "Publisher", 0, winreg.REG_SZ, PUBLISHER)
        winreg.SetValueEx(key, "InstallLocation", 0, winreg.REG_SZ, str(install_dir))
        winreg.SetValueEx(key, "DisplayIcon", 0, winreg.REG_SZ, str(install_dir / "RuFlow.exe"))
        winreg.SetValueEx(key, "UninstallString", 0, winreg.REG_SZ, command)
        winreg.SetValueEx(key, "QuietUninstallString", 0, winreg.REG_SZ, command)
        winreg.SetValueEx(key, "NoModify", 0, winreg.REG_DWORD, 1)
        winreg.SetValueEx(key, "NoRepair", 0, winreg.REG_DWORD, 1)


def remove_uninstall_registry() -> None:
    try:
        winreg.DeleteKey(winreg.HKEY_CURRENT_USER, UNINSTALL_REGISTRY_KEY)
    except FileNotFoundError:
        pass


def uninstall_command_string(install_dir: Path) -> str:
    setup_exe = install_dir / "RuFlowSetup.exe"
    if setup_exe.is_file():
        return f'"{setup_exe}" --uninstall --install-dir "{install_dir}"'
    return f'"{sys.executable}" "{Path(__file__).resolve()}" --uninstall --install-dir "{install_dir}"'


def schedule_directory_removal(install_dir: Path) -> None:
    script_path = Path(tempfile.gettempdir()) / "ruflow-uninstall.cmd"
    script_path.write_text(
        f'@echo off\r\nping 127.0.0.1 -n 3 > nul\r\nrmdir /s /q "{install_dir}"\r\ndel "%~f0"\r\n',
        encoding="utf-8",
    )
    subprocess.Popen(
        ["cmd.exe", "/C", str(script_path)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )


def ps_quote(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Install or uninstall RuFlow for the current Windows user")
    parser.add_argument("--uninstall", action="store_true", help="remove the installed app")
    parser.add_argument("--payload", default=str(bundled_payload_dir()), help="built RuFlow app directory")
    parser.add_argument("--install-dir", default=str(default_install_dir()), help="target install directory")
    parser.add_argument("--no-shortcuts", action="store_true", help="do not create Start Menu/Desktop shortcuts")
    parser.add_argument("--no-desktop-shortcut", action="store_true", help="do not create a Desktop shortcut")
    parser.add_argument("--no-registry", action="store_true", help="do not write Add/Remove Programs registry entries")
    parser.add_argument("--launch", action="store_true", help="launch RuFlow after install")
    return parser


def main(argv: list[str] | None = None) -> int:
    if sys.platform != "win32":
        print("RuFlow installer must be run on Windows.", file=sys.stderr)
        return 2

    args = build_parser().parse_args(argv)

    try:
        if args.uninstall:
            uninstall(
                install_dir=Path(args.install_dir),
                remove_shortcuts=not args.no_shortcuts,
                remove_registry=not args.no_registry,
            )
        else:
            install(
                payload_dir=Path(args.payload),
                install_dir=Path(args.install_dir),
                create_shortcuts=not args.no_shortcuts,
                create_desktop_shortcut=not args.no_desktop_shortcut,
                write_registry=not args.no_registry,
                launch=args.launch,
            )
    except InstallerError as error:
        print(f"Installer error: {error}", file=sys.stderr)
        return 1
    except PermissionError as error:
        print(f"Installer error: permission denied: {error}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
