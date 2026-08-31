#!/usr/bin/env python3
"""Reparos locais, validados e reversíveis usados pelo Port Doctor R36S."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import posixpath
import re
import shutil
import struct
import subprocess
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path


MIN_LIBRARY_SIZE = 4096
MIN_GAME_DATA_SIZE = 1024 * 1024
MIN_RUNTIME_SIZE = 1024 * 1024
MACHINES = {"armhf": (1, 40), "aarch64": (2, 183), "x86_64": (2, 62)}
FFMPEG_SONAME = re.compile(
    r"lib(?:av(?:codec|format|util|device|filter|resample)|sw(?:resample|scale)|postproc)\.so(?:\.[0-9]+)+$"
)
PROTECTED_LIBRARY = re.compile(
    r"(?:ld-linux.*|libc\.so.*|libpthread\.so.*|libdl\.so.*|libm\.so.*|"
    r"libgcc_s\.so.*|libstdc\+\+\.so.*|libEGL\.so.*|libGL(?:ESv[12])?\.so.*|"
    r"libmali.*|libdrm\.so.*)$"
)


def fail(message: str) -> None:
    print(f"Port Doctor: {message}", file=sys.stderr)
    raise SystemExit(1)


def safe_slug(value: str) -> str:
    slug = re.sub(r"[^a-z0-9._-]+", "-", value.lower()).strip("-.")
    return slug or "port"


def inside(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def elf_matches(data: bytes, architecture: str) -> tuple[bool, str]:
    if len(data) < MIN_LIBRARY_SIZE:
        return False, f"arquivo tem somente {len(data)} bytes"
    if data[:4] != b"\x7fELF" or len(data) < 20:
        return False, "arquivo não possui cabeçalho ELF"
    elf_class = data[4]
    byte_order = data[5]
    if byte_order not in (1, 2):
        return False, "ordem de bytes ELF inválida"
    expected = MACHINES.get(architecture)
    machine = struct.unpack("<H" if byte_order == 1 else ">H", data[18:20])[0]
    if expected and (elf_class, machine) != expected:
        return False, f"ELF incompatível: classe {elf_class}, máquina {machine}"
    return True, "ELF validado"


def read_valid_elf(path: Path, architecture: str) -> bytes | None:
    try:
        data = path.read_bytes()
    except (OSError, MemoryError):
        return None
    valid, _ = elf_matches(data, architecture)
    return data if valid else None


def atomic_write(path: Path, data: bytes, mode: int | None = None) -> None:
    temporary = path.with_name(path.name + ".portdoctor.tmp")
    temporary.write_bytes(data)
    if mode is not None:
        os.chmod(temporary, mode)
    os.replace(temporary, path)


def newest_log(port_home: Path, launcher: Path) -> Path | None:
    candidates: list[Path] = []
    for direct in (port_home / "log.txt", port_home / "log.log", launcher.with_name("log.txt")):
        if direct.is_file():
            candidates.append(direct)
    try:
        for pattern in ("*.log", "*log*.txt"):
            candidates.extend(path for path in port_home.rglob(pattern) if path.is_file())
    except OSError:
        pass
    unique = {str(path.resolve()): path.resolve() for path in candidates}
    return max(unique.values(), key=lambda path: path.stat().st_mtime_ns, default=None)


def log_snapshot(port_home: Path, launcher: Path) -> dict | None:
    path = newest_log(port_home, launcher)
    if path is None:
        return None
    try:
        data = path.read_bytes()
        stat = path.stat()
    except OSError:
        return None
    return {
        "path": str(path),
        "size": len(data),
        "mtime_ns": stat.st_mtime_ns,
        "sha256": hashlib.sha256(data).hexdigest(),
    }


def oom_snapshot() -> dict[str, object]:
    try:
        result = subprocess.run(["dmesg"], capture_output=True, text=True, errors="replace")
        lines = [line for line in result.stdout.splitlines()
                 if re.search(r"Out of memory: Kill process|Killed process .+ total-vm", line, re.I)]
    except OSError:
        lines = []
    return {
        "count": len(lines),
        "sha256": hashlib.sha256("\n".join(lines).encode()).hexdigest(),
    }


def new_backup(doctor_home: Path, port_home: Path, launcher: Path, action: str) -> tuple[Path, dict]:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S-%f")
    folder = doctor_home / "conf" / "backups" / safe_slug(port_home.name) / stamp
    folder.mkdir(parents=True, exist_ok=False)
    launcher_backup = folder / "launcher.original.sh"
    shutil.copy2(launcher, launcher_backup)
    manifest = {
        "format": 2,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "action": action,
        "port_home": str(port_home),
        "launcher_path": str(launcher),
        "launcher_backup": str(launcher_backup),
        "created_files": [],
        "replaced_files": [],
        "restored": False,
        "verification": "pending",
        "log_before": log_snapshot(port_home, launcher),
        "crashes_before": crash_snapshot(port_home),
    }
    return folder, manifest


def crash_snapshot(port_home: Path) -> dict:
    """Bounded crash evidence, excluding bundled/old crashes when comparing runs."""
    result = {}
    for directory in (port_home, port_home / 'conf', port_home / 'logs'):
        for path in directory.glob('tombstone_*'):
            try:
                if not inside(path, port_home) or not path.is_file():
                    continue
                result[str(path)] = path.stat().st_mtime_ns
            except OSError:
                continue
    return result


def new_native_crashes(port_home: Path, before: dict, since_ns=0) -> list[str]:
    failures = []
    for name, stamp in crash_snapshot(port_home).items():
        if stamp <= max(int(before.get(name, 0)), since_ns):
            continue
        try:
            with Path(name).open('rb') as stream:
                text = stream.read(65536).decode('utf-8', errors='replace')
        except OSError:
            continue
        if re.search(r'signal\s+\d+\s+\(SIG(?:BUS|SEGV|ILL|ABRT)\)', text, re.I):
            failures.append(name)
    return failures


def save_manifest(folder: Path, manifest: dict) -> None:
    atomic_write(folder / "manifest.json", (json.dumps(manifest, indent=2, ensure_ascii=False) + "\n").encode())


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def game_data_candidates(port_home: Path) -> list[Path]:
    destination = (port_home / "saves" / "game.droid").resolve()
    candidates: list[Path] = []
    try:
        for candidate in port_home.rglob("*"):
            if candidate.name.lower() != "game.droid" or not candidate.is_file():
                continue
            resolved = candidate.resolve()
            if resolved == destination or not inside(resolved, port_home):
                continue
            if resolved.stat().st_size >= MIN_GAME_DATA_SIZE:
                candidates.append(resolved)
    except OSError:
        pass
    return sorted(candidates, key=lambda path: (len(path.parts), str(path).lower()))


def locate_game_archive(port_home: Path, launcher: Path, log_text: str = "") -> Path | None:
    matches = re.findall(r"Loading APK\s+(.+?\.port)(?:Just before|\s|$)", log_text)
    for value in reversed(matches):
        candidate = Path(value.strip())
        if not candidate.is_absolute():
            candidate = port_home / candidate
        try:
            candidate = candidate.resolve()
        except OSError:
            continue
        if inside(candidate, port_home) and candidate.is_file():
            return candidate
    try:
        for config in sorted(port_home.glob("*.json")):
            data = json.loads(config.read_text(encoding="utf-8", errors="replace"))
            value = data.get("apk_path") if isinstance(data, dict) else None
            if isinstance(value, str) and value.lower().endswith(".port"):
                candidate = (port_home / value).resolve()
                if inside(candidate, port_home) and candidate.is_file():
                    return candidate
    except (OSError, ValueError):
        pass
    archives = sorted(path.resolve() for path in port_home.glob("*.port") if path.is_file())
    return archives[0] if len(archives) == 1 else None


def command_repack_game_archive(args: argparse.Namespace) -> None:
    launcher = Path(args.launcher).resolve()
    port_home = Path(args.port_home).resolve()
    doctor_home = Path(args.doctor_home).resolve()
    log_path = newest_log(port_home, launcher)
    log_text = ""
    if log_path:
        try:
            log_text = log_path.read_bytes()[-1024 * 1024:].decode("utf-8", errors="replace")
        except OSError:
            pass
    archive = locate_game_archive(port_home, launcher, log_text)
    if not launcher.is_file() or not port_home.is_dir() or not doctor_home.is_dir() or archive is None:
        fail("launcher ou arquivo .port não foi encontrado")
    try:
        with zipfile.ZipFile(archive, "r") as source_zip:
            compressed = [info for info in source_zip.infolist()
                          if not info.is_dir() and info.compress_type != zipfile.ZIP_STORED]
    except (OSError, zipfile.BadZipFile):
        fail("o arquivo .port não é um ZIP válido")
    if not compressed:
        interrupted_backup = archive.with_name(archive.name + ".before-portdoctor")
        if interrupted_backup.is_file():
            try:
                with zipfile.ZipFile(interrupted_backup, "r") as previous_zip:
                    previous_compressed = [info for info in previous_zip.infolist()
                                           if not info.is_dir() and info.compress_type != zipfile.ZIP_STORED]
                    previous_failure = previous_zip.testzip()
            except (OSError, zipfile.BadZipFile):
                previous_compressed = []
                previous_failure = "arquivo inválido"
            if previous_compressed and not previous_failure:
                folder, manifest = new_backup(
                    doctor_home, port_home, launcher, "repack-game-archive"
                )
                original = folder / "files-original" / archive.name
                original.parent.mkdir(parents=True, exist_ok=True)
                os.replace(interrupted_backup, original)
                manifest["replaced_files"].append({"path": str(archive), "backup": str(original)})
                manifest["archive"] = str(archive)
                manifest["entries_repacked"] = len(previous_compressed)
                manifest["sha256"] = sha256_file(archive)
                manifest["recovered_interrupted_repair"] = True
                save_manifest(folder, manifest)
                print(f"Port Doctor: reconstrução anterior recuperada e registrada; backup salvo em {folder}")
                return
        print("Port Doctor: o arquivo .port já está totalmente no modo armazenado; nenhuma alteração necessária.")
        return
    required = archive.stat().st_size * 2 + 134217728
    if shutil.disk_usage(port_home).free < required:
        fail("espaço livre insuficiente para reconstruir o .port e guardar o backup")

    folder, manifest = new_backup(doctor_home, port_home, launcher, "repack-game-archive")
    original = folder / "files-original" / archive.name
    original.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(archive, original)
    temporary = archive.with_name(archive.name + ".portdoctor.tmp")
    try:
        with zipfile.ZipFile(archive, "r") as source_zip, zipfile.ZipFile(
            temporary, "w", compression=zipfile.ZIP_STORED, allowZip64=True
        ) as target_zip:
            for info in source_zip.infolist():
                copied = zipfile.ZipInfo(info.filename, date_time=info.date_time)
                copied.comment = info.comment
                copied.extra = info.extra
                copied.internal_attr = info.internal_attr
                copied.external_attr = info.external_attr
                copied.create_system = info.create_system
                copied.compress_type = zipfile.ZIP_STORED
                if info.is_dir():
                    target_zip.writestr(copied, b"")
                else:
                    with source_zip.open(info, "r") as source, target_zip.open(copied, "w", force_zip64=True) as target:
                        shutil.copyfileobj(source, target, length=1024 * 1024)
        with zipfile.ZipFile(temporary, "r") as check_zip:
            failure = check_zip.testzip()
            if failure:
                fail("o pacote reconstruído falhou na validação: " + failure)
            if any(not info.is_dir() and info.compress_type != zipfile.ZIP_STORED for info in check_zip.infolist()):
                fail("o pacote reconstruído ainda contém entradas comprimidas")
        os.replace(temporary, archive)
    finally:
        if temporary.exists():
            temporary.unlink()
    manifest["replaced_files"].append({"path": str(archive), "backup": str(original)})
    manifest["archive"] = str(archive)
    manifest["entries_repacked"] = len(compressed)
    manifest["sha256"] = sha256_file(archive)
    save_manifest(folder, manifest)
    print(f"Port Doctor: {len(compressed)} entrada(s) reconstruída(s) sem compressão; backup salvo em {folder}")


def validate_executable_jar(path: Path) -> tuple[bool, str]:
    try:
        with zipfile.ZipFile(path, "r") as archive:
            if archive.testzip():
                return False, "o ZIP contém uma entrada corrompida"
            names = set(archive.namelist())
            if "META-INF/MANIFEST.MF" not in names:
                return False, "META-INF/MANIFEST.MF está ausente"
            manifest = archive.read("META-INF/MANIFEST.MF").decode("utf-8", errors="replace")
            match = re.search(r"(?mi)^Main-Class:\s*([^\r\n]+)", manifest)
            if not match:
                return False, "Main-Class está ausente do manifesto"
            main_class = match.group(1).strip().replace(".", "/") + ".class"
            if main_class not in names:
                return False, f"a classe principal {main_class} está ausente"
    except (OSError, zipfile.BadZipFile, KeyError):
        return False, "o arquivo não é um JAR/ZIP legível"
    return True, "JAR executável validado"


def locate_broken_jar(port_home: Path, log_text: str) -> Path | None:
    matches = re.findall(r"Invalid or corrupt jarfile\s+([^\r\n]+\.jar)", log_text, re.I)
    for value in reversed(matches):
        candidate = Path(value.strip())
        if not candidate.is_absolute():
            candidate = port_home / candidate
        try:
            candidate = candidate.resolve()
        except OSError:
            continue
        if inside(candidate, port_home) and candidate.is_file():
            return candidate
    candidates = sorted(path.resolve() for path in port_home.glob("*patched*.jar") if path.is_file())
    return candidates[0] if len(candidates) == 1 else None


def locate_jar_base(port_home: Path, target: Path) -> Path | None:
    candidates: list[Path] = []
    try:
        for candidate in port_home.rglob("*"):
            if candidate.resolve() == target or not candidate.is_file():
                continue
            if candidate.suffix.lower() not in (".jar", ".zip"):
                continue
            valid, _ = validate_executable_jar(candidate)
            if valid:
                candidates.append(candidate.resolve())
    except OSError:
        pass
    return min(candidates, key=lambda path: (len(path.parts), path.stat().st_size, str(path)), default=None)


def copy_zip_entry(source_zip: zipfile.ZipFile, target_zip: zipfile.ZipFile,
                   info: zipfile.ZipInfo) -> None:
    copied = zipfile.ZipInfo(info.filename, date_time=info.date_time)
    copied.comment = info.comment
    copied.extra = info.extra
    copied.internal_attr = info.internal_attr
    copied.external_attr = info.external_attr
    copied.create_system = info.create_system
    copied.compress_type = info.compress_type
    if info.is_dir():
        target_zip.writestr(copied, b"")
    else:
        with source_zip.open(info, "r") as source, target_zip.open(copied, "w", force_zip64=True) as target:
            shutil.copyfileobj(source, target, length=1024 * 1024)


def command_repair_java_archive(args: argparse.Namespace) -> None:
    launcher = Path(args.launcher).resolve()
    port_home = Path(args.port_home).resolve()
    doctor_home = Path(args.doctor_home).resolve()
    if not launcher.is_file() or not port_home.is_dir() or not doctor_home.is_dir():
        fail("launcher, port ou Port Doctor não foi encontrado")
    log_path = newest_log(port_home, launcher)
    log_text = ""
    if log_path:
        try:
            log_text = log_path.read_bytes()[-1024 * 1024:].decode("utf-8", errors="replace")
        except OSError:
            pass
    target = locate_broken_jar(port_home, log_text)
    if target is None:
        fail("o JAR que falhou não foi localizado com segurança")

    candidate_arg = getattr(args, "candidate", None)
    candidate = Path(candidate_arg).resolve() if candidate_arg else None
    temporary = target.with_name(target.name + ".portdoctor.tmp")
    temporary.unlink(missing_ok=True)
    try:
        if candidate is not None:
            valid, reason = validate_executable_jar(candidate)
            if not valid:
                fail("a cópia candidata foi recusada: " + reason)
            shutil.copy2(candidate, temporary)
            base = candidate
            merged_entries = 0
        else:
            base = locate_jar_base(port_home, target)
            if base is None:
                fail("nenhum JAR-base íntegro com manifesto e classe principal foi encontrado")
            try:
                with zipfile.ZipFile(base, "r") as base_zip, zipfile.ZipFile(target, "r") as resource_zip, \
                        zipfile.ZipFile(temporary, "w", allowZip64=True) as output_zip:
                    written: set[str] = set()
                    for info in base_zip.infolist():
                        copy_zip_entry(base_zip, output_zip, info)
                        written.add(info.filename)
                    merged_entries = 0
                    for info in resource_zip.infolist():
                        if info.filename in written:
                            continue
                        copy_zip_entry(resource_zip, output_zip, info)
                        written.add(info.filename)
                        merged_entries += 1
            except (OSError, zipfile.BadZipFile):
                fail("não foi possível unir o JAR-base aos recursos preservados")
        valid, reason = validate_executable_jar(temporary)
        if not valid:
            fail("o JAR reconstruído foi recusado: " + reason)
        required = target.stat().st_size + temporary.stat().st_size + 134217728
        if shutil.disk_usage(port_home).free < required:
            fail("espaço livre insuficiente para instalar o JAR reconstruído e guardar o backup")

        folder, manifest = new_backup(doctor_home, port_home, launcher, "repair-java-archive")
        original = folder / "files-original" / target.name
        original.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(target, original)
        os.replace(temporary, target)
        manifest["replaced_files"].append({"path": str(target), "backup": str(original)})
        manifest["jar"] = str(target)
        manifest["base"] = str(base)
        manifest["merged_entries"] = merged_entries
        manifest["sha256"] = sha256_file(target)
        save_manifest(folder, manifest)
        print(f"Port Doctor: JAR executável reconstruído e validado; backup salvo em {folder}")
    finally:
        temporary.unlink(missing_ok=True)


def command_install_game_data(args: argparse.Namespace) -> None:
    launcher = Path(args.launcher).resolve()
    port_home = Path(args.port_home).resolve()
    doctor_home = Path(args.doctor_home).resolve()
    source = Path(args.source).resolve()
    if not launcher.is_file() or not port_home.is_dir() or not doctor_home.is_dir():
        fail("launcher, port ou Port Doctor não foi encontrado")
    if not inside(source, port_home) or not source.is_file() or source.name.lower() != "game.droid":
        fail("game.droid precisa estar dentro da pasta do próprio port")
    if source.stat().st_size < MIN_GAME_DATA_SIZE:
        fail("game.droid é pequeno demais e parece incompleto")

    destination = (port_home / "saves" / "game.droid").resolve()
    if source == destination:
        fail("game.droid já está no destino esperado")
    folder, manifest = new_backup(doctor_home, port_home, launcher, "install-game-data")
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        original = folder / "files-original" / "game.droid"
        original.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(destination, original)
        manifest["replaced_files"].append({"path": str(destination), "backup": str(original)})
    else:
        manifest["created_files"].append(str(destination))

    temporary = destination.with_name(destination.name + ".portdoctor.tmp")
    try:
        shutil.copy2(source, temporary)
        if temporary.stat().st_size != source.stat().st_size or sha256_file(temporary) != sha256_file(source):
            fail("a cópia de game.droid não passou na validação SHA-256")
        os.replace(temporary, destination)
    finally:
        if temporary.exists():
            temporary.unlink()
    manifest["source"] = str(source)
    manifest["destination"] = str(destination)
    manifest["sha256"] = sha256_file(destination)
    save_manifest(folder, manifest)
    print(f"Port Doctor: game.droid instalado com backup em {folder}")


def insert_export(launcher: Path, export_line: str, marker: str, action: str,
                  doctor_home: Path, port_home: Path) -> bool:
    original = launcher.read_text(encoding="utf-8", errors="surrogateescape")
    if marker in original:
        print(f"Port Doctor: {marker} já está configurado; nenhuma alteração necessária.")
        return False

    lines = original.splitlines(keepends=True)
    insertion = 1 if lines and lines[0].startswith("#!") else 0
    for index, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("export LD_LIBRARY_PATH=") or stripped.startswith("export SDL_AUDIODRIVER="):
            insertion = index + 1
    newline = "\r\n" if "\r\n" in original else "\n"
    lines.insert(insertion, export_line + newline)
    updated = "".join(lines)

    folder, manifest = new_backup(doctor_home, port_home, launcher, action)
    mode = launcher.stat().st_mode & 0o777
    atomic_write(launcher, updated.encode("utf-8", errors="surrogateescape"), mode)
    save_manifest(folder, manifest)
    print(f"Port Doctor: launcher atualizado; backup salvo em {folder}")
    return True


def insert_or_replace_block(launcher: Path, block: str, start_marker: str, end_marker: str,
                            action: str, doctor_home: Path, port_home: Path) -> bool:
    original = launcher.read_text(encoding="utf-8", errors="surrogateescape")
    if start_marker not in original:
        return insert_export(launcher, block, start_marker, action, doctor_home, port_home)
    pattern = re.compile(
        rf"^[^\r\n]*{re.escape(start_marker)}.*?^[^\r\n]*{re.escape(end_marker)}[^\r\n]*(?:\r?\n)?",
        re.MULTILINE | re.DOTALL,
    )
    newline = "\r\n" if "\r\n" in original else "\n"
    replacement = block.replace("\n", newline) + newline
    updated, count = pattern.subn(lambda _: replacement, original, count=1)
    if count != 1:
        fail("o bloco de reparo anterior está incompleto; use Desfazer último reparo antes de continuar")
    if updated == original:
        print(f"Port Doctor: {start_marker} já está atualizado; nenhuma alteração necessária.")
        return False
    folder, manifest = new_backup(doctor_home, port_home, launcher, action)
    mode = launcher.stat().st_mode & 0o777
    atomic_write(launcher, updated.encode("utf-8", errors="surrogateescape"), mode)
    manifest["upgraded_previous_repair"] = True
    save_manifest(folder, manifest)
    print(f"Port Doctor: reparo anterior atualizado; backup salvo em {folder}")
    return True


def command_audio_alsa(args: argparse.Namespace) -> None:
    launcher = Path(args.launcher).resolve()
    port_home = Path(args.port_home).resolve()
    doctor_home = Path(args.doctor_home).resolve()
    if not launcher.is_file() or not port_home.is_dir():
        fail("launcher ou pasta do port não foi encontrado")
    insert_export(
        launcher,
        'export ALSOFT_DRIVERS="alsa" # Port Doctor: audio backend',
        "Port Doctor: audio backend",
        "audio-alsa",
        doctor_home,
        port_home,
    )


def command_repair_launcher_header(args: argparse.Namespace) -> None:
    launcher = Path(args.launcher).resolve()
    port_home = Path(args.port_home).resolve()
    doctor_home = Path(args.doctor_home).resolve()
    if not launcher.is_file() or not port_home.is_dir() or not doctor_home.is_dir():
        fail("launcher, port ou Port Doctor não foi encontrado")
    original = launcher.read_text(encoding="utf-8", errors="surrogateescape")
    if original.startswith("#!"):
        print("Port Doctor: o interpretador já está na primeira linha; nenhuma alteração necessária.")
        return
    lines = original.splitlines(keepends=True)
    shebang_index = next((index for index, line in enumerate(lines[:6]) if line.startswith("#!/")), None)
    if shebang_index is None:
        fail("nenhum #! seguro foi encontrado nas primeiras linhas do launcher")
    prefix = "".join(lines[:shebang_index])
    if any(line.strip() and not re.fullmatch(r"[A-Za-z0-9 ._+-]+", line.strip()) for line in lines[:shebang_index]):
        fail("o conteúdo anterior ao #! não é um prefixo simples e exige revisão manual")
    folder, manifest = new_backup(doctor_home, port_home, launcher, "repair-launcher-header")
    mode = launcher.stat().st_mode & 0o777
    atomic_write(launcher, "".join(lines[shebang_index:]).encode("utf-8", errors="surrogateescape"), mode)
    manifest["removed_prefix"] = prefix
    save_manifest(folder, manifest)
    print(f"Port Doctor: cabeçalho do launcher corrigido; backup salvo em {folder}")


def command_repair_shell_defaults(args: argparse.Namespace) -> None:
    launcher = Path(args.launcher).resolve()
    port_home = Path(args.port_home).resolve()
    doctor_home = Path(args.doctor_home).resolve()
    if not launcher.is_file() or not port_home.is_dir() or not doctor_home.is_dir():
        fail("launcher, port ou Port Doctor não foi encontrado")
    original = launcher.read_text(encoding="utf-8", errors="surrogateescape")
    updated, count = re.subn(r"\$\{([A-Z][A-Z0-9_]*):([0-9]+)\}", r"${\1:-\2}", original)
    if count == 0:
        print("Port Doctor: nenhum valor-padrão de shell incorreto foi encontrado.")
        return
    folder, manifest = new_backup(doctor_home, port_home, launcher, "repair-shell-defaults")
    mode = launcher.stat().st_mode & 0o777
    atomic_write(launcher, updated.encode("utf-8", errors="surrogateescape"), mode)
    manifest["expressions_fixed"] = count
    save_manifest(folder, manifest)
    print(f"Port Doctor: {count} valor(es)-padrão do launcher corrigido(s); backup salvo em {folder}")




def valid_squashfs(path: Path) -> tuple[bool, str]:
    try:
        size = path.stat().st_size
        with path.open("rb") as stream:
            magic = stream.read(4)
    except OSError as error:
        return False, str(error)
    if size < MIN_RUNTIME_SIZE:
        return False, f"imagem tem somente {size} bytes"
    if magic not in (b"hsqs", b"sqsh"):
        return False, "imagem não possui cabeçalho SquashFS"
    return True, "SquashFS validado"


def find_local_runtime(port_home: Path, runtime: str) -> Path | None:
    if not runtime or Path(runtime).name != runtime or not runtime.endswith(".squashfs"):
        return None
    try:
        candidates = sorted(
            (path for path in port_home.rglob(runtime) if path.is_file() and not path.is_symlink()),
            key=lambda path: (len(path.parts), str(path)),
        )
    except OSError:
        return None
    for candidate in candidates:
        valid, _ = valid_squashfs(candidate)
        if valid:
            return candidate
    return None


def command_repair_local_runtime(args: argparse.Namespace) -> None:
    launcher = Path(args.launcher).resolve()
    port_home = Path(args.port_home).resolve()
    doctor_home = Path(args.doctor_home).resolve()
    runtime = str(args.runtime or "").strip()
    if not launcher.is_file() or not port_home.is_dir() or not doctor_home.is_dir():
        fail("launcher, port ou Port Doctor não foi encontrado")
    local_runtime = find_local_runtime(port_home, runtime)
    if local_runtime is None:
        fail(f"nenhuma cópia SquashFS local válida de {runtime or 'runtime'} foi encontrada")
    relative = local_runtime.relative_to(port_home).as_posix()
    if any(character in relative for character in ('\n', '\r', '"', '`', '$')):
        fail("o caminho do runtime local não pode ser inserido com segurança no launcher")

    original = launcher.read_text(encoding="utf-8", errors="surrogateescape")
    marker = "Port Doctor: local runtime fallback"
    if marker in original:
        print(f"Port Doctor: fallback local de {runtime} já está configurado; nenhuma alteração necessária.")
        return
    guard = re.compile(
        r'(?m)^(\s*)if\s+\[\s*!\s+-f\s+"\$controlfolder/libs/\$RUNTIME"\s*\]\s*;\s*then\s*$'
    )
    replacement = (
        r'\1if [ ! -f "$controlfolder/libs/$RUNTIME" ] '
        rf'&& [ ! -f "$GAMEDIR/{relative}" ]; then # {marker}'
    )
    updated, count = guard.subn(replacement, original)
    if count == 0:
        fail("o launcher não contém uma verificação de runtime localizável e não será alterado")

    folder, manifest = new_backup(doctor_home, port_home, launcher, "repair-local-runtime")
    mode = launcher.stat().st_mode & 0o777
    atomic_write(launcher, updated.encode("utf-8", errors="surrogateescape"), mode)
    manifest["runtime"] = runtime
    manifest["local_runtime"] = str(local_runtime)
    manifest["guards_updated"] = count
    save_manifest(folder, manifest)
    print(f"Port Doctor: runtime local validado em {local_runtime}")
    print(f"Port Doctor: {count} verificações do launcher ajustadas; backup salvo em {folder}")


def command_audio_busy(args: argparse.Namespace) -> None:
    launcher = Path(args.launcher).resolve()
    port_home = Path(args.port_home).resolve()
    doctor_home = Path(args.doctor_home).resolve()
    if not launcher.is_file() or not port_home.is_dir():
        fail("launcher ou pasta do port não foi encontrado")
    block = """# Port Doctor: audio busy start
