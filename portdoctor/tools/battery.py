#!/usr/bin/env python3
"""Battery readings and reversible, boot-local brightness/governor adjustments.

Never writes to power_supply, charging limits, clock limits, voltage or firmware.
"""
import argparse
import json
import math
import os
from pathlib import Path
import re
import sys


SYS = Path('/sys')
STATE = Path('/run/portdoctor-battery/state.json')


def read(path):
    try:
        return path.read_text().strip()
    except OSError:
        return ''


def number(value):
    try:
        return int(value)
    except (ValueError, TypeError):
        return None


def controls(root=SYS):
    result = {}
    for base in sorted((root / 'class/backlight').glob('*')):
        maximum = number(read(base / 'max_brightness'))
        current = number(read(base / 'brightness'))
        if maximum and current is not None and 0 <= current <= maximum:
            result[str(base / 'brightness')] = {'kind': 'brightness', 'value': str(current), 'maximum': maximum}
    for base in sorted((root / 'devices/system/cpu/cpufreq').glob('policy[0-9]*')):
        governors = read(base / 'scaling_available_governors').split()
        current = read(base / 'scaling_governor')
        if current in governors:
            result[str(base / 'scaling_governor')] = {'kind': 'governor', 'value': current, 'available': governors}
    return result


def performance_guard(root=SYS):
    compatible = read(root / 'firmware/devicetree/base/compatible').split('\x00')
    if 'rockchip,rk3326' not in compatible:
        raise RuntimeError('Desempenho não validado neste SoC. Use Padrão ou Equilibrado.')
    temps = []
    for sensor in (root / 'class/thermal').glob('thermal_zone*'):
        value = number(read(sensor / 'temp'))
        if value is not None and 0 < value < 150000:
            temps.append(value)
    # Conservative application policy, NOT a manufacturer temperature rating.
    if not temps or max(temps) >= 65000:
        raise RuntimeError('Desempenho bloqueado: sensor ausente ou temperatura a partir de 65 °C. Deixe o aparelho esfriar.')
    for base in (root / 'devices/system/cpu/cpufreq').glob('policy[0-9]*'):
        maximum = number(read(base / 'scaling_max_freq'))
        if maximum is None or maximum > 1512000:
            raise RuntimeError('Limite de frequência não reconhecido ou acima de 1,512 GHz; não aplicaremos desempenho.')
    for base in (root / 'class/power_supply').glob('*'):
        if read(base / 'type').lower() == 'battery':
            charge = number(read(base / 'capacity'))
            if charge is not None and charge < 20:
                raise RuntimeError('Desempenho bloqueado com carga abaixo de 20%.')


def status(root=SYS):
    lines = ['BATERIA — leitura do aparelho', '']
    found = False
    names = {'Discharging': 'descarregando', 'Charging': 'carregando', 'Full': 'carregada',
             'Not charging': 'sem carregamento', 'Unknown': 'não informado', 'Good': 'normal'}
    for base in sorted((root / 'class/power_supply').glob('*')):
        if read(base / 'type').lower() != 'battery' and base.name.lower() != 'battery':
            continue
        found = True
        data = {}
        for line in read(base / 'uevent').splitlines():
            key, sep, value = line.partition('=')
            if sep:
                data[key.removeprefix('POWER_SUPPLY_').lower()] = value
        def value(key):
            return read(base / key) or data.get(key, '')
        cap = number(value('capacity'))
        lines += [f'Sensor: {base.name}', f'Carga: {cap}%' if cap is not None and 0 <= cap <= 100 else 'Carga: não informada',
                  'Estado: ' + names.get(value('status'), value('status') or 'não informado')]
        for key, label, scale, unit in [('voltage_now','Tensão',1000000,'V'),('current_now','Corrente',1000,'mA'),('temp','Temperatura',10,'°C')]:
            raw = number(value(key))
            lines.append(f'{label}: {raw / scale:.2f} {unit}' if raw is not None else f'{label}: não informada')
        voltage, current = number(value('voltage_now')), number(value('current_now'))
        if voltage and current is not None:
            lines.append(f'Consumo instantâneo estimado: {abs(voltage * current) / 1e12:.2f} W')
        lines += ['Saúde reportada: ' + names.get(value('health'), value('health') or 'não informada'), '']
    if not found:
        lines.append('Esta imagem não expõe um sensor de bateria compatível.')
    for path, control in controls(root).items():
        if control['kind'] == 'brightness':
            lines.append(f'Brilho: {round(int(control["value"]) * 100 / control["maximum"])}%')
        else:
            lines.append('Modo da CPU: ' + control['value'])
            base = Path(path).parent
            for name, label in [('scaling_cur_freq', 'Frequência solicitada'), ('scaling_max_freq', 'Limite atual')]:
                freq = number(read(base / name))
                if freq is not None:
                    lines.append(f'{label}: {freq / 1000:.0f} MHz')
    for sensor in sorted((root / 'class/thermal').glob('thermal_zone*')):
        temp = number(read(sensor / 'temp'))
        if temp is not None:
            lines.append(f'{read(sensor / "type") or sensor.name}: {temp / 1000:.1f} °C')
    lines += ['', 'Y na página Bateria atualiza as leituras.',
              'Porcentagem e saúde vêm do firmware; não medem o desgaste real. Não é feita calibração nem alteração do carregamento.',
              'Perfis valem neste boot. Um jogo ou o firmware pode substituir os ajustes. Pode haver redução de desempenho.',
              'Não há overclock: nenhum limite de frequência, tensão ou proteção térmica é alterado. O bloqueio de 65 °C é preventivo na ativação, não um monitor contínuo nem limite certificado do fabricante.']
    return '\n'.join(lines)


