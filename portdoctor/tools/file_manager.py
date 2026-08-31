#!/usr/bin/env python3
"""Unprivileged storage manager. Plans are previews, never executable shell text.

Only /roms and /roms2 are writable. Deletion is an atomic same-filesystem move
to a journalled trash. Permanent removal requires its own fresh, explicit plan.
No traversal of symlinks or nested mounts; no automatic game/save classification.
"""
import contextlib
import ctypes
import errno
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import stat
import sys
import time
import uuid

LIMIT = 100000
AGE = 30 * 86400
TAG = 'portdoctor-storage-v1'
PROTECTED = {'bios', 'tools', 'portmaster', 'portdoctor', 'runtimes', 'lost+found',
             '.portdoctor-trash', '.portdoctor-state', 'portdoctor-install-backups',
             'system volume information', '$recycle.bin'}


def display(value):
    return ''.join(c if ord(c) >= 32 and ord(c) != 127 else repr(c)[1:-1] for c in str(value))


def size_text(size):
    for unit in ('B', 'KiB', 'MiB', 'GiB', 'TiB'):
        if size < 1024 or unit == 'TiB':
            return f'{size:.1f} {unit}'
        size /= 1024


def inside(path, root):
    return path == root or root in path.parents


def atomic_json(path, value):
    temporary = path.with_name(path.name + '.' + uuid.uuid4().hex + '.tmp')
    try:
        with temporary.open('x', encoding='utf-8') as handle:
            json.dump(value, handle, ensure_ascii=True)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def rename_new(source, destination):
    """Use atomic no-replace when available; reserve/recheck on legacy exFAT.

    The fallback replaces only our own untouched empty reservation. The app's
    card lock serializes its operations. External file transfers must be stopped.
    """
    if os.name == 'posix':
        libc = ctypes.CDLL(None, use_errno=True)
        function = getattr(libc, 'renameat2', None)
        if function is None:
            return reserved_rename(source, destination)
        function.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint]
        function.restype = ctypes.c_int
        if function(-100, os.fsencode(source), -100, os.fsencode(destination), 1):
            code = ctypes.get_errno()
            if code in (errno.EINVAL, errno.EOPNOTSUPP, errno.ENOSYS):
                return reserved_rename(source, destination)
            raise OSError(code, os.strerror(code), str(destination))
    else:  # Windows test fixtures: rename refuses an existing destination.
        os.rename(source, destination)