PORTDOCTOR_AUDIO_RUNTIME="/run/user/$(id -u)"
if [ -S "$PORTDOCTOR_AUDIO_RUNTIME/pulse/native" ]; then
    export PULSE_SERVER="unix:$PORTDOCTOR_AUDIO_RUNTIME/pulse/native"
    export SDL_AUDIODRIVER="pulseaudio"
else
    export SDL_AUDIODRIVER="alsa"
    export ALSOFT_DRIVERS="alsa"
    export AUDIODEV="dmix"
    export ALSOFT_ALSA_DEVICE="dmix"
    if command -v fuser >/dev/null 2>&1; then
        PORTDOCTOR_AUDIO_UID="$(id -u)"
        for PORTDOCTOR_AUDIO_PID in $(fuser /dev/snd/pcm* 2>/dev/null); do
            PORTDOCTOR_AUDIO_COMM="$(cat "/proc/$PORTDOCTOR_AUDIO_PID/comm" 2>/dev/null || true)"
            PORTDOCTOR_AUDIO_OWNER="$(stat -c %u "/proc/$PORTDOCTOR_AUDIO_PID" 2>/dev/null || true)"
            case "$PORTDOCTOR_AUDIO_COMM" in
                pipewire|pipewire-pulse|pulseaudio|mpv|ffplay|aplay)
                    if [ "$PORTDOCTOR_AUDIO_OWNER" = "$PORTDOCTOR_AUDIO_UID" ]; then
                        kill -TERM "$PORTDOCTOR_AUDIO_PID" 2>/dev/null || true
                    fi
                    ;;
            esac
        done
        sleep 0.4
    fi
