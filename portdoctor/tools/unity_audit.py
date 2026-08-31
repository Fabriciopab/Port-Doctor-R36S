#!/usr/bin/env python3
"""Read-only checks for extracted Unity Android ports. Does not execute game code."""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
from pathlib import Path, PurePosixPath


MAX_MANIFEST = 8 * 1024 * 1024
MAX_ENTRIES = 20000
MAX_TOTAL = 8 * 1024 * 1024 * 1024


def confined(root: Path, name: str) -> Path:
    relative = PurePosixPath(name)
    if (not name or '\\' in name or ':' in name or relative.is_absolute()
            or '..' in relative.parts or any(ord(c) < 32 for c in name)):
        raise ValueError('caminho inválido no manifesto')
    path = root.joinpath(*relative.parts)
    if not path.resolve().is_relative_to(root.resolve()):
        raise ValueError('caminho sai da pasta do jogo')
    return path


def fingerprint(path: Path) -> dict:
    result = {'file': path.name, 'size': path.stat().st_size}
    with path.open('rb') as stream:
        header = stream.read(20)
        stream.seek(0)
        digest = hashlib.sha256()
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    result['sha256'] = digest.hexdigest()
    result['architecture'] = 'não identificado'
    if header[:4] == b'\x7fELF' and len(header) == 20 and header[5] in (1, 2):
        machine = int.from_bytes(header[18:20], 'little' if header[5] == 1 else 'big')
        result['architecture'] = {(1, 40): 'armhf', (2, 183): 'aarch64',
                                  (2, 62): 'x86_64'}.get((header[4], machine), 'outro ELF')
    return result


def verify_manifest(root: Path) -> dict:
    root = root.resolve()
    manifest = confined(root, 'META-INF/MANIFEST.MF')
    result = {'status': 'unavailable', 'matching': 0, 'missing': [], 'different': [],
              'rejected': [], 'unchecked': 0, 'bytes_checked': 0}
    if not manifest.is_file():
        return result
    if manifest.stat().st_size > MAX_MANIFEST:
        raise ValueError('manifesto excede o limite de leitura')
    text = manifest.read_text(encoding='utf-8', errors='strict').replace('\r\n', '\n')
    text = text.replace('\n ', '')  # JAR continuation lines, including long entry names.
    seen = set()
    for section in text.split('\n\n'):
        pairs = [line.split(': ', 1) for line in section.splitlines() if ': ' in line]
        values = dict(pairs)
        name = values.get('Name')
        if not name:
            continue
        if len(seen) >= MAX_ENTRIES:
            raise ValueError('manifesto excede o limite de entradas')
        try:
            if name in seen or len(values) != len(pairs):
                raise ValueError('entrada ou atributo duplicado')
            seen.add(name)
            path = confined(root, name)
            algorithm, expected = next(((algo, values[key]) for key, algo in
                (('SHA-256-Digest', 'sha256'), ('SHA1-Digest', 'sha1')) if key in values), ('', ''))
            if not algorithm:
                result['unchecked'] += 1
                continue
            expected_bytes = base64.b64decode(expected, validate=True)
            if len(expected_bytes) != hashlib.new(algorithm).digest_size:
                raise ValueError('resumo inválido')
            if not path.is_file():
                result['missing'].append(name)
                continue
            size = path.stat().st_size
            if size + result['bytes_checked'] > MAX_TOTAL:
                raise ValueError('limite total de leitura excedido')
            digest = hashlib.new(algorithm)
            read = 0
            with path.open('rb') as stream:
                for block in iter(lambda: stream.read(1024 * 1024), b''):
                    read += len(block)
                    if result['bytes_checked'] + read > MAX_TOTAL:
                        raise ValueError('limite total de leitura excedido')
                    digest.update(block)
            result['bytes_checked'] += read
            if path.stat().st_size != size or read != size:
                raise ValueError('arquivo mudou durante a leitura; execute com o jogo fechado')
            if digest.digest() == expected_bytes:
                result['matching'] += 1
            else:
                result['different'].append(name)
        except (ValueError, OSError) as error:
            result['rejected'].append({'entry': name, 'reason': str(error)})
    result['status'] = ('mismatch' if any(result[k] for k in ('missing', 'different', 'rejected'))
                        else 'partial' if result['unchecked'] else
                        'matching' if result['matching'] else 'unavailable')
    return result


def audit(port: Path) -> dict:
    port = port.resolve()
    paths = ['unityloader', 'gamedata/lib/arm64-v8a/libunity.so',
             'gamedata/lib/arm64-v8a/libil2cpp.so', 'gamedata/lib/arm64-v8a/libmain.so']
    binaries = []
    for name in paths:
        path = confined(port, name)
        if path.is_file():
            record = fingerprint(path)
            record['file'] = name
            binaries.append(record)
    return {'binaries': binaries, 'manifest': verify_manifest(confined(port, 'gamedata')),
            'automatic_repair': False,
            'notice': 'Comparação com o manifesto local; não autentica o publicador e não comprova que o jogo funciona.'}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port-home', required=True)
    parser.add_argument('--json', action='store_true')
    args = parser.parse_args()
    try:
        result = audit(Path(args.port_home))
    except (ValueError, OSError) as error:
        print('Port Doctor: verificação interrompida: ' + str(error))
        return 1
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print('PACOTE UNITY — somente leitura; execute com o jogo fechado.\n')
        for item in result['binaries']:
            print(f"{item['file']}: {item['architecture']}, {item['size']} bytes\nSHA-256: {item['sha256']}")
        manifest = result['manifest']
        print(f"\nManifesto: {manifest['matching']} arquivos conferem; {len(manifest['missing'])} ausentes; "
              f"{len(manifest['different'])} diferentes; {len(manifest['rejected'])} recusados; "
              f"{manifest['unchecked']} sem resumo suportado.")
        if manifest['status'] == 'unavailable':
            print('Manifesto ausente ou sem entradas verificáveis: integridade INCONCLUSIVA.')
        for category in ('missing', 'different', 'rejected'):
            if manifest[category]:
                print(category + ': ' + json.dumps(manifest[category][:30], ensure_ascii=False))
        print('\n' + result['notice'])
        print('Nenhum arquivo, save ou biblioteca foi alterado. Não há reparo de SIGBUS comprovado para o build de Hollow Knight investigado no dArkOSRE.')
        print('Se houver diferenças, confira a cópia legítima dos arquivos e as versões exigidas pelo autor do port; não substitua libunity.so isoladamente.')
    return 1 if result['manifest']['status'] == 'mismatch' else 0


if __name__ == '__main__':
    raise SystemExit(main())
