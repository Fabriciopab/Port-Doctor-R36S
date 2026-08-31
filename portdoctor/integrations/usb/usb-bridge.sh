#!/bin/bash
set -eu

BASE="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
CONF="/etc/r36s-usb-file-access.conf"
ACTION="${1:-status}"

CONTROL_SHA="58763e2acadb6ba69fe7d9f93b19e14b950c0d32ad299ec4cac26c3b737498e3"
GADGET_SHA="2e5ebc8c2cc7aeecb67d2ccbab3563ea4f696d712b4e4f676f3c4cb2ba63da57"
SERVICE_SHA="98b76e92e2a8803feadbae65a645b5363b56619fceaf9e4e8551cab1be97f929"

# O script independente sempre elevou a si próprio. A integração não pode
# depender apenas de ESUDO, pois algumas imagens dArkOSRE deixam essa variável
# vazia dentro de ports Love2D.
case "$ACTION" in
    status|install|activate|restore|uninstall)
        if [ "$(id -u)" -ne 0 ]; then
            if command -v sudo >/dev/null 2>&1; then
                exec sudo -n /bin/bash "$0" "$@"
            fi
            printf 'Port Doctor: esta ação USB requer elevação automática, mas sudo não está disponível.\n' >&2
            exit 1
        fi
        ;;
esac

verify_payload_file() {
    expected="$1"
    path="$2"
    [ -f "$path" ] || {
        printf 'Port Doctor: componente USB v1.0.2 ausente: %s\n' "$path" >&2
        return 1
    }
    actual="$(sha256sum "$path" | awk '{print $1}')"
    [ "$actual" = "$expected" ] || {
        printf 'Port Doctor: componente USB v1.0.2 alterado ou corrompido: %s\n' "$path" >&2
        return 1
    }
}

verify_original_payload() {
    verify_payload_file "$CONTROL_SHA" "$BASE/payload/r36s-usb-control" &&
    verify_payload_file "$GADGET_SHA" "$BASE/payload/r36s-usb-gadget" &&
    verify_payload_file "$SERVICE_SHA" "$BASE/payload/r36s-usb-gadget.service"
}

prepare_v102_state() {
    install -d -m 0700 /var/lib/samba/private || {
        printf 'Port Doctor: não foi possível preparar o banco de usuários Samba v1.0.2.\n' >&2
        return 1
    }
    if command -v smbpasswd >/dev/null 2>&1 && id ark >/dev/null 2>&1; then
        if command -v pdbedit >/dev/null 2>&1 && \
           pdbedit -L 2>/dev/null | cut -d: -f1 | grep -qx ark; then
            return 0
        fi
        printf 'Port Doctor: Samba sem conta configurada; use credenciais do firmware. Nenhuma senha padrão foi criada.\n' >&2
    fi
    return 0
}

preflight() {
    missing=""
    for command_name in dtc fdtget fdtput sha256sum systemctl modprobe ip; do
        command -v "$command_name" >/dev/null 2>&1 || missing="$missing $command_name"
    done
    for module_name in libcomposite usb_f_rndis; do
        modinfo "$module_name" >/dev/null 2>&1 || missing="$missing módulo:$module_name"
    done
    [ -f /boot/rk3326-r36s-linux.dtb ] || missing="$missing DTB:/boot/rk3326-r36s-linux.dtb"
    udc="$(find /sys/class/udc -mindepth 1 -maxdepth 1 -printf '%f\n' 2>/dev/null | head -n 1)"
    [ -n "$udc" ] || missing="$missing controlador:UDC"
    if [ -n "$missing" ]; then
        printf 'Port Doctor: USB por cabo incompatível; ausente:%s\n' "$missing" >&2
        return 1
    fi
    mode="$(fdtget -t s /boot/rk3326-r36s-linux.dtb /usb@ff300000 dr_mode 2>/dev/null || true)"
    case "$mode" in
        otg|peripheral) ;;
        *) printf 'Port Doctor: modo USB inesperado no DTB: %s\n' "${mode:-ausente}" >&2; return 1 ;;
    esac
    printf 'Port Doctor: USB compatível; DTB=%s; UDC=%s; modo=%s.\n' \
        /boot/rk3326-r36s-linux.dtb "$udc" "$mode"
}

status_cmd() {
    if [ ! -r "$CONF" ]; then
        printf 'Port Doctor: USB por cabo ainda não instalado. Execute a verificação e depois a instalação.\n'
        return 0
    fi
    # The file is root-owned and created by the validated installer.
    # shellcheck disable=SC1090
    . "$CONF"
    file_mode="$(fdtget -t s "$ACTIVE_DTB" "$USB_NODE" dr_mode 2>/dev/null || true)"
    live_mode="$(tr -d '\000' < "/proc/device-tree${USB_NODE}/dr_mode" 2>/dev/null || true)"
    service="$(systemctl is-active r36s-usb-gadget.service 2>/dev/null || true)"
    address="$(ip -4 -brief address show usb0 2>/dev/null || true)"
    rm -f "$(dirname "$ORIGINAL_DTB")/pending-mode" 2>/dev/null || true
    printf 'Port Doctor: USB v1.0.2 instalado; DTB=%s; boot=%s; serviço=%s; %s\n' \
        "${file_mode:-desconhecido}" "${live_mode:-desconhecido}" "${service:-inativo}" \
        "${address:-usb0 ausente}"
}

run_control() {
    action="$1"
    verify_original_payload || return 1
    prepare_v102_state || return 1
    [ -x /usr/local/sbin/r36s-usb-control ] || {
        printf 'Port Doctor: instale o acesso USB antes desta ação.\n' >&2
        return 1
    }
    if [ "$action" = "activate" ] || [ "$action" = "restore" ]; then
        for helper in r36s-usb-control r36s-usb-gadget; do
            packaged="$BASE/payload/$helper"
            installed="/usr/local/sbin/$helper"
            [ -f "$packaged" ] || continue
            /bin/bash -n "$packaged" || {
                printf 'Port Doctor: controlador USB empacotado está inválido: %s\n' "$helper" >&2
                return 1
            }
            if ! cmp -s "$packaged" "$installed"; then
                temporary="${installed}.portdoctor-new"
                install -m 755 "$packaged" "$temporary"
                mv -f "$temporary" "$installed"
            fi
        done
        if [ -f "$BASE/payload/r36s-usb-gadget.service" ] && \
           ! cmp -s "$BASE/payload/r36s-usb-gadget.service" /etc/systemd/system/r36s-usb-gadget.service; then
            install -m 644 "$BASE/payload/r36s-usb-gadget.service" \
                /etc/systemd/system/r36s-usb-gadget.service.portdoctor-new
            mv -f /etc/systemd/system/r36s-usb-gadget.service.portdoctor-new \
                /etc/systemd/system/r36s-usb-gadget.service
            systemctl daemon-reload
        fi
    fi
    exec /usr/local/sbin/r36s-usb-control "$action"
}

case "$ACTION" in
    preflight) preflight ;;
    status) status_cmd ;;
    install) verify_original_payload && exec /bin/bash "$BASE/install.sh" ;;
    activate) run_control activate ;;
    restore) run_control restore ;;
    uninstall) exec /usr/local/sbin/r36s-usb-control uninstall --confirm ;;
    *) printf 'Uso: %s preflight|status|install|activate|restore|uninstall\n' "$0" >&2; exit 2 ;;
esac