def checked_write(path, value):
    # sysfs attributes cannot be replaced with rename/atomic_write.
    with Path(path).open('w') as stream:
        stream.write(str(value) + '\n')
    if read(Path(path)) != str(value):
        raise RuntimeError('O aparelho não confirmou a gravação: ' + str(path))


def load_state(path):
    if not path.exists():
        return {}
    data = json.loads(path.read_text())
    if not isinstance(data, dict):
        raise RuntimeError('Registro de restauração inválido; nenhuma alteração aplicada.')
    return data


def save_state(path, data):
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    temporary = path.with_suffix('.tmp')
    with temporary.open('w') as stream:
        json.dump(data, stream)
        stream.flush()
        os.fsync(stream.fileno())
    os.chmod(temporary, 0o600)
    temporary.replace(path)


def adjust(action, root=SYS, state_path=STATE, writer=checked_write):
    if action not in ('restore', 'balanced', 'performance', 'economy', 'brighter', 'dimmer'):
        raise RuntimeError('Perfil desconhecido; nenhuma alteração.')
    if action == 'performance':
        performance_guard(root)
    available = controls(root)
    saved = load_state(state_path)
    planned = {}
    skipped = []
    for path, control in available.items():
        current = control['value']
        if action == 'restore':
            entry = saved.get(path)
            if not isinstance(entry, dict):
                continue
            if current != entry.get('applied'):
                skipped.append(path)
                continue
            target = str(entry.get('original', ''))
        elif control['kind'] == 'brightness':
            if action in ('balanced', 'performance'):
                continue
            maximum = control['maximum']
            minimum = max(1, math.ceil(maximum * .15))
            if action == 'economy':
                target = str(min(int(current), max(minimum, round(maximum * .30))))
            else:
                delta = max(1, round(maximum * .10)) * (1 if action == 'brighter' else -1)
                target = str(max(minimum, min(maximum, int(current) + delta)))
        elif action in ('economy', 'balanced', 'performance'):
            preferences = {'economy': ['conservative'], 'balanced': ['ondemand', 'schedutil', 'interactive'], 'performance': ['performance']}
            target = next((g for g in preferences[action] if g in control['available']), None)
            if target is None:
                if action != 'economy':
                    raise RuntimeError('Perfil não suportado por este kernel; nada alterado.')
                continue
        else:
            continue
        if control['kind'] == 'brightness':
            target_number = number(target)
            if target_number is None or not 0 < target_number <= control['maximum']:
                raise RuntimeError('Valor de brilho salvo fora do intervalo; restauração recusada.')
        elif target not in control['available']:
            raise RuntimeError('Modo salvo não é suportado por este kernel.')
        if target != current:
            planned[path] = (current, target)
    if not planned:
        if skipped:
            raise RuntimeError('O firmware ou outro programa mudou os ajustes. Nada foi sobrescrito; ajuste o brilho pelo menu do aparelho.')
        return 'Nenhuma mudança necessária ou controle compatível disponível.'
    previous = json.loads(json.dumps(saved))
    for path, (current, target) in planned.items():
        if action != 'restore':
            saved.setdefault(path, {'original': current})
            saved[path]['applied'] = target
    # Journal is durable before any hardware writes.
    save_state(state_path, saved)
    attempted = []
    try:
        for path, (current, target) in planned.items():
            attempted.append((path, current))
            writer(path, target)
    except (OSError, RuntimeError) as error:
        rollback_errors = []
        for path, current in reversed(attempted):
            try:
                writer(path, current)
            except (OSError, RuntimeError):
                rollback_errors.append(path)
        if not rollback_errors:
            save_state(state_path, previous)
        raise RuntimeError(str(error) + ('; restauração incompleta: ' + ', '.join(rollback_errors) if rollback_errors else '; ajustes anteriores restaurados.'))
    if action == 'restore':
        for path in planned:
            saved.pop(path, None)
        save_state(state_path, saved)
    lines = [f'Ajustes gravados e confirmados: {len(planned)}.']
    for path, (current, target) in planned.items():
        label = 'Brilho (escala do aparelho)' if available[path]['kind'] == 'brightness' else 'Modo CPU'
        lines.append(f'{label}: {current} → {target}')
    if skipped:
        lines.append('Alguns ajustes foram alterados externamente e foram preservados.')
    lines.append('Não altera tensão, carregamento, USB, Wi-Fi ou arquivos de inicialização.')
    return '\n'.join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['status', 'balanced', 'performance', 'economy', 'brighter', 'dimmer', 'restore'])
    args = parser.parse_args()
    try:
        if args.action == 'status':
            print(status()); return
        if not hasattr(os, 'geteuid') or os.geteuid() != 0:
            raise RuntimeError('Sem permissão automática. Nenhum ajuste aplicado; verifique o suporte sudo da imagem.')
        # Never accept a state directory owned by an unprivileged caller.
        if STATE.parent.is_symlink() or STATE.is_symlink():
            raise RuntimeError('Caminho de restauração inseguro.')
        if STATE.parent.exists() and (STATE.parent.stat().st_uid != 0 or STATE.parent.stat().st_mode & 0o022):
            raise RuntimeError('Permissões inseguras no registro de restauração.')
        import fcntl
        STATE.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        lock_path=STATE.parent / 'lock'
        if lock_path.is_symlink():
            raise RuntimeError('Trava de manutenção insegura.')
        with lock_path.open('a') as lock:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise RuntimeError('Já existe uma alteração de bateria em andamento.')
            print(adjust(args.action))
    except (OSError, ValueError, RuntimeError) as error:
        print('Bateria: ' + str(error), file=sys.stderr)
        raise SystemExit(1)


if __name__ == '__main__':
    main()
