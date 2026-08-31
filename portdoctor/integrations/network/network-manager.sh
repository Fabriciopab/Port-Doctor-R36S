#!/bin/bash

# Jogos em Rede R36S
# dArkOSRE / ArkOS - gerenciador SMB para a pasta Tools
# Creditos: Fabricio Bastos - https://github.com/Fabriciopab

VERSION="1.0.1-portdoctor"
TTY_DEVICE="/dev/tty1"
SCRIPT_PATH="$(readlink -f "$0" 2>/dev/null || printf '%s' "$0")"
SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$SCRIPT_PATH")" 2>/dev/null && pwd)"
PORTDOCTOR_HOME="${PORTDOCTOR_HOME:-$(CDPATH= cd -- "$SCRIPT_DIR/../.." 2>/dev/null && pwd)}"
IMPORT_CONFIG=""
for CONFIG_CANDIDATE in \
    "$PORTDOCTOR_HOME/conf/Jogos-em-Rede-R36S.conf" \
    "/roms/tools/Jogos-em-Rede-R36S.conf" \
    "/roms2/tools/Jogos-em-Rede-R36S.conf" \
    "$SCRIPT_DIR/Jogos-em-Rede-R36S.conf"; do
    if [ -f "$CONFIG_CANDIDATE" ]; then
        IMPORT_CONFIG="$CONFIG_CANDIDATE"
        break
    fi
done
[ -n "$IMPORT_CONFIG" ] || IMPORT_CONFIG="$PORTDOCTOR_HOME/conf/Jogos-em-Rede-R36S.conf"
STATE_DIR="/etc/r36s-network"
SYSTEM_CONFIG="$STATE_DIR/config"
CREDENTIALS_FILE="$STATE_DIR/credentials"
BIND_LIST="$STATE_DIR/binds.list"
LOG_FILE="/var/log/r36s-network.log"
REPORT_FILE="$PORTDOCTOR_HOME/conf/reports/Jogos-em-Rede-R36S-diagnostico.txt"
MOUNT_ROOT="/mnt/r36s-jogos"
ES_CONFIG="/etc/emulationstation/es_systems.cfg"
MAPPER_PID=""
UI_READY="no"

if [ "$(id -u)" -ne 0 ]; then
    if command -v sudo >/dev/null 2>&1; then
        exec sudo -E /bin/bash "$SCRIPT_PATH" "$@"
    fi
    printf '\nEste script precisa de permissao administrativa.\n' > "$TTY_DEVICE" 2>/dev/null
    exit 1
fi

umask 077
mkdir -p "$STATE_DIR" "$MOUNT_ROOT"
mkdir -p "$(dirname -- "$REPORT_FILE")"
touch "$LOG_FILE"
chmod 600 "$LOG_FILE" 2>/dev/null

timestamp() {
    date '+%Y-%m-%d %H:%M:%S'
}

log_line() {
    printf '[%s] %s\n' "$(timestamp)" "$*" >> "$LOG_FILE"
}

cleanup_ui() {
    if [ -n "$MAPPER_PID" ]; then
        kill "$MAPPER_PID" >/dev/null 2>&1
        wait "$MAPPER_PID" >/dev/null 2>&1
        MAPPER_PID=""
    fi
    if [ "$UI_READY" = "yes" ]; then
        printf '\e[?25h\033c' > "$TTY_DEVICE" 2>/dev/null
    fi
    UI_READY="no"
}

