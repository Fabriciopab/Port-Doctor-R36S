#!/bin/bash
set -eu

VERSION="${PORTDOCTOR_INSTALL_VERSION:-0.11.4}"
[[ "$VERSION" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]] || exit 1
SCRIPT_PATH="$(readlink -f "$0" 2>/dev/null || printf '%s' "$0")"
BASE="$(CDPATH= cd -- "$(dirname -- "$SCRIPT_PATH")" && pwd)"
PACKAGE="$BASE/portdoctor.zip"
LOG_FILE="$BASE/instalacao-portdoctor.log"
TTY_DEVICE="/dev/tty1"

: > "$LOG_FILE" 2>/dev/null || LOG_FILE="/tmp/instalacao-portdoctor.log"
exec >> "$LOG_FILE" 2>&1

message() {
    title="$1"
    text="$2"
    seconds="${3:-4}"
    if [ "${PORTDOCTOR_INSTALL_QUIET:-0}" != 1 ] && command -v dialog >/dev/null 2>&1 && [ -w "$TTY_DEVICE" ]; then
        dialog --clear --title "$title" --infobox "$text" 15 68 < "$TTY_DEVICE" > "$TTY_DEVICE" 2>&1 || true
        sleep "$seconds"
    else
        printf '\n%s\n%b\n' "$title" "$text"
    fi
}

fail() {
    message "Port Doctor - Instalação cancelada" "$1\n\nNenhuma instalação incompleta será mantida.\nLog: $LOG_FILE" 8
    exit 1
}

detect_ports_root() {
    control=""
    for candidate in \
        /opt/system/Tools/PortMaster/control.txt \
        /opt/tools/PortMaster/control.txt \
        /roms/ports/PortMaster/control.txt \
        /roms2/ports/PortMaster/control.txt; do
        if [ -f "$candidate" ]; then control="$candidate"; break; fi
    done

    selected="roms"
    if [ -n "$control" ]; then
        detected="$(/bin/bash -c 'set +u; source "$1" >/dev/null 2>&1; printf "%s" "${directory:-roms}"' _ "$control" 2>/dev/null || true)"
        case "$detected" in roms|roms2) selected="$detected" ;; esac
    elif [ -d /roms2/ports ] && [ ! -d /roms/ports ]; then
        selected="roms2"
    fi
    printf '/%s/ports' "$selected"
}

[ -f "$PACKAGE" ] || fail "O arquivo portdoctor.zip precisa permanecer ao lado deste instalador."
command -v unzip >/dev/null 2>&1 || fail "O comando unzip não está disponível nesta imagem."

PORTS_ROOT="${PORTDOCTOR_INSTALL_PORTS_ROOT:-$(detect_ports_root)}"
case "$PORTS_ROOT" in /roms/ports|/roms2/ports) ;; *) fail "Pasta de ports não reconhecida: $PORTS_ROOT" ;; esac
[ -d "$PORTS_ROOT" ] || fail "Pasta de ports não encontrada: $PORTS_ROOT"
[ ! -L "$PORTS_ROOT/portdoctor" ] && [ ! -L "$PORTS_ROOT/portdoctor-install-backups" ] || fail "Pasta de instalação/backup não pode ser um link."

if [ "$(id -u)" -ne 0 ] && [ ! -w "$PORTS_ROOT" ]; then
    if command -v sudo >/dev/null 2>&1; then
        exec sudo -n -E /bin/bash "$SCRIPT_PATH"
    fi
    fail "Sem permissão de gravação e sudo indisponível."
fi

# Serialize manual and in-app installers without waiting for an interactive prompt.
if command -v flock >/dev/null 2>&1; then
    [ ! -L "$PORTS_ROOT/.portdoctor-installer.lock" ] || fail "Trava de instalação inválida."
    exec 9>"$PORTS_ROOT/.portdoctor-installer.lock"
    flock -n 9 || fail "Outra instalação está em andamento. Aguarde sua conclusão."
fi

message "Instalando Port Doctor R36S" "Validando o pacote e preparando uma instalação segura..." 2
unzip -tq "$PACKAGE" || fail "O ZIP está corrompido ou incompleto. Baixe-o novamente."

ARCHIVE_LIST="$(unzip -Z1 "$PACKAGE")"
if printf '%s\n' "$ARCHIVE_LIST" | grep -Eq '(^/|(^|/)\.\.(/|$)|\\)'; then
    fail "O ZIP contém um caminho inseguro e foi recusado."
fi
for required in "Port Doctor R36S.sh" "portdoctor/lovegame/main.lua" "portdoctor/portdoctor.gptk"; do
    printf '%s\n' "$ARCHIVE_LIST" | grep -Fxq "$required" || fail "Arquivo obrigatório ausente: $required"
done

STAGE="$(mktemp -d "$PORTS_ROOT/.portdoctor-install.XXXXXX")" || fail "Não foi possível criar a área temporária."
cleanup_stage() { rm -rf -- "$STAGE" 2>/dev/null || true; }
trap cleanup_stage EXIT INT TERM

