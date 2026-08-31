#!/usr/bin/env python3
"""Read network addresses and toggle only the NetworkManager Wi-Fi radio.

No password collection, package installation, DTB change, reboot, or global
network shutdown. Unsupported backends remain read-only.
"""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys


def run(arguments, timeout=12):
    try:
        result = subprocess.run(arguments, capture_output=True, text=True, timeout=timeout,
                                env={**os.environ, 'LC_ALL': 'C', 'LANG': 'C'})
        return result.stdout.strip(), result.returncode, result.stderr.strip()
    except (OSError, subprocess.TimeoutExpired) as error:
        return '', 1, str(error)


def nm_active():
    output, code, _ = run(['nmcli', '-t', '-f', 'RUNNING', 'general'])
    return code == 0 and output == 'running'


def wifi_devices(sysroot=Path('/sys/class/net')):
    return sorted(p.name for p in sysroot.glob('*') if (p / 'wireless').exists() or (p / 'phy80211').exists())


def addresses():
    output, code, error = run(['ip', '-j', 'address', 'show'])
    if code:
        return [], 'Não foi possível consultar endereços: ' + error
    try:
        return json.loads(output), ''
    except ValueError:
        return [], 'Esta versão de ip não oferece o formato esperado.'


def status():
    active = nm_active()
    radio, _, _ = run(['nmcli', 'radio', 'wifi']) if active else ('desconhecido', 1, '')
    devices = wifi_devices()
    lines = ['REDE DO CONSOLE', '', 'Gerenciador: ' + ('NetworkManager' if active else 'não suportado para alterações'),
             'Rádio Wi-Fi: ' + {'enabled': 'habilitado', 'disabled': 'desabilitado'}.get(radio, radio),
             'Adaptadores Wi-Fi: ' + (', '.join(devices) or 'nenhum detectado'), '',
             'Rádio habilitado não garante conexão ou acesso à internet.']
    for radio_device in Path('/sys/class/rfkill').glob('rfkill*'):
        try:
            if (radio_device / 'type').read_text().strip() == 'wlan':
                hard = (radio_device / 'hard').read_text().strip() == '1'
                soft = (radio_device / 'soft').read_text().strip() == '1'
                lines += ['Bloqueio Wi-Fi: ' + ('físico (o app não remove)' if hard else ('por software' if soft else 'não'))]
        except OSError:
            pass
    data, error = addresses()
    if error:
        lines += ['', error]
    for interface in data:
        name = interface.get('ifname', '')
        if name == 'lo':
            continue
        lines += ['', name + ' — ' + interface.get('operstate', 'desconhecido'),
                  'MAC: ' + interface.get('address', 'não informado')]
        ips = [f"{item.get('local')}/{item.get('prefixlen')}" for item in interface.get('addr_info', [])]
        lines += ['IP: ' + (', '.join(ips) or 'sem endereço')]
        if active:
            # Never request --show-secrets or connection profiles/passwords.
            connection, code, _ = run(['nmcli', '-g', 'GENERAL.CONNECTION', 'device', 'show', name])
            if code == 0 and connection and connection != '--':
                lines += ['Conexão: ' + connection]
            dns, code, _ = run(['nmcli', '-g', 'IP4.DNS,IP6.DNS', 'device', 'show', name])
            if code == 0 and dns:
                lines += ['DNS: ' + dns.replace('\n', ', ')]
    routes, code, _ = run(['ip', '-j', 'route', 'show', 'default'])
    if code == 0:
        try:
            for route in json.loads(routes):
                lines += ['', 'Gateway: ' + route.get('gateway', 'direto') + ' em ' + route.get('dev', '?')]
        except ValueError:
            pass
    if not devices:
        lines += ['', 'No modo USB por cabo, o dongle Wi-Fi da porta OTG pode ficar indisponível. '
                  'Para voltar ao dongle, use USB / OTG > Restaurar USB e Wi-Fi (reinicia). '
                  'Ligar o rádio aqui não altera esse modo.']
    lines += ['', 'Para cadastrar uma nova rede/senha, use as opções de rede do firmware. '
              'Este módulo preserva as conexões já salvas.']
    return '\n'.join(lines)


def toggle(enabled):
    if not nm_active():
        raise ValueError('NetworkManager não está ativo. Firmware não suportado para esta alteração; nenhuma mudança aplicada.')
    desired = 'enabled' if enabled else 'disabled'
    _, code, error = run(['nmcli', '--wait', '10', 'radio', 'wifi', 'on' if enabled else 'off'])
    if code:
        raise ValueError('Não foi possível mudar o rádio Wi-Fi: ' + error)
    actual, code, error = run(['nmcli', 'radio', 'wifi'])
    if code or actual != desired:
        raise ValueError('Não foi possível confirmar o novo estado do rádio. Consulte as informações de rede. ' + error)
    prefix = 'Wi-Fi habilitado.' if enabled else 'Wi-Fi desabilitado.'
    return prefix + '\nUSB/Ethernet, redes salvas e DTB não foram alterados.\n\n' + status()


def main():
    action = sys.argv[1] if len(sys.argv) > 1 else 'status'
    try:
        if action not in ('status', 'on', 'off'):
            raise ValueError('Ação inválida.')
        # Escalate only the radio command, never a user-supplied path or arbitrary command.
        if action != 'status' and os.geteuid() != 0:
            if not shutil.which('sudo'):
                raise ValueError('Sem permissão para alterar o rádio; sudo indisponível.')
            result = subprocess.run(['sudo', '-n', sys.executable, str(Path(__file__).resolve()), action], timeout=45)
            raise SystemExit(result.returncode)
        print(status() if action == 'status' else toggle(action == 'on'))
    except (ValueError, subprocess.TimeoutExpired) as error:
        print(str(error))
        raise SystemExit(1)


if __name__ == '__main__':
    main()