if [ $# -eq 0 ]; then
    trap cleanup_ui EXIT INT TERM
fi

setup_ui() {
    chmod 666 "$TTY_DEVICE" 2>/dev/null
    chmod 666 /dev/uinput 2>/dev/null
    export TERM=linux
    export DIALOGRC=/opt/inttools/noshadows.dialogrc
    export SDL_GAMECONTROLLERCONFIG_FILE=/opt/inttools/gamecontrollerdb.txt
    export XDG_RUNTIME_DIR="/run/user/$(id -u ark 2>/dev/null || printf '1000')"

    if [ -f /usr/share/consolefonts/Lat7-TerminusBold20x10.psf.gz ]; then
        setfont /usr/share/consolefonts/Lat7-TerminusBold20x10.psf.gz >/dev/null 2>&1
    elif [ -f /usr/share/consolefonts/Lat7-Terminus16.psf.gz ]; then
        setfont /usr/share/consolefonts/Lat7-Terminus16.psf.gz >/dev/null 2>&1
    fi

    if ! pgrep -f '[g]ptokeyb' >/dev/null 2>&1 && ! pgrep -f '[o]ga_controls' >/dev/null 2>&1; then
        if [ -x /opt/inttools/gptokeyb ] && [ -f /opt/inttools/keys.gptk ]; then
            /opt/inttools/gptokeyb -1 dialog -c /opt/inttools/keys.gptk >/dev/null 2>&1 &
            MAPPER_PID=$!
        fi
    fi

    printf '\033c\e[?25l' > "$TTY_DEVICE" 2>/dev/null
    UI_READY="yes"
}

show_message() {
    local title="$1"
    local message="$2"
    if [ "$UI_READY" = "yes" ] && command -v dialog >/dev/null 2>&1; then
        dialog --clear --title "$title" --msgbox "$message" 18 58 < "$TTY_DEVICE" > "$TTY_DEVICE" 2> "$TTY_DEVICE"
    else
        printf '\n%s\n\n%b\n' "$title" "$message"
    fi
}

ask_yes_no() {
    local title="$1"
    local message="$2"
    dialog --clear --title "$title" --yesno "$message" 18 58 < "$TTY_DEVICE" > "$TTY_DEVICE" 2> "$TTY_DEVICE"
}

show_text_file() {
    local title="$1"
    local file="$2"
    dialog --clear --title "$title" --textbox "$file" 21 62 < "$TTY_DEVICE" > "$TTY_DEVICE" 2> "$TTY_DEVICE"
}

read_value() {
    local key="$1"
    local file="$2"
    sed -n "s/^${key}=//p" "$file" 2>/dev/null | head -n 1 | tr -d '\r'
}

valid_simple_value() {
    local value="$1"
    [ -n "$value" ] || return 1
    case "$value" in
        *[!A-Za-z0-9._:-]*) return 1 ;;
    esac
    return 0
}

valid_share_name() {
    local value="$1"
    [ -n "$value" ] || return 1
    case "$value" in
        *[!A-Za-z0-9_-]*) return 1 ;;
    esac
    return 0
}

import_configuration() {
    local server share user domain smb_version password_b64 password tmp_file

    if [ ! -f "$IMPORT_CONFIG" ]; then
        show_message "Configuracao ausente" "Nao encontrei:\n\n$IMPORT_CONFIG\n\nExecute primeiro o preparador no Windows e copie o arquivo .conf para a pasta tools."
        return 1
    fi

    server="$(read_value SERVIDOR "$IMPORT_CONFIG")"
    share="$(read_value COMPARTILHAMENTO "$IMPORT_CONFIG")"
    user="$(read_value USUARIO "$IMPORT_CONFIG")"
    domain="$(read_value DOMINIO "$IMPORT_CONFIG")"
    smb_version="$(read_value VERSAO_SMB "$IMPORT_CONFIG")"
    password_b64="$(read_value SENHA_BASE64 "$IMPORT_CONFIG")"

    valid_simple_value "$server" || {
        show_message "Configuracao invalida" "O campo SERVIDOR esta vazio ou possui caracteres invalidos. Gere novamente o arquivo no Windows."
        return 1
    }
    valid_share_name "$share" || {
        show_message "Configuracao invalida" "O nome do compartilhamento e invalido. Gere novamente o arquivo no Windows."
        return 1
    }
    valid_simple_value "$user" || {
        show_message "Configuracao invalida" "O campo USUARIO e invalido. Gere novamente o arquivo no Windows."
        return 1
    }
    valid_simple_value "$domain" || {
        show_message "Configuracao invalida" "O campo DOMINIO e invalido. Gere novamente o arquivo no Windows."
        return 1
    }
    case "$smb_version" in
        3.1.1|3.0|2.1|2.0) ;;
        *) smb_version="3.0" ;;
    esac
    if [ -z "$password_b64" ] || [ "$password_b64" = "IMPORTADA_E_REMOVIDA" ]; then
        show_message "Senha ja importada" "Este arquivo .conf nao contem mais a senha.\n\nSe quiser trocar o computador ou a senha, execute novamente o preparador no Windows e copie o novo .conf para tools."
        return 1
    fi
    if ! command -v base64 >/dev/null 2>&1; then
        show_message "Componente ausente" "O comando base64 nao esta instalado neste sistema."
        return 1
    fi

    password="$(printf '%s' "$password_b64" | base64 -d 2>/dev/null)" || password=""
    if [ -z "$password" ]; then
        show_message "Senha invalida" "Nao foi possivel ler a senha do arquivo .conf. Gere novamente no Windows."
        return 1
    fi

    mkdir -p "$STATE_DIR"
    chmod 700 "$STATE_DIR"
    {
        printf 'SERVIDOR=%s\n' "$server"
        printf 'COMPARTILHAMENTO=%s\n' "$share"
        printf 'USUARIO=%s\n' "$user"
        printf 'DOMINIO=%s\n' "$domain"
        printf 'VERSAO_SMB=%s\n' "$smb_version"
    } > "$SYSTEM_CONFIG"
    {
        printf 'username=%s\n' "$user"
        printf 'password=%s\n' "$password"
        printf 'domain=%s\n' "$domain"
    } > "$CREDENTIALS_FILE"
    chmod 600 "$SYSTEM_CONFIG" "$CREDENTIALS_FILE"
    password=""

    tmp_file="${IMPORT_CONFIG}.tmp.$$"
    sed 's/^SENHA_BASE64=.*/SENHA_BASE64=IMPORTADA_E_REMOVIDA/' "$IMPORT_CONFIG" > "$tmp_file" && mv -f "$tmp_file" "$IMPORT_CONFIG"
    rm -f "$tmp_file" 2>/dev/null

    log_line "Configuracao importada para servidor $server, compartilhamento $share."
    show_message "Configuracao importada" "A configuracao foi guardada no sistema.\n\nA senha foi removida do arquivo que fica na pasta tools."
    return 0
}