fi
unset PORTDOCTOR_AUDIO_RUNTIME PORTDOCTOR_AUDIO_UID PORTDOCTOR_AUDIO_PID PORTDOCTOR_AUDIO_COMM PORTDOCTOR_AUDIO_OWNER
# Port Doctor: audio busy end"""
    insert_or_replace_block(
        launcher,
        block,
        "Port Doctor: audio busy start",
        "Port Doctor: audio busy end",
        "audio-busy",
        doctor_home,
        port_home,
    )


def portmaster_roots(pm_home: Path) -> list[Path]:
    candidates = [
        pm_home,
        Path("/opt/system/Tools/PortMaster"),
        Path("/opt/tools/PortMaster"),
        Path("/roms/tools/PortMaster"),
        Path("/roms2/tools/PortMaster"),
        Path("/roms/ports/PortMaster"),
    ]
    result: list[Path] = []
    seen: set[str] = set()
    for candidate in candidates:
        try:
            key = str(candidate.resolve())
        except OSError:
            key = str(candidate)
        if key not in seen and candidate.exists():
            seen.add(key)
            result.append(candidate)
    return result


def compat_pack_candidates(doctor_home: Path, library: str, architecture: str):
    pack_root = doctor_home / "compat-packs"
    if not pack_root.is_dir():
        return
    try:
        manifests = sorted(pack_root.rglob("pack.json"))
    except OSError:
        return
    for manifest_path in manifests:
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if manifest.get("format") != 1 or not manifest.get("license"):
            continue
        for entry in manifest.get("files", []):
            if not isinstance(entry, dict) or entry.get("architecture") != architecture:
                continue
            if entry.get("name") != library or not re.fullmatch(r"[A-Fa-f0-9]{64}", str(entry.get("sha256", ""))):
                continue
            candidate = manifest_path.parent / str(entry.get("path", ""))
            if not inside(candidate, manifest_path.parent) or not candidate.is_file():
                continue
            try:
                digest = hashlib.sha256(candidate.read_bytes()).hexdigest()
            except OSError:
                continue
            if digest.lower() == str(entry["sha256"]).lower():
                yield candidate