unzip -q "$PACKAGE" "Port Doctor R36S.sh" "portdoctor/*" "port.json" -d "$STAGE" || \
    fail "Não foi possível extrair os arquivos do Port Doctor."
[ -f "$STAGE/Port Doctor R36S.sh" ] && [ -f "$STAGE/portdoctor/lovegame/main.lua" ] || \
    fail "A validação depois da extração falhou."

TARGET_LAUNCHER="$PORTS_ROOT/Port Doctor R36S.sh"
TARGET_HOME="$PORTS_ROOT/portdoctor"
BACKUP_ROOT="$PORTS_ROOT/portdoctor-install-backups"
mkdir -p "$BACKUP_ROOT"
BACKUP_DIR="$(mktemp -d "$BACKUP_ROOT/$(date '+%Y%m%d-%H%M%S').XXXXXX")"

if [ -e "$TARGET_LAUNCHER" ]; then mv -- "$TARGET_LAUNCHER" "$BACKUP_DIR/"; fi
if [ -e "$TARGET_HOME" ]; then mv -- "$TARGET_HOME" "$BACKUP_DIR/"; fi

restore_previous() {
    rm -f -- "$TARGET_LAUNCHER" 2>/dev/null || true
    rm -rf -- "$TARGET_HOME" 2>/dev/null || true
    if [ -e "$BACKUP_DIR/Port Doctor R36S.sh" ]; then mv -- "$BACKUP_DIR/Port Doctor R36S.sh" "$TARGET_LAUNCHER"; fi
    if [ -e "$BACKUP_DIR/portdoctor" ]; then mv -- "$BACKUP_DIR/portdoctor" "$TARGET_HOME"; fi
}

if ! mv -- "$STAGE/portdoctor" "$TARGET_HOME" || ! mv -- "$STAGE/Port Doctor R36S.sh" "$TARGET_LAUNCHER"; then
    restore_previous
    fail "A troca dos arquivos falhou; a instalação anterior foi restaurada."
fi

# Atualizações preservam relatórios, manifestos e cópias necessárias para
# verificar ou desfazer reparos realizados pela versão anterior.
if [ -d "$BACKUP_DIR/portdoctor/conf" ]; then
    if ! mkdir -p "$TARGET_HOME/conf" || ! cp -a "$BACKUP_DIR/portdoctor/conf/." "$TARGET_HOME/conf/"; then
        restore_previous
        fail "A versão nova foi extraída, mas os dados dos reparos anteriores não puderam ser preservados. A instalação anterior foi restaurada."
    fi
fi

# Keep user-provided compatibility packs without replacing new bundled files.
if [ -d "$BACKUP_DIR/portdoctor/compat-packs" ]; then
    if ! mkdir -p "$TARGET_HOME/compat-packs" || ! cp -an "$BACKUP_DIR/portdoctor/compat-packs/." "$TARGET_HOME/compat-packs/"; then
        restore_previous
        fail "Não foi possível preservar os pacotes de compatibilidade; instalação anterior restaurada."
    fi
fi

if [ -f "$STAGE/port.json" ]; then cp "$STAGE/port.json" "$TARGET_HOME/port.json"; fi
chmod a+rx "$TARGET_LAUNCHER"
find "$TARGET_HOME/integrations" -type d -exec chmod a+rx {} + 2>/dev/null || true
find "$TARGET_HOME/integrations" -type f -name '*.sh' -exec chmod a+rx {} + 2>/dev/null || true
find "$TARGET_HOME/tools" -type d -exec chmod a+rx {} + 2>/dev/null || true
find "$TARGET_HOME/tools" -type f -name '*.sh' -exec chmod a+rx {} + 2>/dev/null || true
for helper in \
    "$TARGET_HOME/integrations/usb/payload/r36s-usb-control" \
    "$TARGET_HOME/integrations/usb/payload/r36s-usb-gadget"; do
    [ -f "$helper" ] && chmod a+rx "$helper"
done

OWNER_USER="ark"
id "$OWNER_USER" >/dev/null 2>&1 || OWNER_USER="$(id -un)"
chown -R "$OWNER_USER":"$(id -gn "$OWNER_USER")" "$TARGET_LAUNCHER" "$TARGET_HOME" 2>/dev/null || true
sync

trap - EXIT INT TERM
cleanup_stage
message "Port Doctor R36S instalado" "Versão $VERSION instalada em:\n$PORTS_ROOT\n\nNão é necessário SSH ou chmod.\nO menu será recarregado." 7

if [ "${PORTDOCTOR_INSTALL_NO_RESTART:-0}" != 1 ] && command -v systemctl >/dev/null 2>&1; then
    (sleep 2; systemctl --no-ask-password restart emulationstation >/dev/null 2>&1 || sudo -n systemctl restart emulationstation >/dev/null 2>&1 || true) &
fi
exit 0
