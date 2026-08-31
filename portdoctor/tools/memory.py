#!/usr/bin/env python3
"""Boot-local, owned zram only. Never reset firmware devices or swap with pages in use."""
import argparse
import errno
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
import time

MIB = 1024 * 1024
STATE = Path('/run/portdoctor-zram/state.json')


def read(path):
    return Path(path).read_text().strip()


def save(path, data):
    temporary = path.with_suffix('.tmp')
    if temporary.is_symlink():
        raise RuntimeError('Registro temporário inseguro.')
    with temporary.open('w', encoding='utf-8') as stream:
        json.dump(data, stream)
        stream.flush(); os.fsync(stream.fileno())
    os.chmod(temporary, 0o600)
    temporary.replace(path)


class Linux:
    def memory(self):
        values = {}
        for line in read('/proc/meminfo').splitlines():
            key, value = line.split(':', 1)
            values[key] = int(value.split()[0]) * 1024
        return values['MemTotal'], values.get('MemAvailable', 0)

    def devices(self):
        swaps = {}
        for line in read('/proc/swaps').splitlines()[1:]:
            p = line.split()
            if len(p) >= 5:
                swaps[p[0]] = {'used': int(p[3]) * 1024, 'priority': int(p[4])}
        mounted = {line.split()[0] for line in read('/proc/mounts').splitlines()}
        found = {}
        for base in Path('/sys/block').glob('zram[0-9]*'):
            name = '/dev/' + base.name
            mm = (base / 'mm_stat').read_text().split() if (base / 'mm_stat').exists() else []
            found[base.name] = {'size': int(read(base / 'disksize')), 'used': swaps.get(name, {}).get('used', 0),
                'active': name in swaps, 'mounted': name in mounted,
                'algorithm': read(base / 'comp_algorithm'), 'memory_used': int(mm[2]) if len(mm) > 2 else None}
        return found

    def support(self):
        return Path('/sys/class/zram-control/hot_add').is_file() and Path('/sys/class/zram-control/hot_remove').is_file()

    def create(self):
        # Reading hot_add CREATES a new device. Only called after user confirmation.
        number = read('/sys/class/zram-control/hot_add')
        if not re.fullmatch(r'[0-9]+', number):
            raise RuntimeError('Kernel não devolveu uma identificação válida.')
        return 'zram' + number

    def device(self, name):
        if not re.fullmatch(r'zram[0-9]+', name):
            raise RuntimeError('Dispositivo inválido.')
        path = Path('/dev') / name
        info = path.lstat()
        if not stat.S_ISBLK(info.st_mode):
            raise RuntimeError('Não é um dispositivo de bloco zram.')
        dev = read(Path('/sys/block') / name / 'dev')
        if dev != f'{os.major(info.st_rdev)}:{os.minor(info.st_rdev)}':
            raise RuntimeError('Identidade do dispositivo não confere.')
        return str(path)

    def write(self, name, key, value):
        self.device(name)
        with (Path('/sys/block') / name / key).open('w') as stream:
            stream.write(str(value) + '\n')

    def initialize(self, name, size):
        self.write(name, 'disksize', size)
        if int(read(Path('/sys/block') / name / 'disksize')) != size:
            raise RuntimeError('Tamanho não confirmado pelo kernel.')
        subprocess.run(['mkswap', '-L', 'PORTDOCTOR', self.device(name)], check=True, capture_output=True, timeout=10)

    def activate(self, name):
        subprocess.run(['swapon', '-p', '100', self.device(name)], check=True, capture_output=True, timeout=10)

    def deactivate(self, name):
        subprocess.run(['swapoff', self.device(name)], check=True, capture_output=True, timeout=15)

    def remove_id(self, name):
        with Path('/sys/class/zram-control/hot_remove').open('w') as stream:
            stream.write(name[4:] + '\n')

    def remove(self, name):
        # Kernel 4.4/udev may still hold an opener just after swapoff/mkswap.
        # Retry only EBUSY, bounded to two seconds, rechecking non-use every time.
        for attempt in range(21):
            current = self.devices().get(name)
            if current is None:
                return
            if current['active'] or current['mounted'] or current['used']:
                raise RuntimeError('Área voltou a ser usada; não será resetada.')
            self.device(name)
            try:
                self.write(name, 'reset', 1)
                self.remove_id(name)
                return
            except OSError as error:
                if error.errno != errno.EBUSY or attempt == 20:
                    raise
                time.sleep(.1)