def normal_candidates(port_home: Path, pm_home: Path, doctor_home: Path,
                      library: str, architecture: str):
    yield from compat_pack_candidates(doctor_home, library, architecture) or ()
    roots = [port_home / "lib", port_home / "libs"]
    ports_root = port_home.parent
    if ports_root.is_dir():
        try:
            for sibling in sorted(ports_root.iterdir()):
                if sibling.is_dir() and sibling.resolve() != port_home.resolve():
                    roots.extend((sibling / "lib", sibling / "libs"))
        except OSError:
            pass
    for master in portmaster_roots(pm_home):
        roots.extend((master / "runtimes", master / "libs"))
    for root in roots:
        if not root.exists():
            continue
        try:
            for candidate in root.rglob(library):
                if candidate.is_file():
                    yield candidate
        except OSError:
            continue


def runtime_image_allowed(image: Path, runtimes: list[str]) -> bool:
    lowered = image.name.lower()
    for runtime in runtimes:
        base = runtime.lower().removesuffix(".squashfs")
        if lowered.startswith(base) and lowered.endswith(".squashfs"):
            return True
    return False


def squashfs_candidates(pm_home: Path, library: str, runtimes: list[str], architecture: str):
    unsquashfs = shutil.which("unsquashfs")
    if not unsquashfs:
        return
    images = []
    for master in portmaster_roots(pm_home):
        for root in (master / "libs", master / "runtimes"):
            if root.exists():
                try:
                    images.extend(root.rglob("*.squashfs"))
                except OSError:
                    pass
    for image in sorted(set(images)):
        if not runtime_image_allowed(image, runtimes):
            continue
        listing = subprocess.run(
            [unsquashfs, "-ll", str(image)], capture_output=True, text=True, errors="replace"
        )
        if listing.returncode != 0:
            continue
        for line in listing.stdout.splitlines():
            match = re.search(r"squashfs-root/(.+?)(?:\s+->\s+.*)?$", line)
            if not match:
                continue
            inner = match.group(1)
            inner_name = inner.rsplit("/", 1)[-1]
            if inner_name != library and not inner_name.startswith(library + "."):
                continue
            extraction_paths = [inner]
            link = re.search(r"\s+->\s+(.+?)\s*$", line)
            if link:
                target = link.group(1)
                if target.startswith("/"):
                    target = target.lstrip("/")
                else:
                    target = posixpath.normpath(posixpath.join(posixpath.dirname(inner), target))
                extraction_paths.insert(0, target)
            for extraction_path in extraction_paths:
                extracted = subprocess.run(
                    [unsquashfs, "-cat", str(image), extraction_path], capture_output=True
                )
                if extracted.returncode == 0:
                    valid, _ = elf_matches(extracted.stdout, architecture)
                    if valid:
                        yield image, extraction_path, extracted.stdout
                        break


def find_library(port_home: Path, pm_home: Path, doctor_home: Path, library: str,
                 runtimes: list[str], architecture: str) -> tuple[str, bytes] | None:
    for candidate in normal_candidates(port_home, pm_home, doctor_home, library, architecture):
        data = read_valid_elf(candidate, architecture)
        if data is not None:
            return str(candidate), data
    for image, inner, data in squashfs_candidates(pm_home, library, runtimes, architecture) or ():
        return f"{image}:{inner}", data
    return None


def library_export(port_home: Path, launcher_text: str) -> str:
    if re.search(r"^\s*GAMEDIR=", launcher_text, re.MULTILINE):
        return 'export LD_LIBRARY_PATH="$GAMEDIR/libs.portdoctor:${LD_LIBRARY_PATH:-}" # Port Doctor: local libraries'
    escaped = str(port_home / "libs.portdoctor").replace("'", "'\"'\"'")
    return f"export LD_LIBRARY_PATH='{escaped}':\"${{LD_LIBRARY_PATH:-}}\" # Port Doctor: local libraries"


def validate_local_bundle(source_dir: Path, executable: Path, architecture: str,
                          libraries: set[str], search_dirs: list[Path] | None = None) -> dict[str, object]:
    loaders = {
        "aarch64": Path("/lib/ld-linux-aarch64.so.1"),
        "armhf": Path("/lib/ld-linux-armhf.so.3"),
        "x86_64": Path("/lib64/ld-linux-x86-64.so.2"),
    }
    loader = loaders.get(architecture)
    if loader is None or not loader.is_file():
        fail(f"o carregador dinâmico de {architecture} não foi encontrado para validar o conjunto")
    environment = os.environ.copy()
    previous = environment.get("LD_LIBRARY_PATH", "")
    ordered_dirs: list[Path] = []
    for directory in [*(search_dirs or []), source_dir]:
        if directory not in ordered_dirs and directory.is_dir():
            ordered_dirs.append(directory)
    search_path = ":".join(str(directory) for directory in ordered_dirs)
    environment["LD_LIBRARY_PATH"] = search_path + ((":" + previous) if previous else "")
    result = subprocess.run(
        [str(loader), "--list", str(executable)],
        capture_output=True, text=True, errors="replace", env=environment,
    )
    output = result.stdout + result.stderr
    if result.returncode != 0 or re.search(r"\bnot found\b|file too short", output, re.I):
        reason = output.strip().splitlines()[-1] if output.strip() else f"código {result.returncode}"
        fail(f"o conjunto candidato falhou no teste do carregador: {reason}")
    unresolved = []
    for library in sorted(libraries):
        expected = source_dir / library
        if str(expected) not in output and str(expected.resolve()) not in output:
            unresolved.append(library)
    if unresolved:
        fail("o carregador não selecionou a mesma origem para todo o conjunto: " + ", ".join(unresolved))
    source_libraries: list[str] = []
    source_resolved = source_dir.resolve()
    for name, resolved_path in re.findall(r"^\s*(lib\S+)\s+=>\s+(/\S+)", output, re.MULTILINE):
        path = Path(resolved_path)
        try:
            same_source = path.parent.resolve() == source_resolved
        except OSError:
            same_source = False
        if same_source and re.fullmatch(r"lib[A-Za-z0-9_.+-]+\.so(?:\.[0-9]+)*", name):
            source_libraries.append(name)
    return {
        "loader": str(loader),
        "executable": str(executable),
        "source_directory": str(source_dir),
        "libraries": sorted(libraries),
        "source_libraries": sorted(set(source_libraries)),
    }


