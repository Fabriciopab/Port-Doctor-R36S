#!/usr/bin/env python3
"""Allowlisted, reversible Hollow Knight EGL-surface repair. Never patches a game ELF."""
from __future__ import annotations
import argparse
import hashlib
import os
from pathlib import Path
import platform
import re
import subprocess
import tempfile

MODULE_SHA256 = '7468735542e37a02339326a6e7a43e65b752bd04863df910c13b4d0d4b9be33d'
KNOWN = {
    'unityloader': '9c52d486b975e62ccab12ee480ffda37b92adcaa9e8d6ec9ced67f2916c3db5e',
    'gamedata/lib/arm64-v8a/libunity.so': '19083b858d9dc6ae8dc323a28eec7de29dc6177343170e0d7facc890103406a7',
    'gamedata/lib/arm64-v8a/libil2cpp.so': '61232637376119a733ad9d078f007154b236d21545c70e264a90027c6d0c3f8f',
}
DESTINATION = 'portdoctor-egl/unity-egl-rebind.so'
MARKER = '# Port Doctor: Unity EGL surface repair v1'
END_MARKER = '# Port Doctor: end Unity EGL surface repair'
LAUNCH = re.compile(r'(?m)^(?P<indent>[ \t]*)(?P<command>"\$GAMEDIR/unityloader"|\./unityloader)[ \t]+(?P<config>hk\.toml|"\$GAMEDIR/hk\.toml")(?P<tail>[ \t]*(?:&[ \t]*)?)$')

def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024*1024), b''):
            value.update(block)
    return value.hexdigest()

def local_file(root: Path, relative: str) -> Path:
    path = root / relative
    for component in (path, *path.parents):
        if component == root:
            break
        if component.is_symlink():
            raise ValueError('atalhos simbólicos não são aceitos neste reparo')
    if not path.resolve().is_relative_to(root.resolve()):
        raise ValueError('caminho fora do port')
    return path

def platform_reason() -> str:
    if platform.system() != 'Linux' or platform.machine() not in ('aarch64', 'arm64'):
        return 'reparo disponível somente em Linux AArch64'
    try:
        compatible = Path('/proc/device-tree/compatible').read_bytes().lower()
        if b'rockchip,rk3326' not in compatible:
            return 'reparo validado somente para RK3326/Mali-G31'
        libc = os.confstr('CS_GNU_LIBC_VERSION') or ''
        version = tuple(int(x) for x in libc.split()[-1].split('.')[:2])
        if not libc.startswith('glibc ') or version < (2, 17):
            return 'glibc compatível não identificada'
        if not Path('/usr/lib/aarch64-linux-gnu/libmali-bifrost-g31-rxp0-gbm.so').is_file():
            return 'provedor Mali-G31 GBM validado não encontrado'
    except (OSError, ValueError, IndexError):
        return 'não foi possível confirmar o ambiente gráfico'
    return ''

def check(port: Path, launcher: Path | None = None) -> tuple[str, str]:
    reason = platform_reason()
    if reason:
        return 'unsupported', reason
    try:
        for name, expected in KNOWN.items():
            path = local_file(port, name)
            if not path.is_file() or path.stat().st_size > 64*1024*1024 or digest(path) != expected:
                return 'unsupported', 'carregador ou motor não corresponde ao build validado'
        if launcher is not None:
            if launcher.is_symlink() or not launcher.is_file() or launcher.stat().st_size > 128*1024:
                return 'unsupported', 'launcher inválido'
            text = launcher.read_text(encoding='utf-8')
            if MARKER in text:
                module = local_file(port, DESTINATION)
                if END_MARKER in text and module.is_file() and digest(module) == MODULE_SHA256:
                    return 'applied', 'reparo instalado; funcionamento requer teste no aparelho'
                return 'unsupported', 'reparo incompleto; desfaça o último reparo antes de reaplicar'
            if len(LAUNCH.findall(text)) != 1 or 'LD_AUDIT' in text:
                return 'unsupported', 'formato do launcher não reconhecido para aplicação segura'
        return 'available', 'superfície EGL obsoleta: receita compatível com este build'
    except (OSError, UnicodeError, ValueError) as error:
        return 'unsupported', str(error)

