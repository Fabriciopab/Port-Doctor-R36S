#!/usr/bin/env python3
"""Instala ports de um compartilhamento local já montado pelo Port Doctor."""

import hashlib
import json
import os
import shutil
import stat
import sys
import tempfile
from pathlib import Path


MOUNT_ROOT = Path(os.environ.get("PORTDOCTOR_NETWORK_MOUNT", "/mnt/r36s-jogos"))
REPORT_DIR = Path(os.environ.get("PORTDOCTOR_HOME", "/roms/ports/portdoctor")) / "conf/reports"
MAX_FILES = 20000
MAX_DEPTH = 12


def destination_roots():
    configured = os.environ.get("PORTDOCTOR_PORTS_ROOTS")
    if configured:
        return tuple(Path(item) for item in configured.split(os.pathsep) if item)
    return (Path("/roms/ports"), Path("/roms2/ports"))


def result(ok, kind, title, text, **extra):
    print(json.dumps({"ok": ok, "kind": kind, "title": title, "text": text, **extra}, ensure_ascii=False))


def fail(title, text, code=1):
    result(False, "error", title, text)
    raise SystemExit(code)


def contained(path, root):
    try:
        path.resolve(strict=False).relative_to(root.resolve(strict=False))
        return True
    except ValueError:
        return False


def source_root():
    for candidate in (MOUNT_ROOT / "ports", MOUNT_ROOT / "R36S-Ports", MOUNT_ROOT / "r36s-ports"):
        if candidate.is_dir() and not candidate.is_symlink():
            return candidate
    fail("Pasta de ports ausente", "Crie no compartilhamento do Windows uma pasta chamada R36S-Ports ou ports.")


def inspect_package(path):
    if not path.is_dir() or path.is_symlink() or not contained(path, source_root()):
        return None
    launchers = sorted(p for p in path.iterdir() if p.is_file() and not p.is_symlink() and p.suffix.lower() == ".sh")
    if not launchers:
        return None
    count = 0
    size = 0
    for base, dirs, files in os.walk(path, followlinks=False):
        relative_depth = len(Path(base).relative_to(path).parts)
        if relative_depth > MAX_DEPTH:
            raise ValueError(f"estrutura profunda demais em {path.name}")
        for directory in dirs:
            if (Path(base) / directory).is_symlink():
                raise ValueError(f"link simbólico recusado em {path.name}")
        for name in files:
            item = Path(base) / name
            if item.is_symlink():
                raise ValueError(f"link simbólico recusado em {path.name}")
            count += 1
            if count > MAX_FILES:
                raise ValueError(f"arquivos demais em {path.name}")
            size += item.stat().st_size
    return {"id": path.name, "name": path.name, "launchers": [p.name for p in launchers], "files": count, "size": size}


def list_packages():
    root = source_root()
    packages = []
    warnings = []
    for path in sorted(root.iterdir(), key=lambda p: p.name.casefold()):
        if path.name.startswith("."):
            continue
        try:
            package = inspect_package(path)
            if package:
                packages.append(package)
        except (OSError, ValueError) as exc:
            warnings.append(str(exc))
    destinations = []
    for root_path in destination_roots():
        if root_path.is_dir() and not root_path.is_symlink():
            usage = shutil.disk_usage(root_path)
            destinations.append({"path": str(root_path), "free": usage.free})
    text = f"{len(packages)} pacote(s) válido(s) encontrado(s)."
    if warnings:
        text += f" {len(warnings)} item(ns) recusado(s)."
    result(True, "packages", "Ports disponíveis no Windows", text, packages=packages, destinations=destinations, warnings=warnings[:20])


def safe_id(value):
    if not value or value in (".", "..") or "/" in value or "\\" in value or "\x00" in value:
        fail("Pacote inválido", "O nome recebido não é seguro.")
    return value


