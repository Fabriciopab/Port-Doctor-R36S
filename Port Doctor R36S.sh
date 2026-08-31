#!/bin/bash
set -u

XDG_DATA_HOME=${XDG_DATA_HOME:-$HOME/.local/share}
PORTNAME="portdoctor"
PORTDOCTOR_SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)

if [ -d "/opt/system/Tools/PortMaster/" ]; then
    controlfolder="/opt/system/Tools/PortMaster"
elif [ -d "/opt/tools/PortMaster/" ]; then
    controlfolder="/opt/tools/PortMaster"
elif [ -d "$XDG_DATA_HOME/PortMaster/" ]; then
    controlfolder="$XDG_DATA_HOME/PortMaster"
else
    controlfolder="/roms/ports/PortMaster"
fi

if [ ! -f "$controlfolder/control.txt" ]; then
    echo "Port Doctor: PortMaster control.txt não encontrado." >&2
    exit 1
fi

export controlfolder
set +u
# shellcheck disable=SC1090
source "$controlfolder/control.txt"
[ -f "${controlfolder}/mod_${CFW_NAME:-}.txt" ] && source "${controlfolder}/mod_${CFW_NAME:-}.txt"
if declare -F get_controls >/dev/null 2>&1; then
    get_controls || true
fi
set -u

if [ -n "${directory:-}" ] && [ -d "/${directory}/ports/${PORTNAME}" ]; then
    GAMEDIR="/${directory}/ports/${PORTNAME}"
elif [ -d "$PORTDOCTOR_SCRIPT_DIR/${PORTNAME}" ]; then
    GAMEDIR="$PORTDOCTOR_SCRIPT_DIR/${PORTNAME}"
else
    echo "Port Doctor: pasta ${PORTNAME} não encontrada." >&2
    exit 1
fi

CONFDIR="$GAMEDIR/conf"

run_elevated() {
    "$@" 2>/dev/null && return 0
    if [ -n "${ESUDO:-}" ]; then
        ${ESUDO} "$@" 2>/dev/null && return 0
    fi
    if command -v sudo >/dev/null 2>&1; then
        sudo -n "$@" 2>/dev/null && return 0
    fi
    return 1
}

bootstrap_installation() {
    local owner_uid owner_gid helper
    owner_uid="$(id -u)"
    owner_gid="$(id -g)"

    # A normal PortMaster installation already has these modes. This repair
    # also covers ZIPs extracted through Windows/Samba without Unix bits.
    run_elevated mkdir -p "$CONFDIR/reports" "$CONFDIR/backups" || return 1
    run_elevated chown -R "$owner_uid:$owner_gid" "$CONFDIR" || true
    run_elevated chmod -R u+rwX "$CONFDIR" || return 1
    run_elevated chmod a+rx "$PORTDOCTOR_SCRIPT_DIR/Port Doctor R36S.sh" || return 1

    if [ -d "$GAMEDIR/integrations" ]; then
        run_elevated find "$GAMEDIR/integrations" -type d -exec chmod a+rx {} + || return 1
        run_elevated find "$GAMEDIR/integrations" -type f -name '*.sh' -exec chmod a+rx {} + || return 1
    fi
    if [ -d "$GAMEDIR/tools" ]; then
        run_elevated find "$GAMEDIR/tools" -type d -exec chmod a+rx {} + || return 1
        run_elevated find "$GAMEDIR/tools" -type f -name '*.sh' -exec chmod a+rx {} + || return 1
    fi
    for helper in \
        "$GAMEDIR/integrations/usb/payload/r36s-usb-control" \
        "$GAMEDIR/integrations/usb/payload/r36s-usb-gadget"; do
        [ -f "$helper" ] || continue
        run_elevated chmod a+rx "$helper" || return 1
    done
    return 0
}

if ! bootstrap_installation; then
    echo "Port Doctor: não foi possível preparar as permissões automaticamente." >&2
    if declare -F pm_message >/dev/null 2>&1; then
        pm_message "Port Doctor não conseguiu preparar sua pasta. Reinstale o pacote pelo PortMaster."
    fi
    exit 1
fi

cd "$GAMEDIR" || exit 1

: > "$GAMEDIR/log.txt"
exec > >(tee -a "$GAMEDIR/log.txt") 2>&1

export XDG_DATA_HOME="$CONFDIR"
export XDG_CONFIG_HOME="$CONFDIR"
export PORTDOCTOR_HOME="$GAMEDIR"
export PORTS_ROOT="$(dirname "$GAMEDIR")"
export PORTMASTER_HOME="$controlfolder"
export PORTDOCTOR_ESUDO="${ESUDO:-}"
export SDL_GAMECONTROLLERCONFIG="${sdl_controllerconfig:-${SDL_GAMECONTROLLERCONFIG:-}}"

if command -v python3 >/dev/null 2>&1 && [ -f "$GAMEDIR/tools/install_metadata.py" ]; then
    python3 "$GAMEDIR/tools/install_metadata.py" --ports-root "$PORTS_ROOT" --port-home "$GAMEDIR" || true
fi

runtime="love_11.5"
runtime_file="$controlfolder/runtimes/$runtime/love.txt"

if [ ! -f "$runtime_file" ]; then
    if [ ! -x "$controlfolder/harbourmaster" ]; then
        echo "Port Doctor: runtime Love2D 11.5 ausente e HarbourMaster indisponível." >&2
        exit 1
    fi
    ${ESUDO:-} "$controlfolder/harbourmaster" --quiet --no-check runtime_check "$runtime"
fi

if [ ! -f "$runtime_file" ]; then
    echo "Port Doctor: não foi possível preparar o runtime $runtime." >&2
    exit 1
fi

# shellcheck disable=SC1090
set +u
source "$runtime_file"
set -u

GPTK_PID=""
if [ -n "${GPTOKEYB:-}" ] && [ -n "${LOVE_GPTK:-}" ] && [ -f "$GAMEDIR/portdoctor.gptk" ]; then
    $GPTOKEYB "$LOVE_GPTK" -c "$GAMEDIR/portdoctor.gptk" &
    GPTK_PID=$!
fi

if declare -F pm_platform_helper >/dev/null 2>&1; then
    pm_platform_helper "$LOVE_BINARY"
fi

cleanup() {
    trap - EXIT INT TERM
    if [ -n "$GPTK_PID" ] && kill -0 "$GPTK_PID" 2>/dev/null; then
        kill "$GPTK_PID" 2>/dev/null || true
    fi
    if declare -F pm_finish >/dev/null 2>&1; then
        pm_finish
    fi
}
trap cleanup EXIT INT TERM

$LOVE_RUN "$GAMEDIR/lovegame"
status=$?
# Apply only a package already downloaded, validated and confirmed inside the UI.
# The UI and its worker have exited, so no live Lua files are replaced in use.
if [ -f "$(dirname "$GAMEDIR")/.portdoctor-updates/pending.json" ]; then
    echo "Port Doctor: instalando atualização confirmada. Não desligue o console."
    python3 "$GAMEDIR/tools/updater.py" apply || status=$?
fi
exit "$status"