def command_repair_library(args: argparse.Namespace) -> None:
    launcher = Path(args.launcher).resolve()
    port_home = Path(args.port_home).resolve()
    doctor_home = Path(args.doctor_home).resolve()
    pm_home = Path(args.pm_home).resolve()
    library = Path(args.library).name
    if library != args.library or not re.fullmatch(r"lib[A-Za-z0-9_.+-]+\.so(?:\.[0-9]+)*", library):
        fail("nome de biblioteca recusado")
    if not launcher.is_file() or not port_home.is_dir() or not pm_home.is_dir():
        fail("launcher, port ou PortMaster não foi encontrado")

    bad_path = args.bad_path or ""
    if bad_path:
        allowed_path = re.fullmatch(r"/(?:usr/)?lib(?:/[A-Za-z0-9_.+-]+)*/" + re.escape(library), bad_path)
        if not allowed_path:
            fail("caminho absoluto da biblioteca foi recusado")

    patchelf = shutil.which("patchelf")
    absolute_candidates: list[Path] = []
    dependency_candidates: list[Path] = []
    needed_by_candidate: dict[Path, list[str]] = {}
    if bad_path or args.failed_executable:
        try:
            for candidate in port_home.rglob("*"):
                if not candidate.is_file() or candidate.is_symlink() or not inside(candidate, port_home):
                    continue
                try:
                    with candidate.open("rb") as handle:
                        if handle.read(4) != b"\x7fELF":
                            continue
                except OSError:
                    continue
                needed_names: list[str] = []
                if patchelf:
                    needed = subprocess.run(
                        [patchelf, "--print-needed", str(candidate)],
                        capture_output=True, text=True, errors="replace"
                    )
                    if needed.returncode == 0:
                        needed_names = needed.stdout.splitlines()
                elif shutil.which("readelf"):
                    needed = subprocess.run(
                        ["readelf", "-d", str(candidate)],
                        capture_output=True, text=True, errors="replace"
                    )
                    if needed.returncode == 0:
                        needed_names = re.findall(r"Shared library:\s*\[([^]]+)]", needed.stdout)
                if library in needed_names or (bad_path and bad_path in needed_names):
                    dependency_candidates.append(candidate)
                    needed_by_candidate[candidate] = needed_names
                if bad_path and bad_path in needed_names:
                    absolute_candidates.append(candidate)
        except OSError:
            pass
    if absolute_candidates and not patchelf:
        fail("a dependência é realmente absoluta, mas patchelf não está instalado")

    found = find_library(port_home, pm_home, doctor_home, library, args.runtime, args.architecture)
    if not found:
        runtime_images = []
        for master in portmaster_roots(pm_home):
            for root in (master / "libs", master / "runtimes"):
                if root.exists():
                    runtime_images.extend(str(path) for path in root.rglob("*.squashfs")
                                          if runtime_image_allowed(path, args.runtime))
        if runtime_images:
            print("Port Doctor: runtimes examinados: " + ", ".join(sorted(set(runtime_images))), file=sys.stderr)
        else:
            print("Port Doctor: nenhuma imagem dos runtimes declarados foi localizada nos caminhos do PortMaster.",
                  file=sys.stderr)
        fail(f"nenhuma cópia ELF {args.architecture} válida de {library} foi encontrada nos runtimes ou ports instalados")
    source, data = found
    destination_dir = port_home / "libs.portdoctor"
    destination_dir.mkdir(parents=True, exist_ok=True)
    destination = destination_dir / library

    bundle: dict[str, tuple[str, bytes]] = {library: (source, data)}
    source_path = Path(source)
    loader_validation = None
    if source_path.is_file() and not inside(source_path, port_home):
        failed_name = Path(args.failed_executable).name if args.failed_executable else ""
        failed_target = port_home / failed_name if failed_name else None
        executable = failed_target if failed_target and read_valid_elf(failed_target, args.architecture) else None
        if executable is None and dependency_candidates:
            executable = next(
                (candidate for candidate in dependency_candidates if candidate.name == failed_name),
                dependency_candidates[0],
            )
        if executable is not None:
            loader_validation = validate_local_bundle(
                source_path.parent,
                executable,
                args.architecture,
                {library},
                [source_path.parent, destination_dir, port_home / "lib", port_home / "libs"],
            )
            for companion in loader_validation.get("source_libraries", []):
                companion_path = source_path.parent / str(companion)
                companion_data = read_valid_elf(companion_path, args.architecture)
                if companion_data is None:
                    fail(f"o carregador selecionou uma dependência inválida na fonte: {companion}")
                bundle[str(companion)] = (str(companion_path), companion_data)
            loader_validation["libraries"] = sorted(bundle)
        else:
            required_ffmpeg = {library}
            for needed_names in needed_by_candidate.values():
                required_ffmpeg.update(name for name in needed_names if FFMPEG_SONAME.fullmatch(name))
            for companion in sorted(required_ffmpeg - {library}):
                companion_path = source_path.parent / companion
                companion_data = read_valid_elf(companion_path, args.architecture)
                if companion_data is None:
                    fail(f"a fonte local possui {library}, mas não contém o conjunto compatível completo: {companion}")
                bundle[companion] = (str(companion_path), companion_data)

    original_text = launcher.read_text(encoding="utf-8", errors="surrogateescape")
    needs_launcher_patch = "Port Doctor: local libraries" not in original_text
    failed_executable = Path(args.failed_executable).name if args.failed_executable else ""
    invocation_names = {candidate.name for candidate in dependency_candidates}
    if failed_executable and re.fullmatch(r"[A-Za-z0-9_.+ -]+", failed_executable):
        invocation_names.add(failed_executable)
    needs_immediate_patch = bool(invocation_names) and "Port Doctor: immediate local libraries" not in original_text
    same_bundle = all(
        (destination_dir / name).is_file() and (destination_dir / name).read_bytes() == contents
        for name, (_, contents) in bundle.items()
    )
    if same_bundle and not needs_launcher_patch and not needs_immediate_patch and not absolute_candidates:
        print(f"Port Doctor: conjunto local de {library} já está validado e ativo.")
        return

    folder, manifest = new_backup(doctor_home, port_home, launcher, "repair-library")
    for bundle_name, (_, bundle_data) in bundle.items():
        bundle_destination = destination_dir / bundle_name
        if bundle_destination.exists():
            old_backup = folder / "libraries-original" / bundle_name
            old_backup.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(bundle_destination, old_backup)
            manifest["replaced_files"].append({"path": str(bundle_destination), "backup": str(old_backup)})
        else:
            manifest["created_files"].append(str(bundle_destination))
        atomic_write(bundle_destination, bundle_data, 0o644)

    if needs_launcher_patch:
        export_line = library_export(port_home, original_text)
        lines = original_text.splitlines(keepends=True)
        insertion = 1 if lines and lines[0].startswith("#!") else 0
        for index, line in enumerate(lines):
            if line.strip().startswith("export LD_LIBRARY_PATH="):
                insertion = index + 1
        newline = "\r\n" if "\r\n" in original_text else "\n"
        lines.insert(insertion, export_line + newline)
        mode = launcher.stat().st_mode & 0o777
        atomic_write(launcher, "".join(lines).encode("utf-8", errors="surrogateescape"), mode)

    immediate_patched = False
    if needs_immediate_patch:
        current_text = launcher.read_text(encoding="utf-8", errors="surrogateescape")
        current_lines = current_text.splitlines(keepends=True)
        export_line = library_export(port_home, current_text).replace(
            "# Port Doctor: local libraries", "# Port Doctor: immediate local libraries"
        )
        for index, line in enumerate(current_lines):
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or re.search(r"\b(?:pkill|pgrep|kill)\b", stripped):
                continue
            if any(re.search(rf"(?:^|[/\"']){re.escape(name)}(?:[\"'\s]|$)", stripped)
                   for name in invocation_names):
                newline = "\r\n" if line.endswith("\r\n") else "\n"
                indent = line[:len(line) - len(line.lstrip())]
                current_lines.insert(index, indent + export_line + newline)
                immediate_patched = True
                break
        if immediate_patched:
            mode = launcher.stat().st_mode & 0o777
            atomic_write(launcher, "".join(current_lines).encode("utf-8", errors="surrogateescape"), mode)

    patched_binaries: list[str] = []
    if bad_path:
        for candidate in absolute_candidates:
            relative = candidate.relative_to(port_home)
            binary_backup = folder / "elf-original" / relative
            binary_backup.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(candidate, binary_backup)
            result = subprocess.run(
                [patchelf, "--replace-needed", bad_path, library, str(candidate)],
                capture_output=True, text=True, errors="replace"
            )
            verification = subprocess.run(
                [patchelf, "--print-needed", str(candidate)],
                capture_output=True, text=True, errors="replace"
            ) if result.returncode == 0 else None
            verified = verification is not None and verification.returncode == 0 \
                and bad_path not in verification.stdout.splitlines() \
                and library in verification.stdout.splitlines()
            if not verified:
                shutil.copy2(binary_backup, candidate)
                for entry in manifest["replaced_files"]:
                    replaced = Path(entry["path"])
                    backup = Path(entry["backup"])
                    if replaced != destination and backup.is_file():
                        shutil.copy2(backup, replaced)
                shutil.copy2(manifest["launcher_backup"], launcher)
                for created_text in manifest["created_files"]:
                    created = Path(created_text)
                    if inside(created, port_home) and created.is_file():
                        created.unlink()
                for entry in manifest["replaced_files"]:
                    replaced = Path(entry["path"])
                    backup = Path(entry["backup"])
                    if inside(replaced, port_home) and backup.is_file():
                        shutil.copy2(backup, replaced)
                manifest["restored"] = True
                manifest["restored_at"] = datetime.now(timezone.utc).isoformat()
                manifest["failure"] = (result.stderr if result.returncode != 0 else verification.stderr).strip()
                save_manifest(folder, manifest)
                fail(f"patchelf não conseguiu validar a correção de {relative}; todas as alterações foram desfeitas")
            manifest["replaced_files"].append({"path": str(candidate), "backup": str(binary_backup)})
            patched_binaries.append(str(relative))

    manifest["library"] = library
    manifest["source"] = source
    manifest["libraries"] = [
        {"name": name, "source": bundle_source}
        for name, (bundle_source, _) in sorted(bundle.items())
    ]
    manifest["loader_validation"] = loader_validation
    manifest["bad_path"] = bad_path or None
    manifest["patched_binaries"] = patched_binaries
    manifest["immediate_launcher_patch"] = immediate_patched
    save_manifest(folder, manifest)
    print(f"Port Doctor: {len(bundle)} biblioteca(s) {args.architecture} validada(s), copiada(s) e ativada(s) para este port.")
    for bundle_name, (bundle_source, _) in sorted(bundle.items()):
        print(f"Port Doctor: {bundle_name} <- {bundle_source}")
    print(f"Port Doctor: backup salvo em {folder}")
    if patched_binaries:
        print("Port Doctor: dependência absoluta corrigida em: " + ", ".join(patched_binaries))
    elif bad_path:
        print("Port Doctor: o caminho do erro era a biblioteca escolhida pelo Linux, não uma dependência absoluta.")
    if immediate_patched:
        print("Port Doctor: caminho local reforçado imediatamente antes de iniciar o executável do jogo.")
    if loader_validation:
        print("Port Doctor: conjunto aprovado pelo carregador dinâmico antes da alteração.")
    print("Port Doctor: alteração aplicada. Abra o jogo uma vez e use 'Verificar resultado do reparo'.")