def patch_launcher(text: str) -> str:
    text = text.replace('\r\n', '\n')
    if MARKER in text or 'LD_AUDIT' in text or len(LAUNCH.findall(text)) != 1:
        raise ValueError('launcher não reconhecido ou já modificado')
    checks = '\n'.join(f"        '{sha}  {name}' \\" for name, sha in {**KNOWN, DESTINATION: MODULE_SHA256}.items())
    block = (MARKER + '\n'
        'if ! (cd "$GAMEDIR" && printf "%s\\n" \\\n' + checks + '\n'
        '        | sha256sum --check --status); then\n'
        '    echo "Port Doctor: build ou módulo EGL mudou; desfaça o reparo e analise novamente." >&2\n'
        '    exit 1\n'
        'fi\n' + END_MARKER + '\n')
    return LAUNCH.sub(lambda m: block + m['indent'] + 'env LD_AUDIT="$GAMEDIR/' + DESTINATION
                     + '" ' + m['command'] + ' ' + m['config'] + m['tail'], text)

def atomic_replace(path: Path, data: bytes, mode: int):
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(prefix='.portdoctor-egl-', dir=path.parent, delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(data); stream.flush(); os.fsync(stream.fileno())
        temporary.chmod(mode)
        os.replace(temporary, path)
    finally:
        if temporary and temporary.exists():
            temporary.unlink()

def running(port: Path) -> bool:
    executable = (port / 'unityloader').resolve()
    for proc in Path('/proc').glob('[0-9]*/exe'):
        try:
            if proc.resolve() == executable:
                return True
        except OSError:
            continue
    return False

def apply(args):
    import repair_port as repair
    original_port, original_launcher = Path(args.port_home), Path(args.launcher)
    if original_port.is_symlink() or original_launcher.is_symlink():
        raise ValueError('pasta ou launcher simbólico recusado')
    port, launcher, doctor = original_port.resolve(), original_launcher.resolve(), Path(args.doctor_home).resolve()
    if (not port.is_relative_to(launcher.parent) or port == launcher.parent
            or any(':' in part or any(ord(c)<32 for c in part) for part in port.parts[1:])):
        raise ValueError('pasta deve estar dentro do diretório de ports do launcher')
    state, reason = check(port, launcher)
    if state == 'applied':
        print('Port Doctor: ' + reason); return
    if state != 'available':
        raise ValueError(reason)
    if running(port):
        raise ValueError('feche Hollow Knight antes de aplicar o reparo')
    source = local_file(doctor, 'libexec/aarch64/unity-egl-rebind.so')
    if not source.is_file() or digest(source) != MODULE_SHA256:
        raise ValueError('módulo do Port Doctor ausente ou alterado; reinstale o pacote oficial')
    destination = local_file(port, DESTINATION)
    if destination.exists():
        raise ValueError('já existe um arquivo no destino; não será sobrescrito')
    original = launcher.read_bytes()
    updated = patch_launcher(original.decode('utf-8')).encode('utf-8')
    syntax = subprocess.run(['bash', '-n'], input=updated, capture_output=True, timeout=10)
    if syntax.returncode:
        raise ValueError('launcher gerado não passou na validação de sintaxe')
    folder, manifest = repair.new_backup(doctor, port, launcher, 'unity-egl')
    manifest['created_files'] = [str(destination)]
    manifest['module_sha256'] = MODULE_SHA256
    manifest['verified_build'] = KNOWN
    manifest['log_before'] = repair.log_snapshot(port, launcher, port / 'log.txt')
    repair.save_manifest(folder, manifest)  # rollback record exists before any mutation
    try:
        destination.parent.mkdir(exist_ok=True)
        atomic_replace(destination, source.read_bytes(), 0o644)
        # Detect user edits between preflight and commit.
        if launcher.read_bytes() != original or running(port):
            raise ValueError('o launcher mudou ou o jogo foi aberto durante o reparo')
        atomic_replace(launcher, updated, launcher.stat().st_mode & 0o777 | 0o100)
        if digest(destination) != MODULE_SHA256 or launcher.read_bytes() != updated:
            raise OSError('verificação da gravação falhou')
    except BaseException:
        if launcher.read_bytes() == updated:
            atomic_replace(launcher, original, launcher.stat().st_mode & 0o777)
        if destination.is_file():
            destination.unlink()
        manifest['restored'] = True
        repair.save_manifest(folder, manifest)
        raise
    print(f'Port Doctor: reparo EGL aplicado com backup em {folder}')
    print('Módulo restrito a este jogo. Bibliotecas do sistema, motor Unity, caches e saves preservados.')
    print('Abra o jogo e confira imagem, controles e áudio. Desfazer último reparo restaura o launcher.')

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port-home', required=True)
    parser.add_argument('--launcher')
    args = parser.parse_args()
    state, reason = check(Path(args.port_home), Path(args.launcher) if args.launcher else None)
    print(state)
    print(reason)

if __name__ == '__main__':
    main()