def reserved_rename(source, destination):
    """Do not fall back to an unchecked rename on older FAT/exFAT drivers."""
    directory = source.is_dir() and not source.is_symlink()
    if directory:
        destination.mkdir(mode=0o700)  # exclusive; never exist_ok
    else:
        descriptor = os.open(destination, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        os.close(descriptor)
    def identity():
        s = destination.lstat()
        return (s.st_dev, s.st_ino, s.st_mode, s.st_size, s.st_mtime_ns, s.st_ctime_ns)
    reservation = identity()
    def untouched():
        return identity() == reservation and (not directory or not any(destination.iterdir()))
    published = False
    try:
        if not untouched():
            raise ValueError('Destino alterado por outro programa. Origem preservada.')
        os.rename(source, destination)  # only replaces the owned empty reservation
        published = True
    finally:
        if not published and destination.exists() and untouched():
            destination.rmdir() if directory else destination.unlink()


class Manager:
    def __init__(self, roots=None, doctor=None, proc=Path('/proc')):
        self.roots = [Path(p).absolute() for p in (roots or ['/roms', '/roms2'])
                      if Path(p).is_dir() and not Path(p).is_symlink()]
        self.doctor = Path(doctor or Path(__file__).resolve().parents[1]).absolute()
        self.proc = proc
        self.mounts = set()
        try:
            for line in (proc / 'self/mountinfo').read_text().splitlines():
                value = re.sub(r'\\([0-7]{3})', lambda m: chr(int(m[1], 8)), line.split()[4])
                self.mounts.add(Path(value))
        except OSError:
            pass

    def path(self, raw, write=False, exists=True, internal=False):
        p = Path(raw)
        if not p.is_absolute() or '..' in p.parts:
            raise ValueError('Caminho relativo ou com .. recusado.')
        root = next((r for r in self.roots if inside(p, r)), None)
        if root is None:
            raise ValueError('Operação permitida apenas nos cartões /roms e /roms2.')
        current = root
        for part in p.relative_to(root).parts:
            current /= part
            if current.is_symlink():
                raise ValueError('Link simbólico: não será seguido ou alterado: ' + display(current))
            if current in self.mounts or (current.exists() and os.path.ismount(current)):
                raise ValueError('Montagem interna/rede protegida: ' + display(current))
        if exists and not p.exists():
            raise ValueError('Arquivo não existe mais: ' + display(p))
        if write and not internal:
            relative = p.relative_to(root)
            if len(relative.parts) == 0 or (len(relative.parts) == 1 and p.is_dir()):
                raise ValueError('A raiz do cartão e as pastas dos sistemas são protegidas.')
            if any(part.lower() in PROTECTED or part.startswith('.portdoctor-') for part in relative.parts):
                raise ValueError('Componente do sistema, lixeira ou ferramenta protegido.')
            if inside(p, self.doctor) or inside(self.doctor, p):
                raise ValueError('O Port Doctor não pode modificar a própria instalação.')
            if p.name.lower() in {'gamelist.xml', 'port doctor r36s.sh', 'portmaster.sh'}:
                raise ValueError('Metadados/ferramenta protegidos; use a função específica.')
        return p, root

    def snapshot(self, p, content=False):
        """No symlink traversal. Detect changed files and mountpoints in recursive plans."""
        h = hashlib.sha256()
        device = p.lstat().st_dev
        count = total = allocated = 0
        pending = [p]
        while pending:
            item = pending.pop()
            s = item.lstat()
            if s.st_dev != device or item in self.mounts and item != p:
                raise ValueError('Operação cruza uma montagem: ' + display(item))
            if not (stat.S_ISREG(s.st_mode) or stat.S_ISDIR(s.st_mode) or stat.S_ISLNK(s.st_mode)):
                raise ValueError('Arquivo especial protegido: ' + display(item))
            count += 1
            if count > LIMIT:
                raise ValueError('Pasta muito grande para uma operação única; selecione subpastas.')
            rel = str(item.relative_to(p))
            values = [rel, s.st_dev, s.st_ino, s.st_mode, s.st_size, s.st_mtime_ns, s.st_ctime_ns]
            if item.is_symlink():
                values.append(os.readlink(item))
                if content:
                    raise ValueError('Cópia com links não é suportada; originais preservados.')
            elif item.is_dir():
                pending.extend(sorted(item.iterdir(), reverse=True))
            else:
                total += s.st_size
                allocated += getattr(s, 'st_blocks', (s.st_size + 511) // 512) * 512
                if content:
                    with item.open('rb') as stream:
                        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
                            h.update(chunk)
                    # Content comparison ignores timestamps/inodes of a new copy.
                    values = [rel, s.st_size]
            if content and item.is_dir():
                values = [rel, 'directory']
            h.update(json.dumps(values, ensure_ascii=True).encode())
        return {'digest': h.hexdigest(), 'bytes': total, 'allocated': allocated, 'count': count}

    def busy(self, paths):
        """Do not kill games/services. Refuse operations on their open paths."""
        for process in self.proc.glob('[0-9]*'):
            if process.name == str(os.getpid()):
                continue
            candidates = [process / 'exe', process / 'cwd']
            try:
                candidates.extend((process / 'fd').iterdir())
            except (OSError, PermissionError):
                pass
            for candidate in candidates:
                try:
                    target = Path(os.readlink(candidate))
                    if any(inside(target, path) for path in paths):
                        raise ValueError(f'Em uso pelo processo {process.name}. Feche o jogo/transferência primeiro.')
                except OSError:
                    pass

    def private(self, root, name):
        p, _ = self.path(str(root / name), exists=False, internal=True)
        p.mkdir(mode=0o700, exist_ok=True)
        if os.name == 'posix' and p.stat().st_uid != os.geteuid():
            raise ValueError('Pasta de controle pertence a outro usuário.')
        marker = p / 'owner.json'
        if marker.is_symlink():
            raise ValueError('Marcador de controle inválido.')
        if marker.exists():
            if json.loads(marker.read_text()) != {'format': TAG}:
                raise ValueError('Pasta de controle não reconhecida.')
        elif list(p.iterdir()):
            raise ValueError('Pasta de controle preexistente não reconhecida.')
        else:
            atomic_json(marker, {'format': TAG})
        return p

    @contextlib.contextmanager
    def lock(self, root):
        base = self.private(root, '.portdoctor-state')
        path = base / 'lock'
        if path.is_symlink():
            raise ValueError('Trava inválida.')
        with path.open('a') as handle:
            if os.name == 'posix':
                import fcntl
                try:
                    fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
                except BlockingIOError:
                    raise ValueError('Outra operação de arquivos está em andamento.')
            yield base

    def listing(self, raw=None, offset=0):
        if not raw:
            return {'kind': 'files', 'path': '', 'parent': '', 'items': [
                {'name': str(p), 'path': str(p), 'directory': True, 'hint': 'Cartão / armazenamento'} for p in self.roots]}
        p, root = self.path(raw)
        if not p.is_dir():
            raise ValueError('Selecione uma pasta.')
        items = sorted(p.iterdir(), key=lambda q: (not q.is_dir(), q.name.lower()))
        result = []
        offset = max(0, int(offset))
        for item in items[offset:offset + 150]:
            try:
                s = item.lstat()
                result.append({'name': display(item.name), 'path': str(item),
                               'directory': item.is_dir() and not item.is_symlink(),
                               'hint': 'Link protegido' if item.is_symlink() else ('Pasta' if item.is_dir() else size_text(s.st_size))})
            except OSError:
                continue
        disk = shutil.disk_usage(p)
        return {'kind': 'files', 'path': str(p), 'parent': str(p.parent) if p != root else '',
                'items': result, 'offset': offset, 'total': len(items), 'free': size_text(disk.free)}

    def associations(self, folder):
        """Exact PortMaster metadata, or an exact static GAMEDIR path; never execute a launcher."""
        folder, _ = self.path(str(folder), write=True)
        ports = folder.parent
        if ports.name != 'ports' or ports.parent not in self.roots or not folder.is_dir():
            raise ValueError('Desinstalação aceita somente uma pasta de jogo diretamente em ports.')
        claims = {}
        for directory in ports.iterdir():
            meta = directory / 'port.json'
            if directory.is_symlink() or not directory.is_dir() or not meta.is_file() or meta.is_symlink() or meta.stat().st_size > 524288:
                continue
            try:
                data = json.loads(meta.read_text(encoding='utf-8'))
                items = data.get('items', [])
                if isinstance(items, list):
                    claims[directory.name] = {x.rstrip('/') for x in items if isinstance(x, str)}
            except (ValueError, OSError):
                continue
        own = claims.get(folder.name, set())
        launchers = {ports / x for x in own if Path(x).name == x and x.lower().endswith('.sh')}
        if own and folder.name not in own:
            raise ValueError('Metadados não confirmam a pasta do jogo; use seleção manual de arquivos.')
        extra_dirs = [x for x in own if x != folder.name and (ports / x).is_dir()]
        if extra_dirs:
            raise ValueError('Pacote com múltiplas pastas: desinstalação automática recusada.')
        for script in ports.glob('*.sh'):
            if script.is_symlink() or script.stat().st_size > 262144:
                continue
            body = script.read_text(encoding='utf-8', errors='replace')
            match = re.search(r'^\s*(?:export\s+)?GAMEDIR\s*=\s*[\"\']?([^\r\n\"\']+)', body, re.M)
            if match and re.search(r'/ports/' + re.escape(folder.name) + r'/?\s*$', match[1]):
                launchers.add(script)
        launchers = {p for p in launchers if p.exists()}
        if not launchers:
            raise ValueError('Launcher não identificado com segurança. Use o gerenciador para selecionar os arquivos manualmente.')
        for name, items in claims.items():
            if name != folder.name and (folder.name in items or any(p.name in items for p in launchers)):
                raise ValueError('Pasta ou launcher compartilhado com ' + name + '; desinstalação bloqueada.')
        for p in launchers:
            self.path(str(p), write=True)
            # A launcher pointing at a different game must never be removed by a metadata typo.
            body = p.read_text(encoding='utf-8', errors='replace')
            directories = re.findall(r'/ports/([^/\s\"\'${};]+)', body)
            others = {x for x in directories if x != folder.name and (ports / x).is_dir()
                      and x.lower() not in PROTECTED}
            if others:
                raise ValueError('Launcher referencia outra pasta: ' + ', '.join(sorted(others)))
        return [folder] + sorted(launchers)

    def cleanup_candidates(self):
        """Only known generated residues; no global extension-based deletion."""
        result = []
        for root in self.roots:
            ports = root / 'ports'
            if not ports.is_dir() or ports.is_symlink():
                continue
            for folder in ports.iterdir():
                if not folder.is_dir() or folder.is_symlink() or folder.name.lower() in PROTECTED:
                    continue
                # Tombstones are native-crash reports. Keep the latest and all recent reports.
                crashes = sorted((p for p in folder.glob('tombstone_[0-9]*') if p.is_file() and not p.is_symlink()),
                                 key=lambda p: p.stat().st_mtime, reverse=True)
                for p in crashes[1:]:
                    if time.time() - p.stat().st_mtime > AGE:
                        with p.open('rb') as handle:
                            header = handle.read(512)
                        if b'*** *** ***' in header and (b'Build fingerprint:' in header or b'ABI:' in header):
                            result.append((p, 'Registro nativo antigo; o mais recente é preservado'))
                # Common transfer-manager metadata, not game data. Only direct game folders.
                for name in ('Thumbs.db', '.DS_Store'):
                    p = folder / name
                    if not p.is_file() or p.is_symlink() or time.time() - p.stat().st_mtime <= AGE:
                        continue
                    with p.open('rb') as handle:
                        signature = handle.read(8)
                    valid = signature == b'\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1' if name == 'Thumbs.db' else signature == b'\x00\x00\x00\x01Bud1'
                    if valid:
                        result.append((p, 'Metadado do explorador do computador, com mais de 30 dias'))
        return result[:1000]

    def plan(self, request):
        operation = request['operation']
        note = ''
        if operation == 'cleanup':
            candidates = self.cleanup_candidates()
            paths = [p for p, _ in candidates]
            if not paths:
                return {'kind': 'text', 'title': 'Limpeza segura', 'text': 'Nenhum resíduo reconhecido e antigo encontrado.\n\nSaves, BIOS, jogos, runtimes, bibliotecas, logs recentes e backups não são lixo. A varredura não remove arquivos desconhecidos. Use a lixeira para liberar o espaço dos itens que você excluiu.'}
            note = '\n'.join(display(p) + '\n  ' + reason for p, reason in candidates)
        elif operation == 'uninstall':
            paths = self.associations(Path(request['path']))
            note = 'A pasta inteira será movida, INCLUSIVE saves que estiverem dentro dela. Saves externos não serão alterados.\nO launcher sairá do menu após recarregar o EmulationStation.\nPara liberar espaço, esvazie a lixeira depois.\n'
        elif operation in ('delete', 'copy', 'move', 'rename'):
            paths = [self.path(request['path'], write=operation != 'copy')[0]]
        elif operation == 'mkdir':
            paths = []
        elif operation in ('restore', 'purge', 'purge_all'):
            return self.trash_plan(request)
        else:
            raise ValueError('Operação desconhecida.')
        if paths:
            root = self.path(str(paths[0]))[1]
        else:
            root = self.path(request['destination'])[1]
        # Multiple cards are separate transactions, never a partial combined cleanup.
        if any(self.path(str(p))[1] != root for p in paths):
            paths = [p for p in paths if self.path(str(p))[1] == root]
            note += '\nHá outros cartões: repita a varredura após esta operação.\n'
        if operation != 'copy':
            for p in paths:
                self.path(str(p), write=True)
            self.busy(paths)
        destination = None
        if operation in ('copy', 'move', 'rename', 'mkdir'):
            parent, _ = self.path(request['destination'])
            if not parent.is_dir():
                raise ValueError('Destino não é uma pasta.')
            name = request.get('name') if operation in ('rename', 'mkdir') else paths[0].name
            if not name or name in ('.', '..') or any(c in name for c in '/\\\x00\r\n') or len(name.encode('utf-8')) > 240:
                raise ValueError('Nome inválido (até 240 bytes, sem barras ou quebras de linha).')
            destination, _ = self.path(str(parent / name), write=True, exists=False)
            if destination.exists():
                raise ValueError('O destino já existe. Nenhum arquivo será sobrescrito. Renomeie primeiro.')
            if paths and inside(destination, paths[0]):
                raise ValueError('Destino dentro da própria origem recusado.')
            if operation in ('move', 'rename') and paths[0].stat().st_dev != parent.stat().st_dev:
                raise ValueError('Recorte entre cartões não é permitido. Copie, confira o resultado e exclua a origem separadamente.')
        snapshots = [self.snapshot(p) for p in paths]
        if operation == 'copy':
            self.snapshot(paths[0], content=True)  # Reject symlinks/special files before any writes.
            if shutil.disk_usage(destination.parent).free < snapshots[0]['bytes'] + 16 * 1024 * 1024:
                raise ValueError('Espaço insuficiente para copiar com margem de segurança.')
        total = sum(s['allocated'] for s in snapshots)
        title = {'delete': 'Excluir para a lixeira', 'uninstall': 'Desinstalar jogo', 'cleanup': 'Limpeza segura',
                 'copy': 'Copiar', 'move': 'Recortar / mover', 'rename': 'Renomear', 'mkdir': 'Criar pasta'}[operation]
        text = title + '\n\n' + '\n'.join(display(p) for p in paths)
        if destination:
            text += '\n\nDestino: ' + display(destination)
        text += '\n\nTamanho aproximado em disco: ' + size_text(total) + '\n\n' + note
        text += '\nFeche o jogo e termine transferências USB/rede antes de confirmar.'
        if operation in ('delete', 'uninstall', 'cleanup'):
            text += '\nRecuperável na Lixeira. Espaço liberado somente ao esvaziá-la. Nenhum arquivo de sistema será apagado.'
        return self.save_plan(root, {'operation': operation, 'paths': [str(p) for p in paths], 'snapshots': snapshots,
                                    'destination': str(destination) if destination else None, 'title': title, 'text': text})

    def save_plan(self, root, plan):
        with self.lock(root) as base:
            token = uuid.uuid4().hex
            plan.update({'created': time.time(), 'token': token, 'root': str(root), 'format': TAG})
            atomic_json(base / (token + '.json'), plan)
        return {'kind': 'plan', 'title': plan['title'], 'text': plan['text'], 'token': token, 'root': str(root), 'operation': plan['operation'],
                'permanent': plan['operation'] in ('purge', 'purge_all')}

    def trash_items(self):
        result = []
        for root in self.roots:
            base = root / '.portdoctor-trash'
            if not base.exists():
                continue
            self.private(root, '.portdoctor-trash')
            for directory in sorted(base.iterdir(), reverse=True):
                if not re.fullmatch('[0-9a-f]{32}', directory.name) or directory.is_symlink() or not directory.is_dir():
                    continue
                manifest = directory / 'manifest.json'
                if not manifest.is_file() or manifest.is_symlink():
                    continue
                data = json.loads(manifest.read_text())
                if data.get('format') == TAG:
                    result.append({'name': data.get('title', 'Arquivos'), 'path': str(directory),
                                   'hint': time.strftime('%d/%m %H:%M', time.localtime(data['created'])) + ' | ' + size_text(self.snapshot(directory)['allocated'])})
        return {'kind': 'trash', 'items': result}

    def trash_manifest(self, raw):
        p, root = self.path(raw, internal=True)
        if p.parent != root / '.portdoctor-trash' or not re.fullmatch('[0-9a-f]{32}', p.name):
            raise ValueError('Item de lixeira inválido.')
        self.private(root, '.portdoctor-trash')
        manifest, _ = self.path(str(p / 'manifest.json'), internal=True)
        data = json.loads(manifest.read_text())
        if data.get('format') != TAG:
            raise ValueError('Registro de lixeira inválido.')
        for i, entry in enumerate(data['entries']):
            self.path(entry['original'], write=True, exists=False)
            if entry['slot'] != str(i):
                raise ValueError('Registro de recuperação inválido.')
        return p, root, data

    def trash_plan(self, request):
        if request['operation'] == 'purge_all':
            items = self.trash_items()['items']
            if not items:
                return {'kind': 'text', 'title': 'Lixeira vazia', 'text': 'Nenhum item para apagar.'}
            _, root, _ = self.trash_manifest(items[0]['path'])
            paths = []
            originals = []
            for item in items:
                p, item_root, data = self.trash_manifest(item['path'])
                if item_root == root:
                    paths.append(p)
                    originals.extend(e['original'] for e in data['entries'] if (p / e['slot']).exists())
            self.busy(paths)
            snapshots = [self.snapshot(p) for p in paths]
            text = 'Esvaziar a lixeira de ' + str(root) + '\n\n' + '\n'.join(display(p) for p in originals)
            text += '\n\nEspaço estimado: ' + size_text(sum(s['allocated'] for s in snapshots))
            text += '\n\nIRREVERSÍVEL. Inclui os saves que estiverem nos itens acima. A lixeira de outros cartões não será alterada; repita a ação para o próximo cartão.'
            return self.save_plan(root, {'operation': 'purge_all', 'paths': [str(p) for p in paths],
                                        'snapshots': snapshots, 'title': 'Esvaziar lixeira', 'text': text})
        p, root, data = self.trash_manifest(request['path'])
        operation = request['operation']
        self.busy([p])
        existing = [e for e in data['entries'] if (p / e['slot']).exists()]
        if operation == 'restore':
            for e in existing:
                target, _ = self.path(e['original'], write=True, exists=False)
                if target.exists() or not target.parent.is_dir():
                    raise ValueError('Não é possível restaurar: destino existe ou pasta pai ausente: ' + display(target))
        title = 'Restaurar da lixeira' if operation == 'restore' else 'Apagar definitivamente'
        snapshot = self.snapshot(p)
        text = title + '\n\n' + '\n'.join(display(e['original']) for e in existing)
        text += '\n\nTamanho em disco: ' + size_text(snapshot['allocated'])
        text += '\n\nIRREVERSÍVEL: inclui os saves que foram excluídos junto com estas pastas.' if operation == 'purge' else '\n\nOs nomes e locais originais serão restaurados. Nenhum arquivo atual será sobrescrito.'
        return self.save_plan(root, {'operation': operation, 'paths': [str(p)], 'snapshots': [snapshot], 'title': title, 'text': text})

    def execute(self, root_raw, token):
        root = Path(root_raw)
        if root not in self.roots or not re.fullmatch('[0-9a-f]{32}', token):
            raise ValueError('Confirmação inválida.')
        with self.lock(root) as base:
            planfile, _ = self.path(str(base / (token + '.json')), internal=True)
            plan = json.loads(planfile.read_text())
            if plan.get('format') != TAG or time.time() - plan['created'] > 900 or plan.get('used'):
                raise ValueError('Prévia expirada ou já utilizada. Verifique novamente.')
            op = plan['operation']
            paths = [self.path(p, write=op not in ('copy', 'restore', 'purge', 'purge_all'), internal=op in ('restore', 'purge', 'purge_all'))[0]
                     for p in plan['paths']]
            for p, previous in zip(paths, plan['snapshots']):
                if self.snapshot(p) != previous:
                    raise ValueError('Arquivos mudaram desde a prévia. Nenhuma alteração aplicada; gere nova prévia.')
            self.busy(paths)
            if op == 'uninstall' and self.associations(paths[0]) != paths:
                raise ValueError('A associação do jogo mudou. Refaça a prévia.')
            destination = plan.get('destination')
            if destination:
                destination, _ = self.path(destination, write=True, exists=False)
                if destination.exists():
                    raise ValueError('Destino já existe; nada sobrescrito.')
            # Consumed before the first mutation: interrupted tasks cannot be replayed blindly.
            plan['used'] = True
            atomic_json(planfile, plan)
            if op in ('delete', 'cleanup', 'uninstall'):
                message = self.to_trash(root, paths, plan)
            elif op in ('move', 'rename'):
                if paths[0].stat().st_dev != destination.parent.stat().st_dev:
                    raise ValueError('Recorte entre cartões recusado.')
                rename_new(paths[0], destination)
                message = 'Movido para: ' + display(destination)
            elif op == 'mkdir':
                destination.mkdir(mode=0o755)
                message = 'Pasta criada: ' + display(destination)
            elif op == 'copy':
                message = self.copy(paths[0], destination, plan['snapshots'][0])
            elif op == 'restore':
                message = self.restore(paths[0])
            elif op in ('purge', 'purge_all'):
                for p in paths:
                    self.trash_manifest(str(p))
                before = shutil.disk_usage(root).free
                count = 0
                try:
                    for p in paths:
                        # Keep the recovery journal until every payload has been removed.
                        # A full-disk/I/O failure must not hide surviving slots from the UI.
                        for child in p.iterdir():
                            if child.name == 'manifest.json':
                                continue
                            if child.is_dir() and not child.is_symlink():
                                shutil.rmtree(child)  # fd-safe on Linux; mounts rejected above.
                            else:
                                child.unlink()
                        (p / 'manifest.json').unlink()
                        p.rmdir()
                        count += 1
                except OSError as error:
                    raise ValueError(f'Limpeza interrompida após {count} itens. Itens já apagados não são recuperáveis; confira os restantes na lixeira. {error}')
                after = shutil.disk_usage(root).free
                message = f'{count} item(ns) removido(s) definitivamente. Variação do espaço livre: ' + size_text(max(0, after - before)) + '\nA medição pode variar por gravações de outros programas.'
            else:
                raise ValueError('Operação inválida.')
            with contextlib.suppress(OSError):
                planfile.unlink()  # already consumed; bookkeeping failure must not undo success
            return {'kind': 'text', 'title': 'Operação concluída', 'text': message}

    def to_trash(self, root, paths, plan):
        base = self.private(root, '.portdoctor-trash')
        directory = base / uuid.uuid4().hex
        directory.mkdir(mode=0o700)
        entries = [{'original': str(p), 'slot': str(i)} for i, p in enumerate(paths)]
        manifest = {'format': TAG, 'title': plan['title'] + ': ' + paths[0].name,
                    'created': time.time(), 'entries': entries, 'status': 'moving'}
        atomic_json(directory / 'manifest.json', manifest)
        moved = []
        try:
            for p, entry in zip(paths, entries):
                self.path(str(p), write=True)
                rename_new(p, directory / entry['slot'])
                moved.append(entry)
            manifest['status'] = 'complete'
            atomic_json(directory / 'manifest.json', manifest)
        except Exception:
            for e in reversed(moved):
                try:
                    rename_new(directory / e['slot'], Path(e['original']))
                except OSError:
                    pass  # Journal remains; recovery UI restores only surviving slots.
            raise ValueError('Operação interrompida; originais foram restaurados quando possível. Consulte a lixeira para recuperar itens remanescentes.')
        return 'Movido para a lixeira. Ainda não liberou espaço.\n\n' + '\n'.join(display(p) for p in paths) + '\n\nUse Lixeira > Restaurar para desfazer ou Apagar definitivamente para liberar espaço.\nReinicie o EmulationStation para atualizar a lista de jogos.'

    def restore(self, directory):
        directory, _, data = self.trash_manifest(str(directory))
        entries = [e for e in data['entries'] if (directory / e['slot']).exists()]
        for e in entries:
            p, _ = self.path(e['original'], write=True, exists=False)
            if p.exists() or not p.parent.is_dir():
                raise ValueError('Destino alterado; restauração recusada sem sobrescrever.')
        moved = []
        try:
            for e in entries:
                rename_new(directory / e['slot'], Path(e['original']))
                moved.append(e)
        except Exception:
            for e in reversed(moved):
                with contextlib.suppress(OSError):
                    rename_new(Path(e['original']), directory / e['slot'])
            raise ValueError('Restauração interrompida. Consulte a lixeira e os caminhos originais; nenhum destino foi sobrescrito.')
        (directory / 'manifest.json').unlink()
        directory.rmdir()
        return 'Restaurado nos locais originais. Reinicie o EmulationStation para recarregar os jogos.'

    def copy(self, source, destination, previous):
        if shutil.disk_usage(destination.parent).free < previous['bytes'] + 16 * 1024 * 1024:
            raise ValueError('Espaço insuficiente no destino.')
        digest = self.snapshot(source, content=True)['digest']
        staging = destination.parent / ('.portdoctor-copy-' + uuid.uuid4().hex)
        try:
            if source.is_dir():
                # symlinks=True avoids following a link inserted during the copy; validation then rejects it.
                shutil.copytree(source, staging, symlinks=True)
            else:
                with source.open('rb') as src, staging.open('xb') as dst:
                    shutil.copyfileobj(src, dst, 1024 * 1024)
                    dst.flush()
                    os.fsync(dst.fileno())
                shutil.copystat(source, staging)
            if self.snapshot(source) != previous or self.snapshot(staging, content=True)['digest'] != digest:
                raise ValueError('Cópia não validada. Origem preservada; destino não ativado.')
            self.path(str(destination), write=True, exists=False)
            rename_new(staging, destination)
        finally:
            if staging.exists():
                if staging.is_dir():
                    shutil.rmtree(staging)
                else:
                    staging.unlink()
        return 'Cópia validada por SHA-256. Origem preservada.\nDestino: ' + display(destination)

    def request(self, data):
        action = data.get('action')
        if action == 'list':
            return self.listing(data.get('path'), data.get('offset', 0))
        if action == 'trash':
            return self.trash_items()
        if action == 'plan':
            return self.plan(data)
        if action == 'execute':
            return self.execute(data['root'], data['token'])
        if action == 'info':
            p, _ = self.path(data['path'])
            s = self.snapshot(p)
            return {'kind': 'text', 'title': 'Propriedades', 'text': display(p) + '\n\n' + size_text(s['bytes']) +
                    ' de conteúdo\n' + size_text(s['allocated']) + ' em disco\n' + str(s['count']) + ' itens\n\nSaves dentro da pasta acompanham sua movimentação/exclusão.'}
        raise ValueError('Ação desconhecida.')


def main():
    try:
        if os.name == 'posix' and os.geteuid() == 0:
            raise ValueError('Gerenciador deve executar como usuário comum, nunca como root.')
        request = json.loads(sys.argv[1])
        result = Manager().request(request)
        result['ok'] = True
    except Exception as error:
        result = {'ok': False, 'kind': 'text', 'title': 'Ação não concluída', 'text': str(error)}
    print(json.dumps(result, ensure_ascii=True))


if __name__ == '__main__':
    main()