def command_memory_zram(args: argparse.Namespace) -> None:
    launcher = Path(args.launcher).resolve()
    port_home = Path(args.port_home).resolve()
    doctor_home = Path(args.doctor_home).resolve()
    source_helper = doctor_home / "tools/zram-helper.sh"
    if not launcher.is_file() or not port_home.is_dir() or not source_helper.is_file():
        fail("launcher, pasta do port ou componente zram não foi encontrado")
    if not Path("/proc/swaps").is_file():
        fail("o kernel não oferece a interface necessária para memória swap")
    if not Path("/sys/block/zram0/disksize").exists() \
            and not Path("/sys/class/zram-control/hot_add").exists():
        fail("o kernel desta imagem não oferece zram configurável")

    destination_dir = port_home / "libs.portdoctor"
    destination_dir.mkdir(parents=True, exist_ok=True)
    destination_helper = destination_dir / "portdoctor-zram-helper.sh"
    marker = "# Port Doctor: memory zram"
    original_text = launcher.read_text(encoding="utf-8", errors="surrogateescape")
    helper_data = source_helper.read_bytes()
    already_patched = marker in original_text and destination_helper.is_file() \
        and destination_helper.read_bytes() == helper_data
    if already_patched:
        started = subprocess.run([str(destination_helper), "start"], capture_output=True, text=True)
        if started.returncode != 0:
            fail("o reparo já existe, mas zram não pôde ser ativado")
        print("Port Doctor: memória comprimida já está configurada e ativa para este port.")
        return

    folder, manifest = new_backup(doctor_home, port_home, launcher, "memory-zram")
    if destination_helper.exists():
        helper_backup = folder / "files-original/portdoctor-zram-helper.sh"
        helper_backup.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(destination_helper, helper_backup)
        manifest["replaced_files"].append({"path": str(destination_helper), "backup": str(helper_backup)})
    else:
        manifest["created_files"].append(str(destination_helper))
    atomic_write(destination_helper, helper_data, 0o755)

    escaped_helper = str(destination_helper).replace("'", "'\"'\"'")
    newline = "\r\n" if "\r\n" in original_text else "\n"
    block = (
        f"export MALLOC_ARENA_MAX=\"${{MALLOC_ARENA_MAX:-2}}\" {marker}{newline}"
        f"export MALLOC_TRIM_THRESHOLD_=\"${{MALLOC_TRIM_THRESHOLD_:-131072}}\" {marker}{newline}"
        f"'{escaped_helper}' start || true {marker}{newline}"
    )
    lines = original_text.splitlines(keepends=True)
    insertion = 1 if lines and lines[0].startswith("#!") else 0
    for index, line in enumerate(lines):
        if re.match(r"\s*(?:export\s+)?GAMEDIR=", line) or line.strip().startswith("export LD_LIBRARY_PATH="):
            insertion = index + 1
    lines.insert(insertion, block)
    mode = launcher.stat().st_mode & 0o777
    atomic_write(launcher, "".join(lines).encode("utf-8", errors="surrogateescape"), mode)

    started = subprocess.run([str(destination_helper), "start"], capture_output=True, text=True, errors="replace")
    active = False
    try:
        active = any(line.split() and line.split()[0] == "/dev/zram0"
                     for line in Path("/proc/swaps").read_text().splitlines()[1:])
    except OSError:
        pass
    if started.returncode != 0 or not active:
        shutil.copy2(manifest["launcher_backup"], launcher)
        if destination_helper in [Path(path) for path in manifest["created_files"]]:
            destination_helper.unlink(missing_ok=True)
        for entry in manifest["replaced_files"]:
            shutil.copy2(entry["backup"], entry["path"])
        manifest["restored"] = True
        manifest["restored_at"] = datetime.now(timezone.utc).isoformat()
        manifest["failure"] = (started.stderr or started.stdout or "zram não ficou ativo").strip()
        save_manifest(folder, manifest)
        fail("zram não pôde ser ativado; launcher e arquivos foram restaurados")

    manifest["zram_size_bytes"] = 805306368
    manifest["zram_device"] = "/dev/zram0"
    manifest["oom_before"] = oom_snapshot()
    save_manifest(folder, manifest)
    print("Port Doctor: 768 MB de memória comprimida zram ativados sem usar o cartão SD como swap.")
    print(f"Port Doctor: launcher ajustado e backup salvo em {folder}")
    print("Port Doctor: abra o jogo e use 'Verificar resultado do reparo'.")


def elf_architecture(path: Path) -> str | None:
    try:
        with path.open('rb') as stream:
            data = stream.read(20)
    except OSError:
        return None
    for architecture, (elf_class, machine) in MACHINES.items():
        valid, _ = elf_matches(data + bytes(max(0, MIN_LIBRARY_SIZE - len(data))), architecture)
        if valid and data[4] == elf_class:
            byte_order = data[5]
            detected = struct.unpack("<H" if byte_order == 1 else ">H", data[18:20])[0]
            if detected == machine:
                return architecture
    return None


def locate_executable(port_home: Path, value: str) -> Path | None:
    name = Path(value.strip()).name
    if not name or not re.fullmatch(r"[A-Za-z0-9_.+ -]+", name):
        return None
    direct = port_home / name
    if direct.is_file() and elf_architecture(direct):
        return direct
    try:
        for candidate in port_home.rglob(name):
            if candidate.is_file() and elf_architecture(candidate):
                return candidate
    except OSError:
        pass
    return None


def find_graphics_provider(architecture: str) -> Path | None:
    architecture_dirs = {
        "aarch64": ("aarch64-linux-gnu",),
        "armhf": ("arm-linux-gnueabihf",),
    }.get(architecture, ())
    candidates: list[Path] = []
    for directory in architecture_dirs:
        for prefix in (Path("/usr/lib"), Path("/lib")):
            root = prefix / directory
            if root.is_dir():
                candidates.extend(sorted(root.glob("libmali*.so*")))
    seen: set[str] = set()
    for candidate in candidates:
        try:
            resolved = candidate.resolve()
        except OSError:
            continue
        if str(resolved) in seen or not resolved.is_file() or elf_architecture(resolved) != architecture:
            continue
        seen.add(str(resolved))
        try:
            symbols = subprocess.run(
                ["readelf", "--wide", "-Ws", str(resolved)],
                capture_output=True, text=True, errors="replace", timeout=15,
            ).stdout
        except (OSError, subprocess.TimeoutExpired):
            continue
        if all(re.search(rf"\b{symbol}\b", symbols) for symbol in ("eglGetDisplay", "eglInitialize", "glGetString")):
            return resolved
    return None


def command_graphics_provider(args: argparse.Namespace) -> None:
    launcher = Path(args.launcher).resolve()
    port_home = Path(args.port_home).resolve()
    doctor_home = Path(args.doctor_home).resolve()
    architecture = str(args.architecture or "")
    if not launcher.is_file() or not port_home.is_dir() or not doctor_home.is_dir():
        fail("launcher, port ou Port Doctor não foi encontrado")
    provider = find_graphics_provider(architecture)
    if provider is None:
        fail(f"nenhum provedor EGL/GLES Mali {architecture or 'compatível'} foi validado")
    provider_text = str(provider)
    if any(character in provider_text for character in ('\n', '\r', '"', '`', '$')):
        fail("o caminho do provedor gráfico não pode ser inserido com segurança no launcher")
    block = f'''# Port Doctor: graphics provider start
export SDL_VIDEO_EGL_DRIVER="{provider_text}"
export SDL_VIDEO_GL_DRIVER="{provider_text}"
# Port Doctor: graphics provider end'''
    insert_or_replace_block(
        launcher,
        block,
        "Port Doctor: graphics provider start",
        "Port Doctor: graphics provider end",
        "graphics-provider",
        doctor_home,
        port_home,
    )
    print(f"Port Doctor: provedor EGL/GLES validado e configurado: {provider}")