def plan(package_id, destination):
    package_id = safe_id(package_id)
    destination_root = Path(destination)
    allowed = destination_roots()
    if destination_root not in allowed or not destination_root.is_dir() or destination_root.is_symlink():
        fail("Destino indisponível", "O cartão escolhido não possui uma pasta ports válida.")
    source = source_root() / package_id
    package = inspect_package(source)
    if not package:
        fail("Pacote incompleto", "A pasta precisa conter pelo menos um launcher .sh na raiz.")
    free = shutil.disk_usage(destination_root).free
    required = package["size"] + max(16 * 1024 * 1024, package["size"] // 20)
    if free < required:
        fail("Espaço insuficiente", f"Necessário com margem: {required // (1024*1024)} MB; livre: {free // (1024*1024)} MB.")
    conflicts = []
    for child in source.iterdir():
        if (destination_root / child.name).exists():
            conflicts.append(child.name)
    if conflicts:
        fail("Port já existente", "Para proteger jogos e saves, a instalação não sobrescreve: " + ", ".join(conflicts[:8]))
    token_data = f"{source.resolve()}\n{destination_root.resolve()}\n{package['size']}\n{package['files']}"
    token = hashlib.sha256(token_data.encode()).hexdigest()
    result(True, "plan", "Instalar " + package["name"],
           f"Origem: Windows/{source.name}\nDestino: {destination_root}\nArquivos: {package['files']}\nTamanho: {package['size'] // (1024*1024)} MB\n\nNada existente será sobrescrito.",
           package=package_id, destination=str(destination_root), token=token)


def copy_file(source, destination):
    source = Path(source)
    destination = Path(destination)
    with source.open("rb") as src, destination.open("xb") as dst:
        shutil.copyfileobj(src, dst, 1024 * 1024)
        dst.flush()
        os.fsync(dst.fileno())
    shutil.copystat(source, destination, follow_symlinks=False)


def execute(package_id, destination, expected_token):
    package_id = safe_id(package_id)
    source = source_root() / package_id
    destination_root = Path(destination)
    package = inspect_package(source)
    if not package:
        fail("Pacote alterado", "O pacote deixou de ser válido. Atualize a lista e tente novamente.")
    token_data = f"{source.resolve()}\n{destination_root.resolve()}\n{package['size']}\n{package['files']}"
    if not expected_token or hashlib.sha256(token_data.encode()).hexdigest() != expected_token:
        fail("Plano expirado", "Os arquivos mudaram desde a confirmação. Revise a instalação novamente.")
    if destination_root not in destination_roots() or not destination_root.is_dir():
        fail("Destino inválido", "O cartão escolhido não está disponível.")
    for child in source.iterdir():
        if (destination_root / child.name).exists():
            fail("Conflito detectado", f"{child.name} passou a existir. Nenhum arquivo foi sobrescrito.")
    staging = Path(tempfile.mkdtemp(prefix=".portdoctor-install-", dir=destination_root))
    installed = []
    try:
        for child in source.iterdir():
            target = staging / child.name
            if child.is_symlink():
                raise ValueError("links simbólicos não são permitidos")
            if child.is_dir():
                shutil.copytree(child, target, symlinks=False, copy_function=copy_file)
            elif child.is_file():
                copy_file(child, target)
        staged = inspect_staging(staging)
        if staged != (package["files"], package["size"]):
            raise OSError("a conferência da cópia não corresponde à origem")
        for launcher in staging.glob("*.sh"):
            launcher.chmod(launcher.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
        for child in list(staging.iterdir()):
            final = destination_root / child.name
            os.rename(child, final)
            installed.append(final)
        staging.rmdir()
    except Exception as exc:
        for path in reversed(installed):
            try:
                if path.is_dir(): shutil.rmtree(path)
                else: path.unlink()
            except OSError:
                pass
        shutil.rmtree(staging, ignore_errors=True)
        fail("Instalação cancelada", f"A cópia não foi concluída: {exc}. Itens parciais foram removidos.")
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    report = REPORT_DIR / "ultima-instalacao-port-hub.txt"
    report.write_text(f"Pacote: {package_id}\nOrigem: {source}\nDestino: {destination_root}\nArquivos: {package['files']}\nBytes: {package['size']}\n", encoding="utf-8")
    result(True, "installed", "Port instalado", f"{package_id} foi copiado e conferido em {destination_root}.\n\nExecute Reconhecer capas dos ports e depois teste o jogo.")


def inspect_staging(path):
    count = size = 0
    for base, _, files in os.walk(path):
        for name in files:
            count += 1
            size += (Path(base) / name).stat().st_size
    return count, size


def main():
    if len(sys.argv) < 2:
        fail("Uso inválido", "Comando ausente.", 2)
    command = sys.argv[1]
    if command == "list":
        list_packages()
    elif command == "plan" and len(sys.argv) == 4:
        plan(sys.argv[2], sys.argv[3])
    elif command == "execute" and len(sys.argv) == 5:
        execute(sys.argv[2], sys.argv[3], sys.argv[4])
    else:
        fail("Uso inválido", "Use list, plan ou execute.", 2)


if __name__ == "__main__":
    main()
