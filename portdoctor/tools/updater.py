#!/usr/bin/env python3
"""User-confirmed GitHub release updater; never downloads or runs a remote installer.

Download/validate while the UI is open, invoke the bundled local installer only
after LÖVE exits. Uses public releases from the maintainer's fixed GitHub owner.
SHA-256 verifies integrity against GitHub metadata, not an independent signature.
"""
import argparse
import contextlib
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from zipfile import ZipFile

OWNER = 'Fabriciopab'
MAX_DOWNLOAD = 256 * 1024 * 1024
MAX_UNPACKED = 1536 * 1024 * 1024
APP = 'portdoctor-r36s'


def version(value):
    match = re.fullmatch(r'v?(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)', str(value))
    if not match:
        raise ValueError('Versão inválida; somente releases estáveis no formato v1.2.3.')
    return tuple(map(int, match.groups()))


def sha256(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def atomic_json(path, data):
    if path.is_symlink():
        raise ValueError('Link de configuração recusado.')
    temporary = path.with_name(path.name + '.' + uuid.uuid4().hex + '.tmp')
    try:
        with temporary.open('x', encoding='utf-8') as stream:
            json.dump(data, stream, ensure_ascii=True)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def safe_url(url):
    parts = urllib.parse.urlsplit(url)
    if parts.scheme != 'https' or parts.username or parts.password or parts.port not in (None, 443):
        raise ValueError('A atualização exige HTTPS sem credenciais na URL.')
    if parts.hostname not in ('api.github.com', 'github.com', 'release-assets.githubusercontent.com', 'objects.githubusercontent.com'):
        raise ValueError('Servidor de download não autorizado.')
    return url


class Redirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        safe_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def open_url(url):
    request = urllib.request.Request(safe_url(url), headers={
        'User-Agent': 'PortDoctor-R36S-Updater', 'Accept': 'application/vnd.github+json',
        'X-GitHub-Api-Version': '2022-11-28'})
    return urllib.request.build_opener(Redirect()).open(request, timeout=20)


def api_json(url):
    with open_url(url) as response:
        data = response.read(2 * 1024 * 1024 + 1)
        if len(data) > 2 * 1024 * 1024:
            raise ValueError('Resposta do GitHub excede o limite.')
    return json.loads(data)


def validate_zip(path, expected):
    """Validate before the bundled installer gets any opportunity to extract."""
    required = {'Port Doctor R36S.sh', 'portdoctor/release.json', 'portdoctor/lovegame/main.lua',
                'portdoctor/lovegame/conf.lua', 'portdoctor/portdoctor.gptk',
                'portdoctor/tools/updater.py', 'portdoctor/tools/update-install.sh'}
    roots = {'Port Doctor R36S.sh', 'port.json', 'gameinfo.xml', 'README.md', 'screenshot.png', 'cover.png'}
    with ZipFile(path) as archive:
        seen = set()
        total = 0
        infos = archive.infolist()
        if len(infos) > 15000:
            raise ValueError('Pacote contém arquivos demais.')
        for info in infos:
            name = info.orig_filename
            p = PurePosixPath(name)
            mode = info.external_attr >> 16
            if not name or name.startswith('/') or '\\' in name or ':' in name or '\x00' in name or '..' in p.parts:
                raise ValueError('Caminho inseguro no ZIP: ' + repr(name))
            if any(part in ('.', '') or part.rstrip(' .') != part for part in name.rstrip('/').split('/')):
                raise ValueError('Nome ambíguo no ZIP.')
            key = name.rstrip('/').casefold()
            if key in seen:
                raise ValueError('Nomes duplicados/ambíguos no ZIP.')
            seen.add(key)
            if stat.S_IFMT(mode) not in (0, stat.S_IFREG, stat.S_IFDIR) or info.flag_bits & 1:
                raise ValueError('Links, arquivos especiais ou criptografados não são permitidos.')
            if name not in roots and (not p.parts or p.parts[0] != 'portdoctor'):
                raise ValueError('O pacote tenta alterar algo fora do Port Doctor.')
            if len(p.parts) >= 2 and p.parts[1].casefold() == 'conf' and not info.is_dir():
                raise ValueError('Pacote não pode substituir dados pessoais em conf.')
            if any(part.startswith('.portdoctor') for part in p.parts):
                raise ValueError('Pasta interna do atualizador não permitida no pacote.')
            if info.file_size > MAX_UNPACKED or info.compress_size and info.file_size / info.compress_size > 300:
                raise ValueError('Taxa de expansão do pacote recusada.')
            total += info.file_size
            if total > MAX_UNPACKED:
                raise ValueError('Pacote descompactado muito grande.')
        if not required.issubset({i.filename for i in infos}):
            raise ValueError('Pacote incompleto ou não é uma atualização do Port Doctor.')
        if archive.getinfo('portdoctor/release.json').file_size > 16384:
            raise ValueError('Manifesto de versão inválido.')
        manifest = json.loads(archive.read('portdoctor/release.json'))
        if manifest.get('app') != APP or manifest.get('github_owner') != OWNER or version(manifest.get('version')) != version(expected) or manifest.get('update_protocol') != 1:
            raise ValueError('Versão/identificação interna do pacote não confere com a release.')
        if archive.testzip():
            raise ValueError('Arquivo corrompido no ZIP.')
    return total


class Updater:
    def __init__(self, home=None):
        self.home = Path(home or Path(__file__).resolve().parents[1]).absolute()
        self.ports = self.home.parent
        self.base = self.ports / '.portdoctor-updates'
        self.manifest = json.loads((self.home / 'release.json').read_text(encoding='utf-8'))
        if self.manifest.get('app') != APP or self.manifest.get('github_owner') != OWNER:
            raise ValueError('Identidade do app não reconhecida.')
        version(self.manifest['version'])

    def check_paths(self):
        for p in (self.ports, self.home, self.home / 'conf', self.base):
            if p.is_symlink():
                raise ValueError('Atualização recusada em pasta com link simbólico.')
        if not os.access(self.ports, os.W_OK) or not os.access(self.home, os.W_OK):
            raise ValueError('Sem permissão de atualizar esta instalação; use o instalador pelo menu Tools.')

    def repository(self):
        configured = self.home / 'conf/update-channel.json'
        value = self.manifest.get('github_repository')
        if configured.exists():
            if configured.is_symlink():
                raise ValueError('Configuração não pode ser um link.')
            value = json.loads(configured.read_text()).get('repository')
        if value is not None and (not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,99}', value)):
            raise ValueError('Nome de repositório inválido.')
        return value

    def configure(self, name):
        if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,99}', name):
            raise ValueError('Digite somente o nome do repositório, sem URL ou nome do usuário.')
        info = api_json(f'https://api.github.com/repos/{OWNER}/{name}')
        if info.get('full_name', '').lower() != f'{OWNER}/{name}'.lower() or info.get('private'):
            raise ValueError('Repositório público do mantenedor não confirmado.')
        self.check_paths()
        (self.home / 'conf').mkdir(exist_ok=True)
        atomic_json(self.home / 'conf/update-channel.json', {'repository': name})
        return {'kind': 'text', 'title': 'Canal configurado', 'text': f'Origem: {OWNER}/{name}\nAgora use Verificar atualizações. O app só aceita pacotes identificados como Port Doctor, com versão e SHA-256 válidos.'}

    def release(self, release_id=None):
        repo = self.repository()
        if not repo:
            return None
        suffix = str(release_id) if release_id is not None else 'latest'
        if suffix != 'latest' and not re.fullmatch(r'[0-9]+', suffix):
            raise ValueError('Release inválida.')
        data = api_json(f'https://api.github.com/repos/{OWNER}/{repo}/releases/{suffix}')
        tag = data.get('tag_name')
        latest = version(tag)
        if data.get('draft') or data.get('prerelease'):
            raise ValueError('A atualização automática aceita somente releases públicas estáveis.')
        normalized = '.'.join(map(str, latest))
        if latest <= version(self.manifest['version']):
            return {'current': True, 'version': normalized, 'repo': repo}
        name = f'Port-Doctor-R36S-v{normalized}.zip'
        assets = [a for a in data.get('assets', []) if a.get('name') == name and a.get('state') == 'uploaded']
        if len(assets) != 1:
            raise ValueError(f'A release precisa conter exatamente o pacote {name}. Não use o ZIP de código-fonte ou o instalador aninhado.')
        asset = assets[0]
        digest = asset.get('digest') or ''
        if not re.fullmatch(r'sha256:[0-9a-fA-F]{64}', digest):
            raise ValueError('GitHub não informou SHA-256 para este asset. O mantenedor precisa reenviar o pacote; download recusado.')
        if not isinstance(asset.get('size'), int) or not 0 < asset['size'] <= MAX_DOWNLOAD:
            raise ValueError('Tamanho de download inválido ou acima de 256 MiB.')
        expected_url = f'https://github.com/{OWNER}/{repo}/releases/download/{urllib.parse.quote(str(tag), safe="")}/{name}'
        url = asset.get('browser_download_url', '')
        if url.lower() != expected_url.lower():
            raise ValueError('O download não pertence à release/repositório selecionado.')
        return {'version': normalized, 'repo': repo, 'id': int(data['id']), 'sha256': digest.split(':')[1].lower(),
                'size': asset['size'], 'url': url, 'created': time.time()}

    def check(self):
        info = self.release()
        if info is None:
            return {'kind': 'text', 'title': 'Canal ainda não configurado',
                    'text': 'O mantenedor ainda precisa definir o repositório público do Port Doctor no GitHub.\n\nNenhum download foi iniciado. Use Configurar repositório quando ele estiver publicado.\n\nConta oficial: Fabriciopab\nVersão instalada: ' + self.manifest['version']}
        if info.get('current'):
            return {'kind': 'text', 'title': 'Versão em dia', 'text': 'Instalada: ' + self.manifest['version'] + '\nÚltima release estável: ' + info['version']}
        return {'kind': 'offer', 'title': 'Atualização disponível', 'offer': info,
                'text': f"Versão instalada: {self.manifest['version']}\nNova versão: {info['version']}\nOrigem: {OWNER}/{info['repo']}\nDownload: {info['size'] / 1048576:.1f} MiB\n\nBaixar, validar e instalar automaticamente? O app fechará para instalar. Será guardada uma cópia da versão anterior.\n\nPreserva conf, backups, pacotes de compatibilidade e jogos. Não atualiza o firmware/dArkOS nem o PortMaster.\n\nMantenha alimentação e internet estáveis; não desligue o console."}

    @contextlib.contextmanager
    def lock(self):
        self.check_paths()
        self.base.mkdir(mode=0o700, exist_ok=True)
        lock = self.base / 'lock'
        if lock.is_symlink():
            raise ValueError('Trava de atualização inválida.')
        with lock.open('a') as stream:
            if os.name == 'posix':
                import fcntl
                try:
                    fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
                except BlockingIOError:
                    raise ValueError('Outra atualização está em andamento.')
            yield

    def prepare(self, release_id, expected_digest):
        with self.lock():
            pending = self.base / 'pending.json'
            if pending.exists():
                raise ValueError('Já existe uma atualização pendente. Saia e abra o app para concluir ou consulte Estado da atualização.')
            info = self.release(release_id)
            if not info or info.get('current') or info['sha256'] != expected_digest:
                raise ValueError('A release mudou desde a consulta; verifique novamente.')
            if shutil.disk_usage(self.ports).free < info['size'] * 3 + 64 * 1024 * 1024:
                raise ValueError('Espaço insuficiente para baixar e preparar a atualização.')
            token = uuid.uuid4().hex
            stage = self.base / token
            stage.mkdir(mode=0o700)
            archive = stage / 'portdoctor.zip'
            completed = False
            try:
                received = 0
                digest = hashlib.sha256()
                started = time.monotonic()
                with open_url(info['url']) as response, archive.open('xb') as output:
                    while True:
                        if time.monotonic() - started > 600:
                            raise ValueError('Download excedeu 10 minutos; tente novamente em rede estável.')
                        chunk = response.read(256 * 1024)
                        if not chunk:
                            break
                        received += len(chunk)
                        if received > info['size']:
                            raise ValueError('Download maior que o informado pelo GitHub.')
                        digest.update(chunk)
                        output.write(chunk)
                    output.flush()
                    os.fsync(output.fileno())
                if received != info['size'] or digest.hexdigest() != info['sha256']:
                    raise ValueError('Download incompleto ou SHA-256 divergente. Instalação não iniciada.')
                unpacked = validate_zip(archive, info['version'])
                # Current installer preserves conf and packs by copying; reserve their full size.
                preserved = 0
                for name in ('conf', 'compat-packs'):
                    for directory, dirs, files in os.walk(self.home / name, followlinks=False):
                        for filename in files:
                            p = Path(directory) / filename
                            if not p.is_symlink():
                                preserved += p.stat().st_size
                if shutil.disk_usage(self.ports).free < unpacked + preserved + 64 * 1024 * 1024:
                    raise ValueError('Espaço insuficiente para extrair e preservar os dados de reparos.')
                local_installer = self.home / 'tools/update-install.sh'
                if not local_installer.is_file() or local_installer.is_symlink():
                    raise ValueError('Instalador local confiável ausente. Reinstale o Port Doctor pelo menu Tools.')
                shutil.copy2(local_installer, stage / 'install.sh')
                info.update({'token': token, 'state': 'ready', 'installer_sha256': sha256(stage / 'install.sh')})
                atomic_json(stage / 'state.json', info)
                atomic_json(pending, {'token': token})
                completed = True
            finally:
                if not completed:
                    # Only this freshly-created UUID directory is removed; installed app is untouched.
                    shutil.rmtree(stage)
            return {'kind': 'ready', 'title': 'Download validado', 'text': 'Fechando o Port Doctor para instalar a versão ' + info['version'] + '.\nNão desligue o console. Ao terminar, abra novamente pelo menu Ports.'}

    def pending(self):
        marker = self.base / 'pending.json'
        if not marker.exists():
            return None
        if marker.is_symlink():
            raise ValueError('Marcador de atualização inválido.')
        token = json.loads(marker.read_text()).get('token', '')
        if not re.fullmatch(r'[0-9a-f]{32}', token):
            raise ValueError('Identificação da atualização inválida.')
        stage = self.base / token
        if stage.is_symlink() or (stage / 'state.json').is_symlink():
            raise ValueError('Pasta da atualização inválida.')
        return stage, json.loads((stage / 'state.json').read_text())

    def status(self):
        pending = self.pending()
        text = f"Versão: {self.manifest['version']}\nOrigem: {OWNER}/{self.repository() or '(a definir)'}\n"
        if pending:
            stage, info = pending
            text += '\nAtualização pendente: ' + info['version'] + '\nEstado: ' + info['state']
            text += '\nAo sair do app, um pacote validado pendente será instalado.' if info['state'] == 'ready' else '\nA tentativa anterior foi interrompida. Não será repetida automaticamente. Use o instalador pelo menu Tools; backups ficam em portdoctor-install-backups.'
            text += '\n\nPasta do registro: ' + str(stage)
        else:
            text += '\nNenhuma instalação pendente.'
        report = self.base / 'last-result.json'
        if report.is_file() and not report.is_symlink():
            last = json.loads(report.read_text())
            text += '\n\nÚltima tentativa: ' + last.get('text', 'sem detalhes')
        return {'kind': 'text', 'title': 'Estado da atualização', 'text': text}

    def apply(self):
        with self.lock():
            pending = self.pending()
            if not pending:
                return {'kind': 'text', 'title': 'Sem atualização pendente', 'text': 'Nada foi alterado.'}
            stage, info = pending
            if info['state'] != 'ready':
                raise ValueError('Instalação anterior interrompida; repetição automática bloqueada. Consulte o registro e use o instalador pelo menu Tools.')
            archive = stage / 'portdoctor.zip'
            installer = stage / 'install.sh'
            if archive.is_symlink() or installer.is_symlink() or sha256(archive) != info['sha256'] or sha256(installer) != info['installer_sha256']:
                raise ValueError('Arquivos preparados foram alterados. Nada instalado.')
            validate_zip(archive, info['version'])
            info['state'] = 'installing'
            atomic_json(stage / 'state.json', info)
            result = subprocess.run(['/bin/bash', str(installer)], env={**os.environ,
                'PORTDOCTOR_INSTALL_VERSION': info['version'], 'PORTDOCTOR_INSTALL_PORTS_ROOT': str(self.ports),
                'PORTDOCTOR_INSTALL_NO_RESTART': '1', 'PORTDOCTOR_INSTALL_QUIET': '1'}, capture_output=True, text=True)
            current = self.home / 'release.json'
            success = result.returncode == 0 and current.is_file() and version(json.loads(current.read_text())['version']) == version(info['version'])
            text = 'Versão ' + info['version'] + (' instalada. Abra novamente no menu Ports.' if success else ' não foi instalada com sucesso. Consulte instalacao-portdoctor.log na pasta da atualização e os backups antes de tentar novamente.')
            info['state'] = 'installed' if success else 'failed'
            atomic_json(stage / 'state.json', info)
            atomic_json(self.base / 'last-result.json', {'ok': success, 'text': text, 'stage': str(stage)})
            if success:
                (self.base / 'pending.json').unlink()
                archive.unlink()  # validated download only; backup and installation log are retained
            return {'kind': 'text', 'title': 'Resultado da atualização', 'text': text, 'ok': success}

    def cancel(self):
        with self.lock():
            pending = self.pending()
            if not pending:
                return {'kind': 'text', 'title': 'Nada pendente', 'text': 'Nenhum pacote aguardando instalação.'}
            stage, info = pending
            archive = stage / 'portdoctor.zip'
            archive.unlink(missing_ok=True)
            info['state'] = 'cancelled'
            atomic_json(stage / 'state.json', info)
            (self.base / 'pending.json').unlink()
            return {'kind': 'text', 'title': 'Pacote pendente descartado',
                    'text': 'Somente o download e o agendamento foram removidos. Isso NÃO desfaz uma instalação anterior ou interrompida. Os registros e backups foram preservados.'}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=('check', 'status', 'configure', 'prepare', 'apply', 'cancel'))
    parser.add_argument('--repository')
    parser.add_argument('--release-id', type=int)
    parser.add_argument('--sha256')
    args = parser.parse_args()
    try:
        updater = Updater()
        if args.action == 'configure':
            result = updater.configure(args.repository or '')
        elif args.action == 'prepare':
            result = updater.prepare(args.release_id, args.sha256)
        else:
            result = getattr(updater, args.action)()
        result.setdefault('ok', True)
    except urllib.error.HTTPError as error:
        text = 'Repositório/release pública não encontrado.' if error.code == 404 else 'GitHub indisponível ou limite de consultas atingido. Tente novamente mais tarde.'
        result = {'ok': False, 'kind': 'text', 'title': 'Consulta não concluída', 'text': text}
    except Exception as error:
        result = {'ok': False, 'kind': 'text', 'title': 'Atualização não concluída', 'text': str(error) + '\n\nConfira a conexão e consulte Estado da atualização. Não foi feita uma atualização do firmware.'}
    print(json.dumps(result, ensure_ascii=True))
    if not result['ok']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