def loader_preflight(executable: Path, port_home: Path, architecture: str) -> tuple[bool, str]:
    loaders = {
        "aarch64": Path("/lib/ld-linux-aarch64.so.1"),
        "armhf": Path("/lib/ld-linux-armhf.so.3"),
        "x86_64": Path("/lib64/ld-linux-x86-64.so.2"),
    }
    loader = loaders.get(architecture)
    if loader is None or not loader.is_file():
        return False, f"carregador {architecture} ausente"
    environment = os.environ.copy()
    paths = [port_home / "libs.portdoctor", port_home / "lib", port_home / "libs"]
    previous = environment.get("LD_LIBRARY_PATH", "")
    environment["LD_LIBRARY_PATH"] = ":".join(str(path) for path in paths if path.is_dir()) \
        + ((":" + previous) if previous else "")
    result = subprocess.run(
        [str(loader), "--list", str(executable)],
        capture_output=True, text=True, errors="replace", env=environment,
    )
    output = result.stdout + result.stderr
    clean = result.returncode == 0 and not re.search(r"\bnot found\b|file too short|version .+ not found", output, re.I)
    return clean, output


def command_auto_repair(args: argparse.Namespace) -> None:
    launcher = Path(args.launcher).resolve()
    port_home = Path(args.port_home).resolve()
    doctor_home = Path(args.doctor_home).resolve()
    pm_home = Path(args.pm_home).resolve()
    if not launcher.is_file() or not port_home.is_dir() or not doctor_home.is_dir() or not pm_home.is_dir():
        fail("launcher, port, Port Doctor ou PortMaster não foi encontrado")

    try:
        launcher_prefix = launcher.read_bytes()[:512]
    except OSError:
        launcher_prefix = b""
    if not launcher_prefix.startswith(b"#!") and b"#!/" in launcher_prefix:
        print("Port Doctor: plano automático: colocar o interpretador na primeira linha do launcher.")
        command_repair_launcher_header(argparse.Namespace(
            launcher=str(launcher), port_home=str(port_home), doctor_home=str(doctor_home)
        ))
        return

    log_path = newest_log(port_home, launcher)
    log_text = ""
    if log_path:
        try:
            log_text = log_path.read_bytes()[-1024 * 1024:].decode("utf-8", errors="replace")
        except OSError:
            pass

    library_matches = list(re.finditer(
        r"(?m)^([^:\r\n]+):\s*error while loading shared libraries:\s*([^:\r\n]+):\s*"
        r"(?:file too short|cannot open shared object file[^\r\n]*)",
        log_text,
    ))
    def apply_library_plan(executable_text: str, bad_value: str,
                           executable: Path | None = None, architecture: str | None = None) -> None:
        library = Path(bad_value).name
        if PROTECTED_LIBRARY.fullmatch(library):
            fail(f"{library} pertence ao núcleo ou ao driver do sistema e não será transplantada automaticamente")
        executable = executable or locate_executable(port_home, executable_text)
        architecture = architecture or (elf_architecture(executable) if executable else None)
        if architecture is None:
            architecture = next((item for item in args.architecture if item in MACHINES), None)
        if architecture is None:
            fail("não foi possível identificar a arquitetura do executável que falhou")
        repair_args = argparse.Namespace(
            launcher=str(launcher),
            port_home=str(port_home),
            doctor_home=str(doctor_home),
            pm_home=str(pm_home),
            library=library,
            architecture=architecture,
            runtime=args.runtime,
            bad_path=bad_value if bad_value.startswith("/") else None,
            failed_executable=executable_text,
        )
        print(f"Port Doctor: plano automático: reparar {library} e fechar suas dependências transitivas.")
        command_repair_library(repair_args)
        if executable:
            clean, output = loader_preflight(executable, port_home, architecture)
            if not clean:
                last_error = next(
                    (line.strip() for line in reversed(output.splitlines())
                     if re.search(r"not found|file too short|version .+ not found", line, re.I)),
                    "o carregador ainda encontrou uma incompatibilidade",
                )
                fail("o reparo foi salvo com backup, mas o pré-teste ainda falhou: " + last_error)
            print("Port Doctor: pré-teste completo aprovado; nenhuma dependência do carregador ficou pendente.")
    if library_matches:
        match = library_matches[-1]
        apply_library_plan(match.group(1).strip(), match.group(2).strip())
        return

    try:
        launcher_text = launcher.read_text(encoding="utf-8", errors="replace")
    except OSError:
        launcher_text = ""
    executable_candidates: list[Path] = []
    try:
        for candidate in port_home.rglob("*"):
            if not candidate.is_file() or candidate.is_symlink() or ".so" in candidate.name:
                continue
            architecture = elf_architecture(candidate)
            if architecture and os.access(candidate, os.X_OK):
                executable_candidates.append(candidate)
    except OSError:
        pass
    executable_candidates.sort(key=lambda path: (path.name not in launcher_text, len(path.parts), path.name))
    for executable in executable_candidates[:32]:
        architecture = elf_architecture(executable)
        if not architecture:
            continue
        clean, output = loader_preflight(executable, port_home, architecture)
        if clean:
            continue
        missing = re.search(r"^\s*(lib\S+)\s+=>\s+not found\s*$", output, re.MULTILINE)
        truncated = re.search(r"(/\S+):\s*file too short", output)
        versioned = re.search(r"(/\S+):\s*version .+ not found", output)
        bad_value = (missing.group(1) if missing else truncated.group(1) if truncated else
                     versioned.group(1) if versioned else "")
        if bad_value:
            print(f"Port Doctor: pré-análise encontrou a falha em {executable.name} sem depender do log do jogo.")
            apply_library_plan(executable.name, bad_value, executable, architecture)
            return

    lowered = log_text.lower()
    common = argparse.Namespace(
        launcher=str(launcher), port_home=str(port_home), doctor_home=str(doctor_home)
    )
    # A lighter Unity profile did NOT resolve the reported Hollow Knight crash.
    # Do not offer it as an automatic fix without a validated cause/recipe.
    if "game.droid is compressed" in lowered or "bitstream/page/packet is not vorbis data" in lowered:
        print("Port Doctor: plano automático: reconstruir o pacote GMLoader para acesso direto aos recursos.")
        command_repack_game_archive(common)
        return
    if "unable to find game!!" in lowered or ("game.droid" in lowered and "failed to load file" in lowered):
        candidates = game_data_candidates(port_home)
        if not candidates:
            fail("game.droid não está no pacote; forneça sua cópia legítima dentro da pasta do port")
        print("Port Doctor: plano automático: instalar a cópia local validada de game.droid.")
        command_install_game_data(argparse.Namespace(**vars(common), source=str(candidates[0])))
        return
    if "invalid or corrupt jarfile" in lowered:
        print("Port Doctor: plano automático: reconstruir o JAR com a base íntegra e os recursos preservados.")
        command_repair_java_archive(argparse.Namespace(**vars(common), candidate=None))
        return
    if re.search(r"-Dsts\.width=\s+-Dsts\.height=", log_text):
        print("Port Doctor: plano automático: corrigir a expansão do tamanho de tela no launcher.")
        command_repair_shell_defaults(common)
        return
    runtime_match = (
        re.search(r"Unknown runtime\s+([A-Za-z0-9._-]+\.squashfs)", log_text, re.I)
        or re.search(r"Runtime\s+([A-Za-z0-9._-]+\.squashfs)\s+(?:não|nao) encontrado", log_text, re.I)
    )
    if runtime_match:
        runtime = runtime_match.group(1)
        if find_local_runtime(port_home, runtime) is None:
            fail(f"o launcher exige {runtime}, mas nenhuma cópia local válida foi encontrada")
        print(f"Port Doctor: plano automático: permitir a cópia local validada de {runtime}.")
        command_repair_local_runtime(argparse.Namespace(**vars(common), runtime=runtime))
        return
    if "failed to create sdl window" in lowered and (
        "can't load egl/gl library" in lowered or "egl not initialized" in lowered
    ):
        architecture = next((item for item in args.architecture if item in ("aarch64", "armhf")), None)
        if architecture is None:
            architecture = next(
                (elf_architecture(path) for path in port_home.rglob("*")
                 if path.is_file() and os.access(path, os.X_OK) and elf_architecture(path) in ("aarch64", "armhf")),
                None,
            )
        if architecture is None:
            fail("a arquitetura do executável gráfico não foi identificada")
        print("Port Doctor: plano automático: configurar o provedor EGL/GLES Mali validado.")
        command_graphics_provider(argparse.Namespace(**vars(common), architecture=architecture))
        return
    reported_memory = [int(value) for value in re.findall(r"Total memory used\s*=\s*(\d+)", log_text)]
    if (reported_memory and max(reported_memory) > 734003200) or "out of memory" in lowered or "oom-killer" in lowered:
        print("Port Doctor: plano automático: ativar memória comprimida porque o jogo excede a RAM disponível.")
        command_memory_zram(common)
        return
    if "device or resource busy" in lowered and ("openaudiodevice" in lowered or "audio" in lowered):
        print("Port Doctor: plano automático: corrigir acesso concorrente ao dispositivo de áudio.")
        command_audio_busy(common)
        return
    if "failed to create pipewire event context" in lowered or ("pw.conf" in lowered and "client.conf" in lowered):
        print("Port Doctor: plano automático: usar ALSA porque PipeWire não está disponível.")
        command_audio_alsa(common)
        return

    fail("nenhuma falha com correção automática segura foi reconhecida no log atual")


