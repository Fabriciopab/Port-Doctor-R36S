#!/usr/bin/env python3
"""Reversible settings repair for the allowlisted Hollow Knight Android build."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import re
import shutil
import unity_egl as egl

PREFS = 'conf/shared_prefs/com.TeamCherry.HollowKnight.v2.playerprefs.json'

def changes(port: Path) -> list[tuple[Path, bytes, bytes]]:
    config = egl.local_file(port, 'hk.toml')
    prefs = egl.local_file(port, PREFS)
    for path in (config, prefs):
        if not path.is_file() or path.stat().st_size > 128*1024:
            raise ValueError('configuração ausente ou muito grande; abra o jogo uma vez')
    original = config.read_bytes()
    text = original.decode('utf-8')
    # Only the known local path layout, not arbitrary destinations from TOML.
    for key, value in (('game_files','./gamedata/'), ('android_files','../conf/'),
                       ('android_external_files','../conf/')):
        entries = re.findall(r'(?m)^\s*' + key + r'\s*=\s*"([^"\n]*)"\s*(?:#.*)?$', text)
        if entries != [value]:
            raise ValueError('caminhos de configuração diferentes do pacote validado')
    sections = list(re.finditer(r'(?ms)^\[gpu\][ \t]*\r?\n(?P<body>.*?)(?=^\[|\Z)', text))
    if len(sections) != 1:
        raise ValueError('seção GPU ausente ou duplicada')
    section = sections[0]
    pattern = r'(?m)^([ \t]*textureMaxDim[ \t]*=[ \t]*)([0-9]+)([ \t]*(?:#[^\r\n]*)?\r?)$'
    matches = list(re.finditer(pattern, section['body']))
    if len(matches) != 1 or len(re.findall(r'(?m)^\s*textureMaxDim\s*=', text)) != 1:
        raise ValueError('limite de textura não reconhecido')
    limit = int(matches[0][2])
    if limit > 16384:
        raise ValueError('limite de textura fora do intervalo reconhecido')
    body = re.sub(pattern, lambda m: m[1] + '0' + m[3], section['body'])
    updated = (text[:section.start('body')] + body + text[section.end('body'):]).encode('utf-8')
    before_prefs = prefs.read_bytes()
    data = json.loads(before_prefs)
    if not isinstance(data, dict) or not isinstance(data.get('ints'), dict):
        raise ValueError('preferências do jogo em formato não reconhecido')
    quality = data['ints'].get('ShaderQuality')
    if type(quality) is not int or quality not in (0, 1, 2):
        raise ValueError('qualidade de desfoque não reconhecida')
    data['ints']['ShaderQuality'] = 2
    after_prefs = before_prefs if quality == 2 else (json.dumps(data, indent=2, ensure_ascii=False) + '\n').encode('utf-8')
    return [(path, before, after) for path, before, after in
            ((config, original, updated), (prefs, before_prefs, after_prefs)) if before != after]

def check(port: Path, launcher: Path) -> tuple[str, str]:
    try:
        if port.is_symlink() or launcher.is_symlink():
            raise ValueError('pasta ou launcher simbólico recusado')
        state, reason = egl.check(port, launcher)
        if state != 'applied':
            return 'unsupported', 'aplique primeiro o reparo EGL do build validado: ' + reason
        if changes(port):
            return 'available', 'texturas/desfoque incompatíveis: ajuste específico disponível'
        return 'applied', 'texturas sem redução e desfoque Alto; confirme a imagem dentro da fase'
    except (OSError, UnicodeError, ValueError) as error:
        return 'unsupported', str(error)

def apply(args):
    import repair_port as repair
    port, launcher, doctor = Path(args.port_home), Path(args.launcher), Path(args.doctor_home)
    state, reason = check(port, launcher)
    if state == 'applied':
        print('Port Doctor: ' + reason); return
    if state != 'available':
        raise ValueError(reason)
    port, launcher, doctor = port.resolve(), launcher.resolve(), doctor.resolve()
    if port == launcher.parent or not port.is_relative_to(launcher.parent):
        raise ValueError('pasta deve estar dentro do diretório de ports do launcher')
    if egl.running(port):
        raise ValueError('feche Hollow Knight antes de ajustar os gráficos')
    planned = changes(port)
    folder, manifest = repair.new_backup(doctor, port, launcher, 'unity-graphics')
    manifest['log_before'] = repair.log_snapshot(port, launcher, port/'log.txt')
    manifest['verified_build'] = egl.KNOWN
    manifest['settings'] = {'textureMaxDim': 0, 'ShaderQuality': 2}
    for index, (path, original, updated) in enumerate(planned):
        backup = folder/f'graphics-original-{index}'
        shutil.copy2(path, backup)
        if backup.read_bytes() != original:
            raise ValueError('configuração mudou durante o backup')
        manifest['replaced_files'].append({'path': str(path), 'backup': str(backup)})
    repair.save_manifest(folder, manifest)
    committed = []
    try:
        for path, before, after in planned:
            if egl.running(port) or path.read_bytes() != before:
                raise ValueError('jogo aberto ou configuração alterada durante o reparo')
            egl.atomic_replace(path, after, path.stat().st_mode & 0o777)
            committed.append((path, before, after))
            if path.read_bytes() != after:
                raise OSError('gravação não pôde ser confirmada')
    except BaseException:
        for path, before, after in reversed(committed):
            if path.read_bytes() == after:
                egl.atomic_replace(path, before, path.stat().st_mode & 0o777)
        manifest['restored'] = True
        repair.save_manifest(folder, manifest)
        raise
    print(f'Port Doctor: ajustes gráficos aplicados; backup em {folder}')
    print('Texturas sem redução e desfoque Alto. Não altera saves, áudio, controles ou drivers.')
    print('Abertura, personagem/cenário, áudio e controles confirmados no build testado com dArkOSRE.')
    print('Limite de quadros e efeitos de dano preservados. Teste sua cópia: log sem erro não comprova imagem correta.')

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port-home', required=True)
    parser.add_argument('--launcher', required=True)
    args = parser.parse_args()
    print('\n'.join(check(Path(args.port_home), Path(args.launcher))))

if __name__ == '__main__':
    main()