load_configuration() {
    if [ ! -r "$SYSTEM_CONFIG" ] || [ ! -r "$CREDENTIALS_FILE" ]; then
        return 1
    fi
    SERVER="$(read_value SERVIDOR "$SYSTEM_CONFIG")"
    SHARE="$(read_value COMPARTILHAMENTO "$SYSTEM_CONFIG")"
    USER_NAME="$(read_value USUARIO "$SYSTEM_CONFIG")"
    DOMAIN_NAME="$(read_value DOMINIO "$SYSTEM_CONFIG")"
    SMB_VERSION="$(read_value VERSAO_SMB "$SYSTEM_CONFIG")"
    valid_simple_value "$SERVER" && valid_share_name "$SHARE" && valid_simple_value "$USER_NAME" && valid_simple_value "$DOMAIN_NAME"
}

cifs_is_mounted() {
    awk -v point="$MOUNT_ROOT" '$2 == point && $3 == "cifs" { found=1 } END { exit !found }' /proc/mounts 2>/dev/null
}

path_is_mounted() {
    local path="$1"
    if command -v mountpoint >/dev/null 2>&1; then
        mountpoint -q "$path"
    else
        awk -v point="$path" '$2 == point { found=1 } END { exit !found }' /proc/mounts 2>/dev/null
    fi
}

check_cifs_support() {
    if ! command -v mount.cifs >/dev/null 2>&1 && [ ! -x /sbin/mount.cifs ] && [ ! -x /usr/sbin/mount.cifs ]; then
        return 1
    fi
    if ! grep -qw cifs /proc/filesystems 2>/dev/null; then
        modprobe cifs >> "$LOG_FILE" 2>&1
    fi
    grep -qw cifs /proc/filesystems 2>/dev/null || [ -d /sys/module/cifs ]
}

unmount_bind_folders() {
    local target remaining failures
    remaining="${BIND_LIST}.remaining.$$"
    failures=0
    : > "$remaining"
    if [ -f "$BIND_LIST" ]; then
        while IFS= read -r target; do
            [ -n "$target" ] || continue
            if path_is_mounted "$target"; then
                if ! umount "$target" >> "$LOG_FILE" 2>&1; then
                    log_line "Nao foi possivel desmontar $target."
                    printf '%s\n' "$target" >> "$remaining"
                    failures=$((failures + 1))
                    continue
                fi
            fi
            rmdir "$target" >/dev/null 2>&1 || true
        done < "$BIND_LIST"
    fi
    mv -f "$remaining" "$BIND_LIST"
    [ "$failures" -eq 0 ]
}

