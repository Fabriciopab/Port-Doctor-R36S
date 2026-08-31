#!/bin/sh
set -u

ZRAM_DEVICE="/dev/zram0"
ZRAM_SYSFS="/sys/block/zram0"
ZRAM_SIZE="805306368"

as_root() {
    if [ "$(id -u)" -eq 0 ]; then
        "$@"
    elif command -v sudo >/dev/null 2>&1 && sudo -n true 2>/dev/null; then
        sudo -n "$@"
    else
        return 1
    fi
}

already_active() {
    # Respect an active area chosen in the Doctor or by the firmware.
    awk 'NR > 1 && $1 ~ /^\/dev\/zram[0-9]+$/ { found=1 } END { exit !found }' /proc/swaps 2>/dev/null
}

start_zram() {
    already_active && return 0

    if [ ! -e "$ZRAM_SYSFS/disksize" ] && [ -r /sys/class/zram-control/hot_add ]; then
        as_root sh -c 'cat /sys/class/zram-control/hot_add >/dev/null' || return 1
    fi
    [ -b "$ZRAM_DEVICE" ] && [ -e "$ZRAM_SYSFS/disksize" ] || return 1

    current_size="$(cat "$ZRAM_SYSFS/disksize" 2>/dev/null || printf '0')"
    if [ "$current_size" = "0" ]; then
        printf '%s\n' "$ZRAM_SIZE" | as_root tee "$ZRAM_SYSFS/disksize" >/dev/null || return 1
    fi
    as_root mkswap -f "$ZRAM_DEVICE" >/dev/null || return 1
    as_root swapon -p 100 "$ZRAM_DEVICE" || return 1
    already_active
}

case "${1:-start}" in
    start)
        start_zram
        ;;
    status)
        already_active
        ;;
    *)
        printf 'Uso: %s {start|status}\n' "$0" >&2
        exit 2
        ;;
esac