def command_verify(args: argparse.Namespace) -> None:
    launcher = Path(args.launcher).resolve()
    port_home = Path(args.port_home).resolve()
    doctor_home = Path(args.doctor_home).resolve()
    backup_root = doctor_home / "conf" / "backups" / safe_slug(port_home.name)
    manifests = sorted(backup_root.glob("*/manifest.json"), reverse=True) if backup_root.exists() else []
    for manifest_path in manifests:
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if manifest.get("restored") or Path(manifest.get("launcher_path", "")).resolve() != launcher:
            continue
        current = log_snapshot(port_home, launcher)
        previous = manifest.get("log_before")
        if current is None:
            fail("nenhum log do port foi encontrado; abra o jogo uma vez e tente novamente")
        action = manifest.get("action", "")
        same_content = previous and current.get("sha256") == previous.get("sha256")
        same_timestamp = previous and current.get("mtime_ns") == previous.get("mtime_ns")
        if same_content and same_timestamp:
            fail("o log ainda não mudou; abra o jogo depois do reparo e volte para verificar")
        repair_ns = int(datetime.fromisoformat(manifest['created_at']).timestamp() * 1e9)
        if int(current.get('mtime_ns', 0)) <= repair_ns:
            fail("o log é anterior ao reparo; teste o jogo novamente")
        try:
            data = Path(current["path"]).read_bytes()[-1024 * 1024:].decode("utf-8", errors="replace")
        except OSError:
            fail("não foi possível ler o novo log")
        failures: list[str] = []
        if re.search(r'Segmentation fault|Bus error|SIGBUS|SIGSEGV|SIGILL|SIGABRT|Illegal instruction|'
                     r'FATAL UNHANDLED EXCEPTION|error while loading shared libraries|'
                     r'symbol lookup error|Invalid or corrupt jarfile|OpenAudioDevice failed|'
                     r'Engine initialization failed|Failed to create SDL Window', data, re.I):
            failures.append('o novo log ainda contém uma falha impeditiva')
        crashes = new_native_crashes(port_home, manifest.get('crashes_before', {}), repair_ns)
        if crashes:
            failures.append('novo registro de falha nativa: ' + crashes[0])
        if action == "repair-library":
            library = re.escape(str(manifest.get("library", "")))
            if library and re.search(rf"{library}.*(?:file too short|cannot open shared object file)", data, re.I):
                failures.append("a falha da biblioteca reapareceu")
            bad_path = manifest.get("bad_path")
            if bad_path and bad_path in data and "error while loading shared libraries" in data:
                failures.append("o caminho absoluto ainda aparece no carregador")
        elif action in {"audio-alsa", "audio-busy"}:
            patterns = (
                r"OpenAudioDevice failed", r"Device or resource busy",
                r"Engine initialization failed", r"Failed to create PipeWire",
            )
            if any(re.search(pattern, data, re.I) for pattern in patterns):
                failures.append("a falha de inicialização de áudio reapareceu")
        elif action == "memory-zram":
            before_oom = manifest.get("oom_before", {})
            after_oom = oom_snapshot()
            manifest["oom_after"] = after_oom
            if int(after_oom.get("count", 0)) > int(before_oom.get("count", 0)):
                failures.append("o kernel voltou a encerrar um processo por falta de memória")
        elif action == "install-game-data":
            patterns = (r"Unable to find game!!", r"FAILED to load File .+game\.droid")
            if any(re.search(pattern, data, re.I) for pattern in patterns):
                failures.append("o runner ainda não encontrou game.droid")
        elif action == "repack-game-archive":
            patterns = (r"game\.droid is compressed", r"Bitstream/page/packet is not Vorbis data")
            if any(re.search(pattern, data, re.I) for pattern in patterns):
                failures.append("o runner ainda relata recursos comprimidos ou ilegíveis")
        elif action == "repair-local-runtime":
            runtime = re.escape(str(manifest.get("runtime", "")))
            patterns = (
                rf"Unknown runtime\s+{runtime}",
                rf"Runtime\s+{runtime}\s+(?:não|nao) encontrado",
            )
            if runtime and any(re.search(pattern, data, re.I) for pattern in patterns):
                failures.append("o launcher ainda recusou o runtime local")
        elif action == "graphics-provider":
            patterns = (r"Failed to create SDL Window", r"Can't load EGL/GL library", r"EGL not initialized")
            if any(re.search(pattern, data, re.I) for pattern in patterns):
                failures.append("o SDL ainda não conseguiu inicializar EGL/GLES")
        elif action == "repair-java-archive":
            if re.search(r"Invalid or corrupt jarfile", data, re.I):
                failures.append("o Java ainda recusou o arquivo JAR")
        manifest["log_after"] = current
        manifest["verified_at"] = datetime.now(timezone.utc).isoformat()
        manifest["verification"] = "failed" if failures else "awaiting_game_test"
        save_manifest(manifest_path.parent, manifest)
        if failures:
            fail("; ".join(failures) + ". O reparo não resolveu este port e não será marcado como concluído")
        print("Port Doctor: o erro tratado não reapareceu no novo log.")
        print("Port Doctor: resultado INCONCLUSIVO sobre o funcionamento do jogo. Confirme imagem, controles e áudio no aparelho; ausência de erro no log não comprova sucesso.")
        return
    fail("nenhum reparo pendente foi encontrado para verificar")


def command_inspect_native(args: argparse.Namespace) -> None:
    port_home=Path(args.port_home).resolve()
    print('DIAGNÓSTICO NATIVO — somente leitura')
    snapshots=crash_snapshot(port_home)
    if not snapshots:
        fail('nenhum registro tombstone foi encontrado; o log pode exigir investigação do autor do port')
    for path, _ in sorted(snapshots.items(), key=lambda pair: pair[1], reverse=True)[:3]:
        print('\nRegistro: ' + path)
        with Path(path).open('rb') as stream:
            text=stream.read(32768).decode('utf-8', errors='replace')
        for line in text.splitlines():
            if re.match(r"Version |Timestamp:|signal |pid:|ABI:|Failed to unwind|\s+#\d+ pc", line):
                print(line)
        if 'BUS_ADRALN' in text:
            print('O processo tentou acessar ou executar um endereço desalinhado. Isso não identifica por si só a causa; pode envolver dados, ponte nativa ou executável.')
    print('\nCompare os horários com sua última tentativa. Registros antigos podem vir no pacote.')
    print('Não há correção universal segura para SIGBUS/SIGSEGV. Bibliotecas só serão alteradas se uma dependência incompatível ou ausente for comprovada.')


def command_restore(args: argparse.Namespace) -> None:
    launcher = Path(args.launcher).resolve()
    port_home = Path(args.port_home).resolve()
    doctor_home = Path(args.doctor_home).resolve()
    backup_root = doctor_home / "conf" / "backups" / safe_slug(port_home.name)
    manifests = sorted(backup_root.glob("*/manifest.json"), reverse=True) if backup_root.exists() else []
    for manifest_path in manifests:
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if manifest.get("restored") or Path(manifest.get("launcher_path", "")).resolve() != launcher:
            continue
        launcher_backup = Path(manifest.get("launcher_backup", ""))
        if not launcher_backup.is_file():
            continue
        shutil.copy2(launcher_backup, launcher)
        for path_text in manifest.get("created_files", []):
            path = Path(path_text)
            if inside(path, port_home) and path.is_file():
                path.unlink()
        for entry in manifest.get("replaced_files", []):
            path = Path(entry.get("path", ""))
            backup = Path(entry.get("backup", ""))
            if inside(path, port_home) and backup.is_file():
                shutil.copy2(backup, path)
        manifest["restored"] = True
        manifest["restored_at"] = datetime.now(timezone.utc).isoformat()
        save_manifest(manifest_path.parent, manifest)
        print(f"Port Doctor: reparo {manifest.get('action', '')} desfeito com sucesso.")
        return
    fail("nenhum backup pendente foi encontrado para este port")


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    sub = result.add_subparsers(dest="command", required=True)

    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--launcher", required=True)
    common.add_argument("--port-home", required=True)
    common.add_argument("--doctor-home", required=True)

    audio = sub.add_parser("audio-alsa", parents=[common])
    audio.set_defaults(handler=command_audio_alsa)

    launcher_header = sub.add_parser("repair-launcher-header", parents=[common])
    launcher_header.set_defaults(handler=command_repair_launcher_header)

    shell_defaults = sub.add_parser("repair-shell-defaults", parents=[common])
    shell_defaults.set_defaults(handler=command_repair_shell_defaults)

    local_runtime = sub.add_parser("repair-local-runtime", parents=[common])
    local_runtime.add_argument("--runtime", required=True)
    local_runtime.set_defaults(handler=command_repair_local_runtime)

    graphics = sub.add_parser("graphics-provider", parents=[common])
    graphics.add_argument("--architecture", choices=("aarch64", "armhf"), required=True)
    graphics.set_defaults(handler=command_graphics_provider)

    busy = sub.add_parser("audio-busy", parents=[common])
    busy.set_defaults(handler=command_audio_busy)

    game_data = sub.add_parser("install-game-data", parents=[common])
    game_data.add_argument("--source", required=True)
    game_data.set_defaults(handler=command_install_game_data)

    repack = sub.add_parser("repack-game-archive", parents=[common])
    repack.set_defaults(handler=command_repack_game_archive)

    java_archive = sub.add_parser("repair-java-archive", parents=[common])
    java_archive.add_argument("--candidate")
    java_archive.set_defaults(handler=command_repair_java_archive)

    library = sub.add_parser("repair-library", parents=[common])
    library.add_argument("--pm-home", required=True)
    library.add_argument("--library", required=True)
    library.add_argument("--architecture", choices=sorted(MACHINES), required=True)
    library.add_argument("--runtime", action="append", default=[])
    library.add_argument("--bad-path")
    library.add_argument("--failed-executable")
    library.set_defaults(handler=command_repair_library)

    automatic = sub.add_parser("auto-repair", parents=[common])
    automatic.add_argument("--pm-home", required=True)
    automatic.add_argument("--architecture", action="append", choices=sorted(MACHINES), default=[])
    automatic.add_argument("--runtime", action="append", default=[])
    automatic.set_defaults(handler=command_auto_repair)

    memory = sub.add_parser("memory-zram", parents=[common])
    memory.set_defaults(handler=command_memory_zram)

    verify = sub.add_parser("verify", parents=[common])
    verify.set_defaults(handler=command_verify)

    native = sub.add_parser('inspect-native', parents=[common])
    native.set_defaults(handler=command_inspect_native)

    restore = sub.add_parser("restore", parents=[common])
    restore.set_defaults(handler=command_restore)
    return result


def main() -> None:
    args = parser().parse_args()
    args.handler(args)


if __name__ == "__main__":
    main()