extract_system_paths() {
    local cfg
    for cfg in "$ES_CONFIG" /home/ark/.emulationstation/es_systems.cfg; do
        [ -r "$cfg" ] || continue
        sed -n 's:.*<path>[[:space:]]*\([^<]*\)[[:space:]]*</path>.*:\1:p' "$cfg"
    done | sed 's/[[:space:]]*$//' | sort -u
}

bind_network_systems() {
    local remote_root system_path system_name remote_path target temp_list
    local count=0 ignored=0

    remote_root="$MOUNT_ROOT"
    if [ -d "$MOUNT_ROOT/roms" ]; then
        remote_root="$MOUNT_ROOT/roms"
    fi

    if ! unmount_bind_folders; then
        log_line "Ainda existem pastas Rede em uso; conexao cancelada."
        return 1
    fi
    temp_list="${BIND_LIST}.tmp.$$"
    : > "$temp_list"

    while IFS= read -r system_path; do
        case "$system_path" in
            /roms/*|/roms2/*) ;;
            *) continue ;;
        esac
        [ -d "$system_path" ] || continue
        system_name="$(basename "$system_path")"
        case "$system_name" in
            tools|ports|bios|themes|bgmusic|movies|splashscreens|backup|ports_scripts) continue ;;
        esac

        remote_path="$remote_root/$system_name"
        if [ ! -d "$remote_path" ]; then
            ignored=$((ignored + 1))
            continue
        fi

        target="$system_path/Rede"
        if [ -e "$target" ] && [ ! -d "$target" ]; then
            log_line "Ignorado: $target existe e nao e uma pasta."
            continue
        fi
        mkdir -p "$target"
        if mount --bind "$remote_path" "$target" >> "$LOG_FILE" 2>&1; then
            printf '%s\n' "$target" >> "$temp_list"
            count=$((count + 1))
            log_line "Pasta ligada: $remote_path -> $target"
        else
            log_line "Falha ao ligar $remote_path em $target."
            rmdir "$target" >/dev/null 2>&1 || true
        fi
    done <<EOF
$(extract_system_paths)
EOF

    mv -f "$temp_list" "$BIND_LIST"
    BIND_COUNT="$count"
    IGNORED_COUNT="$ignored"
    [ "$count" -gt 0 ]
}

mount_windows_share() {
    local version tried versions mount_error uid_value gid_value
    uid_value="$(id -u ark 2>/dev/null || printf '1000')"
    gid_value="$(id -g ark 2>/dev/null || printf '1000')"
    mount_error="${STATE_DIR}/ultimo-erro-montagem.txt"
    : > "$mount_error"

    versions="$SMB_VERSION 3.0 2.1"
    tried=" "
    for version in $versions; do
        case "$tried" in *" $version "*) continue ;; esac
        tried="$tried$version "
        log_line "Tentando SMB $version em //$SERVER/$SHARE."
        if mount -t cifs "//$SERVER/$SHARE" "$MOUNT_ROOT" \
            -o "credentials=$CREDENTIALS_FILE,vers=$version,sec=ntlmssp,rw,noperm,noserverino,nosuid,nodev,iocharset=utf8,uid=$uid_value,gid=$gid_value,file_mode=0666,dir_mode=0777,cache=strict" \
            2> "$mount_error"; then
            SMB_VERSION_ACTIVE="$version"
            log_line "Compartilhamento montado com SMB $version."
            return 0
        fi
        sed 's/^/  /' "$mount_error" >> "$LOG_FILE"
    done
    return 1
}

connect_games() {
    if ! load_configuration; then
        show_message "Sem configuracao" "Ainda nao existe uma configuracao valida.\n\nCopie o arquivo .conf gerado no Windows para tools e escolha Importar configuracao."
        return 1
    fi
    if ! check_cifs_support; then
        generate_diagnostic
        show_message "Suporte SMB ausente" "O R36S ainda nao possui mount.cifs ou o driver CIFS.\n\nUse a opcao Instalar suporte SMB. Se continuar falhando, envie o diagnostico criado em tools."
        return 1
    fi

    mkdir -p "$MOUNT_ROOT"
    if cifs_is_mounted; then
        log_line "O compartilhamento ja estava montado; recriando atalhos Rede."
    elif ! mount_windows_share; then
        generate_diagnostic
        show_message "Falha na conexao" "Nao consegui abrir:\n//$SERVER/$SHARE\n\nConfira se o PC esta ligado, na mesma rede e com a pasta compartilhada.\n\nUm diagnostico foi salvo na pasta tools."
        return 1
    fi

    if ! bind_network_systems; then
        show_message "Nenhuma pasta encontrada" "A rede foi aberta, mas nenhuma pasta combina com os sistemas do R36S.\n\nNa pasta do Windows use nomes como:\nnes, snes, gba, megadrive, psx, psp."
        return 1
    fi

    log_line "$BIND_COUNT sistemas conectados."
    show_message "Jogos conectados" "$BIND_COUNT sistema(s) da rede foram adicionados.\n\nEles aparecerao dentro da pasta Rede de cada console.\n\nO menu de jogos sera reiniciado agora."
    return 0
}

disconnect_games() {
    if ! unmount_bind_folders; then
        show_message "Nao foi possivel desconectar" "Algum jogo ou emulador ainda esta usando uma pasta Rede. Feche o jogo e tente novamente."
        return 1
    fi
    if cifs_is_mounted; then
        if ! umount "$MOUNT_ROOT" >> "$LOG_FILE" 2>&1; then
            show_message "Nao foi possivel desconectar" "Algum jogo ou emulador ainda esta usando a pasta da rede. Feche o jogo e tente novamente."
            return 1
        fi
    fi
    log_line "Jogos em rede desconectados."
    show_message "Jogos desconectados" "As pastas Rede foram removidas do menu.\n\nNenhum jogo do Windows foi apagado. O menu sera reiniciado agora."
    return 0
}

generate_diagnostic() {
    local server_text share_text port445 cifs_helper
    server_text="nao configurado"
    share_text="nao configurado"
    port445="nao testado"
    cifs_helper="nao encontrado"
    if command -v mount.cifs >/dev/null 2>&1; then
        cifs_helper="$(command -v mount.cifs)"
    elif [ -x /sbin/mount.cifs ]; then
        cifs_helper="/sbin/mount.cifs"
    elif [ -x /usr/sbin/mount.cifs ]; then
        cifs_helper="/usr/sbin/mount.cifs"
    fi
    if load_configuration; then
        server_text="$SERVER"
        share_text="$SHARE"
        if command -v timeout >/dev/null 2>&1 && timeout 3 bash -c "</dev/tcp/$SERVER/445" >/dev/null 2>&1; then
            port445="aberta"
        else
            port445="fechada ou inacessivel"
        fi
    fi

    {
        printf '============================================================\n'
        printf 'Diagnostico Jogos em Rede R36S\n'
        printf 'Versao do script: %s\n' "$VERSION"
        printf 'Data: %s\n' "$(date)"
        printf '============================================================\n\n'
        printf '1. Sistema\n'
        uname -a
        grep -E '^(PRETTY_NAME|VERSION_ID)=' /etc/os-release 2>/dev/null || true
        printf '\n2. Configuracao (sem senha)\n'
        printf 'Servidor: %s\n' "$server_text"
        printf 'Compartilhamento: %s\n' "$share_text"
        printf 'Ponto de montagem: %s\n' "$MOUNT_ROOT"
        printf '\n3. Rede local\n'
        ip -4 address 2>&1 || true
        printf '\nRotas:\n'
        ip -4 route 2>&1 || true
        if [ "$server_text" != "nao configurado" ]; then
            printf '\nPing para o Windows:\n'
            ping -c 1 -W 2 "$server_text" 2>&1 || true
        fi
        printf '\nPorta SMB 445: %s\n' "$port445"
        printf '\n4. Suporte SMB/CIFS\n'
        printf 'mount.cifs: %s\n' "$cifs_helper"
        printf 'Driver CIFS listado: '
        if grep -qw cifs /proc/filesystems 2>/dev/null || [ -d /sys/module/cifs ]; then printf 'sim\n'; else printf 'nao\n'; fi
        modinfo cifs 2>&1 | head -n 12 || true
        printf '\n5. Montagens atuais\n'
        mount | grep -E '(/mnt/r36s-jogos|/Rede| type cifs)' || printf 'Nenhuma montagem de jogos em rede.\n'
        printf '\n6. Pastas reconhecidas pelo EmulationStation\n'
        extract_system_paths
        printf '\n7. Ultimo erro de montagem\n'
        if [ -s "$STATE_DIR/ultimo-erro-montagem.txt" ]; then
            cat "$STATE_DIR/ultimo-erro-montagem.txt"
        else
            printf 'Nenhum erro registrado.\n'
        fi
        printf '\n8. Mensagens recentes do kernel\n'
        dmesg 2>&1 | grep -Ei 'cifs|smb|wlan|network|usb' | tail -n 80 || true
        printf '\n9. Log do projeto\n'
        tail -n 100 "$LOG_FILE" 2>/dev/null || true
    } > "$REPORT_FILE" 2>&1
    chmod 666 "$REPORT_FILE" 2>/dev/null
    log_line "Diagnostico gerado em $REPORT_FILE."
}

show_status() {
    local status_text binds_count
    status_text="Desconectado"
    if cifs_is_mounted; then status_text="Conectado"; fi
    binds_count="0"
    if [ -f "$BIND_LIST" ]; then
        binds_count="$(grep -c '^/' "$BIND_LIST" 2>/dev/null || printf '0')"
    fi
    if load_configuration; then
        show_message "Estado da rede" "Estado: $status_text\nServidor: $SERVER\nPasta: $SHARE\nSistemas ligados: $binds_count\n\nVersao: $VERSION\nCreditos: Fabricio Bastos"
    else
        show_message "Estado da rede" "Estado: $status_text\nConfiguracao: nao importada\nSistemas ligados: $binds_count\n\nVersao: $VERSION\nCreditos: Fabricio Bastos"
    fi
}

install_smb_support() {
    if ! command -v apt-get >/dev/null 2>&1; then
        show_message "Instalacao indisponivel" "Este sistema nao possui o instalador de pacotes apt-get. Gere o diagnostico e envie o arquivo."
        return 1
    fi
    if ! ask_yes_no "Instalar suporte SMB" "Esta etapa precisa de internet apenas uma vez.\n\nO R36S instalara o pacote cifs-utils do Debian.\n\nDeseja continuar?"; then
        return 1
    fi
    dialog --clear --title "Instalando" --infobox "Atualizando a lista de pacotes...\nIsto pode levar alguns minutos." 8 50 < "$TTY_DEVICE" > "$TTY_DEVICE" 2> "$TTY_DEVICE"
    log_line "Inicio da instalacao de cifs-utils."
    if apt-get update >> "$LOG_FILE" 2>&1 && DEBIAN_FRONTEND=noninteractive apt-get install -y cifs-utils >> "$LOG_FILE" 2>&1; then
        modprobe cifs >> "$LOG_FILE" 2>&1 || true
        if check_cifs_support; then
            show_message "Instalacao concluida" "O suporte SMB foi instalado. Agora escolha Conectar jogos."
            return 0
        fi
        generate_diagnostic
        show_message "Driver ausente" "O programa SMB foi instalado, mas este kernel nao possui o driver CIFS.\n\nEnvie o diagnostico salvo em tools para prepararmos a proxima etapa."
        return 1
    fi
    generate_diagnostic
    show_message "Falha na instalacao" "Nao foi possivel instalar cifs-utils.\n\nConfira a internet e tente novamente. O diagnostico foi salvo em tools."
    return 1
}

restart_emulationstation_and_exit() {
    cleanup_ui
    trap - EXIT INT TERM
    (sleep 1; systemctl restart emulationstation >/dev/null 2>&1) &
    exit 0
}

main_menu() {
    local choice
    while true; do
        choice="$(dialog --clear --stdout --backtitle "Jogos em Rede R36S v$VERSION - Fabricio Bastos" \
            --title "Menu principal" \
            --menu "Use o direcional e o botao A." 20 60 8 \
            1 "Conectar jogos do Windows" \
            2 "Desconectar jogos da rede" \
            3 "Ver estado da conexao" \
            4 "Importar nova configuracao" \
            5 "Criar e ver diagnostico" \
            6 "Instalar suporte SMB (internet)" \
            0 "Sair" \
            < "$TTY_DEVICE" 2> "$TTY_DEVICE")"

        case "$choice" in
            1) if connect_games; then restart_emulationstation_and_exit; fi ;;
            2) if disconnect_games; then restart_emulationstation_and_exit; fi ;;
            3) show_status ;;
            4)
                if [ -f "$SYSTEM_CONFIG" ]; then
                    if ask_yes_no "Trocar configuracao" "Isto substituira o servidor e a senha guardados no R36S.\n\nDeseja importar o arquivo .conf novamente?"; then
                        import_configuration
                    fi
                else
                    import_configuration
                fi
                ;;
            5)
                generate_diagnostic
                show_text_file "Diagnostico - salvo em tools" "$REPORT_FILE"
                ;;
            6) install_smb_support ;;
            0|"") break ;;
        esac
    done
}

install_smb_support_cli() {
    if ! command -v apt-get >/dev/null 2>&1; then
        printf 'Port Doctor: apt-get não está disponível neste sistema.\n' >&2
        return 1
    fi
    log_line "Inicio da instalacao de cifs-utils pelo Port Doctor."
    if apt-get update >> "$LOG_FILE" 2>&1 && \
       DEBIAN_FRONTEND=noninteractive apt-get install -y cifs-utils >> "$LOG_FILE" 2>&1; then
        modprobe cifs >> "$LOG_FILE" 2>&1 || true
        if check_cifs_support; then
            printf 'Port Doctor: suporte SMB/CIFS instalado e validado.\n'
            return 0
        fi
    fi
    generate_diagnostic
    printf 'Port Doctor: não foi possível validar o suporte SMB. Diagnóstico: %s\n' "$REPORT_FILE" >&2
    return 1
}

show_status_cli() {
    local status_text binds_count
    status_text="desconectado"
    if cifs_is_mounted; then status_text="conectado"; fi
    binds_count="0"
    if [ -f "$BIND_LIST" ]; then
        binds_count="$(grep -c '^/' "$BIND_LIST" 2>/dev/null || printf '0')"
    fi
    if load_configuration; then
        printf 'Rede: %s; servidor: %s; compartilhamento: %s; sistemas: %s.\n' \
            "$status_text" "$SERVER" "$SHARE" "$binds_count"
    else
        printf 'Rede: %s; configuração ainda não importada; sistemas: %s.\n' \
            "$status_text" "$binds_count"
    fi
}

run_cli() {
    case "${1:-status}" in
        status)
            show_status_cli
            ;;
        import)
            import_configuration
            ;;
        connect)
            if connect_games; then
                log_line "Conexao solicitada pelo Port Doctor."
                (sleep 3; systemctl restart emulationstation >/dev/null 2>&1) &
                printf 'Port Doctor: jogos em rede conectados; o menu será recarregado.\n'
            else
                return 1
            fi
            ;;
        disconnect)
            if disconnect_games; then
                log_line "Desconexao solicitada pelo Port Doctor."
                (sleep 3; systemctl restart emulationstation >/dev/null 2>&1) &
                printf 'Port Doctor: jogos em rede desconectados; o menu será recarregado.\n'
            else
                return 1
            fi
            ;;
        diagnostic)
            generate_diagnostic
            printf 'Port Doctor: diagnóstico de rede salvo em %s\n' "$REPORT_FILE"
            ;;
        install-smb)
            install_smb_support_cli
            ;;
        *)
            printf 'Uso: %s status|import|connect|disconnect|diagnostic|install-smb\n' "$0" >&2
            return 2
            ;;
    esac
}

if [ $# -gt 0 ]; then
    run_cli "$@"
    exit $?
fi

setup_ui
if ! command -v dialog >/dev/null 2>&1; then
    generate_diagnostic
    printf '\nO programa dialog nao foi encontrado. Diagnostico: %s\n' "$REPORT_FILE" > "$TTY_DEVICE" 2>/dev/null
    exit 1
fi

if [ ! -f "$SYSTEM_CONFIG" ] && [ -f "$IMPORT_CONFIG" ]; then
    if ask_yes_no "Primeira configuracao" "Encontrei o arquivo criado no Windows.\n\nDeseja importar a configuracao agora?"; then
        import_configuration
    fi
fi

main_menu
exit 0