class Memory:
    def __init__(self, backend=None, state=STATE):
        self.backend = backend or Linux()
        self.state = state

    def owned(self):
        if not self.state.exists():
            return None
        data = json.loads(read(self.state))
        if not re.fullmatch(r'zram[0-9]+', str(data.get('device', ''))) or not isinstance(data.get('size'), int):
            raise RuntimeError('Registro de zram inválido. Reinicie para restaurar o estado do firmware.')
        return data

    def status(self):
        total, available = self.backend.memory()
        devices = self.backend.devices()
        owned = self.owned()
        lines = [f'RAM visível: {total // MIB} MiB', f'RAM disponível: {available // MIB} MiB', '']
        for name, dev in devices.items():
            if dev['size']:
                label = 'Doctor' if owned and owned['device'] == name else 'firmware/outro programa'
                lines += [f'{name} ({label}): {dev["size"] // MIB} MiB', f'Swap usada: {dev["used"] // MIB} MiB; ativa: {dev["active"]}',
                          'Compressão: ' + dev['algorithm']]
                if dev.get('memory_used') is not None:
                    lines.append(f'RAM ocupada pelo zram: {dev["memory_used"] // MIB} MiB')
        if not any(d['size'] for d in devices.values()):
            lines.append('Nenhuma área zram configurada.')
        lines += ['', 'Opções calculadas para este aparelho:']
        for percent in (25, 50, 75):
            lines.append(f'{percent}%: {self.size(percent, total) // MIB} MiB' + (' — ponto de partida sugerido' if percent == 50 else ''))
        lines += ['', 'Recomendação principal: mantenha o padrão se não há falta de memória. 50% é uma sugestão conservadora do projeto, não garantia de mais FPS.',
                  'Zram comprime RAM; não cria RAM física. Pode aumentar uso de CPU e consumo. Não escreve swap no cartão.',
                  'Ajustes valem até reiniciar. Não substitui zram do firmware. Para trocar/desativar, a área do Doctor precisa estar sem páginas em uso.',
                  'Se houver páginas em uso, feche jogos e reinicie antes de escolher outro tamanho. Nenhum swapoff forçado ou limpeza de cache é feito.']
        return '\n'.join(lines)

    @staticmethod
    def size(percent, total):
        if percent not in (25, 50, 75) or total < 256 * MIB:
            raise RuntimeError('Tamanho fora das opções conservadoras.')
        return (total * percent // 100 // MIB) * MIB

    def remove_owned(self):
        owned = self.owned()
        if not owned:
            return 'Padrão preservado; nenhuma área criada pelo Doctor neste boot.'
        name = owned['device']
        current = self.backend.devices().get(name)
        if current is None:
            self.state.unlink()
            return 'A área do Doctor já não existe. Registro removido.'
        if current['mounted'] or current['size'] not in (0, owned['size']):
            raise RuntimeError('Dispositivo alterado por outro programa; nada removido. Reinicie o console.')
        total, available = self.backend.memory()
        if current['used'] or available < max(128 * MIB, total // 4):
            raise RuntimeError('Zram em uso ou pouca RAM livre. Não será desativada. Feche jogos e reinicie antes de trocar o tamanho.')
        # Re-check immediately before swapoff. Kernel must confirm deactivation.
        current = self.backend.devices()[name]
        if current['used'] or current['mounted']:
            raise RuntimeError('Uso mudou durante a verificação; operação cancelada.')
        if current['active']:
            self.backend.deactivate(name)
        current = self.backend.devices()[name]
        if current['active'] or current['mounted'] or current['used']:
            raise RuntimeError('Desativação não confirmada; dispositivo preservado.')
        self.backend.remove(name)
        if name in self.backend.devices():
            raise RuntimeError('Remoção não confirmada. Registro mantido.')
        self.state.unlink()
        return 'Área criada pelo Doctor removida. Demais swaps e configuração do firmware preservados.'

    def apply(self, percent):
        total, available = self.backend.memory()
        size = self.size(percent, total)
        if not self.backend.support():
            raise RuntimeError('Kernel sem criação dinâmica de zram. Não vamos substituir a área do firmware.')
        if available < max(128 * MIB, total // 4):
            raise RuntimeError('Pouca RAM disponível para manutenção. Feche os jogos e tente novamente.')
        owned = self.owned()
        devices = self.backend.devices()
        others = [d for n, d in devices.items() if (not owned or n != owned['device']) and (d['size'] or d['active'] or d['mounted'])]
        if others:
            raise RuntimeError('Já existe zram do firmware/outro programa. Mantida sem alterações; recomendamos Padrão do aparelho.')
        if owned:
            current = devices.get(owned['device'])
            if current and current['size'] == size == owned['size'] and current['active']:
                return f'Zram do Doctor já está ativa com {size // MIB} MiB.'
            self.remove_owned()
        devices = self.backend.devices()
        name = self.backend.create()
        if name in devices or not re.fullmatch(r'zram[0-9]+', name):
            raise RuntimeError('Criação não devolveu um dispositivo novo; nada será formatado.')
        fresh = self.backend.devices()[name]
        if fresh['size'] or fresh['active'] or fresh['mounted']:
            raise RuntimeError('Novo dispositivo não está vazio; formatação recusada.')
        save(self.state, {'device': name, 'size': size, 'percent': percent, 'phase': 'preparing'})
        try:
            self.backend.initialize(name, size)
            self.backend.activate(name)
            current = self.backend.devices()[name]
            if not current['active'] or current['size'] != size:
                raise RuntimeError('Ativação não confirmada.')
            save(self.state, {'device': name, 'size': size, 'percent': percent, 'phase': 'active'})
        except Exception:
            # Keep the ownership journal. Never reset if pages may already be in use.
            raise RuntimeError('Zram não concluída. Registro mantido; consulte o estado e use Padrão ou reinicie. Não foi alterada a zram do firmware.')
        return f'Zram do Doctor ativa: {size // MIB} MiB ({percent}% da RAM visível).\nVale até reiniciar. Teste o jogo; não há garantia de ganho de desempenho.'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['status', '25', '50', '75', 'restore'])
    args = parser.parse_args()
    try:
        module = Memory()
        if args.action == 'status':
            print(module.status()); return
        if os.geteuid() != 0:
            raise RuntimeError('Permissão administrativa automática indisponível; nada alterado.')
        if STATE.parent.is_symlink() or STATE.is_symlink():
            raise RuntimeError('Registro de manutenção inseguro.')
        STATE.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        info = STATE.parent.stat()
        if info.st_uid != 0 or info.st_mode & 0o022:
            raise RuntimeError('Permissões do registro inseguras.')
        import fcntl
        lock = STATE.parent / 'lock'
        if lock.is_symlink():
            raise RuntimeError('Trava insegura.')
        with lock.open('a') as stream:
            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
            print(module.remove_owned() if args.action == 'restore' else module.apply(int(args.action)))
    except Exception as error:
        print('Memória: ' + str(error), file=sys.stderr)
        raise SystemExit(1)


if __name__ == '__main__':
    main()
