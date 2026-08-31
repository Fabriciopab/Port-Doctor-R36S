#!/bin/bash
set -eu

BASE="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
TTY="/dev/tty1"

[ "$(id -u)" -eq 0 ] || exec sudo -n /bin/bash "$0" "$@"

aviso() {
    if command -v dialog >/dev/null 2>&1 && [ -w "$TTY" ]; then
        dialog --clear --title "R36S USB File Access" --infobox "$1" 14 68 <"$TTY" >"$TTY" 2>&1 || true
        sleep "${2:-5}"
    else
        printf '%b\n' "$1"
    fi
}

falha() {
    aviso "INSTALAÇÃO CANCELADA\n\n$1\n\nNenhum DTB ativo foi substituído." 7
    exit 1
}

aviso "Verificando o aparelho e preparando backups..." 3

[ -f "$BASE/payload/r36s-usb-control" ] || falha "Arquivos do pacote incompletos. Copie a pasta inteira."

MISSING_PACKAGES=""
add_package() {
    case " $MISSING_PACKAGES " in
        *" $1 "*) ;;
        *) MISSING_PACKAGES="$MISSING_PACKAGES $1" ;;
    esac
}

for CMD in dtc fdtget fdtput; do
    command -v "$CMD" >/dev/null 2>&1 || add_package device-tree-compiler
done
command -v dnsmasq >/dev/null 2>&1 || add_package dnsmasq
command -v smbd >/dev/null 2>&1 || add_package samba
command -v smbpasswd >/dev/null 2>&1 || add_package samba

if [ -n "$MISSING_PACKAGES" ]; then
    command -v apt-get >/dev/null 2>&1 || \
        falha "Dependências ausentes:$MISSING_PACKAGES. Este sistema não possui apt-get para instalá-las automaticamente."
    aviso "Instalando somente as dependências ausentes:$MISSING_PACKAGES\n\nÉ necessário acesso à internet." 4
    apt-get update || falha "Não foi possível atualizar a lista de pacotes. Confira a internet e tente novamente."
    # Word splitting is intentional: the list contains only fixed package names above.
    # shellcheck disable=SC2086
    DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends $MISSING_PACKAGES || \
        falha "Não foi possível instalar:$MISSING_PACKAGES"
fi

for CMD in dtc fdtget fdtput sha256sum systemctl modprobe ip dnsmasq smbd smbpasswd; do
    command -v "$CMD" >/dev/null 2>&1 || falha "Comando obrigatório ausente: $CMD"
done

for MOD in libcomposite usb_f_rndis; do
    modinfo "$MOD" >/dev/null 2>&1 || falha "Módulo do kernel ausente: $MOD"
done

UDC="$(find /sys/class/udc -mindepth 1 -maxdepth 1 -printf '%f\n' 2>/dev/null | head -n 1)"
[ -n "$UDC" ] || falha "Controlador USB Device (UDC) não encontrado."

ACTIVE_DTB="/boot/rk3326-r36s-linux.dtb"
USB_NODE="/usb@ff300000"
[ -f "$ACTIVE_DTB" ] || falha "DTB ativo não encontrado em $ACTIVE_DTB"

ACTIVE_MODE="$(fdtget -t s "$ACTIVE_DTB" "$USB_NODE" dr_mode 2>/dev/null || true)"
INSTALL_ACTIVE_SHA="$(sha256sum "$ACTIVE_DTB" | awk '{print $1}')"
case "$ACTIVE_MODE" in
    otg|peripheral) ;;
    *) falha "Modo USB inesperado no DTB: ${ACTIVE_MODE:-ausente}" ;;
esac

STATE_DIR="/boot/r36s-usb-file-access"
DATA_DIR="$BASE/data"
mkdir -p "$STATE_DIR" "$DATA_DIR/backups" "$DATA_DIR/logs"

semantic_match() {
    LEFT="$1"
    RIGHT="$2"
    TARGET_MODE="$3"
    TMPDIR_TEST="$(mktemp -d)"
    cp "$LEFT" "$TMPDIR_TEST/left.dtb"
    fdtput -t s "$TMPDIR_TEST/left.dtb" "$USB_NODE" dr_mode "$TARGET_MODE" >/dev/null 2>&1 || {
        rm -rf "$TMPDIR_TEST"
        return 1
    }
    dtc -q -I dtb -O dts -o "$TMPDIR_TEST/left.dts" "$TMPDIR_TEST/left.dtb" 2>/dev/null || true
    dtc -q -I dtb -O dts -o "$TMPDIR_TEST/right.dts" "$RIGHT" 2>/dev/null || true
    cmp -s "$TMPDIR_TEST/left.dts" "$TMPDIR_TEST/right.dts"
    RESULT=$?
    rm -rf "$TMPDIR_TEST"
    return "$RESULT"
}

ORIGINAL_SOURCE=""
if [ "$ACTIVE_MODE" = "otg" ]; then
    ORIGINAL_SOURCE="$ACTIVE_DTB"
else
    for CANDIDATE in \
        "$STATE_DIR/original.dtb" \
        "$ACTIVE_DTB.BACKUP-OTG" \
        "$BASE/R36S-V21-BACKUP-OTG.dtb" \
        "$DATA_DIR/backups/original.dtb"; do
        [ -f "$CANDIDATE" ] || continue
        [ "$(fdtget -t s "$CANDIDATE" "$USB_NODE" dr_mode 2>/dev/null || true)" = "otg" ] || continue
        if semantic_match "$CANDIDATE" "$ACTIVE_DTB" peripheral; then
            ORIGINAL_SOURCE="$CANDIDATE"
            break
        fi
    done
fi

[ -n "$ORIGINAL_SOURCE" ] || falha "O aparelho já está em peripheral e não foi localizado um backup OTG compatível."

cp "$ORIGINAL_SOURCE" "$STATE_DIR/original.dtb.tmp"
sync
mv -f "$STATE_DIR/original.dtb.tmp" "$STATE_DIR/original.dtb"
cp "$ORIGINAL_SOURCE" "$DATA_DIR/backups/original.dtb"

ORIGINAL_SHA="$(sha256sum "$STATE_DIR/original.dtb" | awk '{print $1}')"
[ "$(sha256sum "$DATA_DIR/backups/original.dtb" | awk '{print $1}')" = "$ORIGINAL_SHA" ] || falha "As duas cópias do backup não conferem."
[ "$(fdtget -t s "$STATE_DIR/original.dtb" "$USB_NODE" dr_mode 2>/dev/null)" = "otg" ] || falha "O backup não contém o modo OTG original."

cp "$STATE_DIR/original.dtb" "$STATE_DIR/peripheral.dtb.tmp"
fdtput -t s "$STATE_DIR/peripheral.dtb.tmp" "$USB_NODE" dr_mode peripheral
[ "$(fdtget -t s "$STATE_DIR/peripheral.dtb.tmp" "$USB_NODE" dr_mode 2>/dev/null)" = "peripheral" ] || falha "Não foi possível criar o DTB peripheral."

semantic_match "$STATE_DIR/original.dtb" "$STATE_DIR/peripheral.dtb.tmp" peripheral || falha "A comparação detectou alterações além do modo USB."
mv -f "$STATE_DIR/peripheral.dtb.tmp" "$STATE_DIR/peripheral.dtb"
cp "$STATE_DIR/peripheral.dtb" "$DATA_DIR/backups/peripheral.dtb"
USB_SHA="$(sha256sum "$STATE_DIR/peripheral.dtb" | awk '{print $1}')"

install -m 755 "$BASE/payload/r36s-usb-control" /usr/local/sbin/r36s-usb-control
install -m 755 "$BASE/payload/r36s-usb-gadget" /usr/local/sbin/r36s-usb-gadget
install -m 644 "$BASE/payload/r36s-usb-gadget.service" /etc/systemd/system/r36s-usb-gadget.service

# Preserve o banco existente. A distribuição pública não cria senha padrão
# nem altera credenciais do firmware; SSH e Samba usam bancos separados.
SAMBA_CREDENTIAL="não configurada; use a configuração de contas do firmware"
if command -v smbpasswd >/dev/null 2>&1 && id ark >/dev/null 2>&1; then
    install -d -m 0700 /var/lib/samba/private
    if command -v pdbedit >/dev/null 2>&1 && \
       pdbedit -L 2>/dev/null | cut -d: -f1 | grep -qx ark; then
        SAMBA_CREDENTIAL="preservada"
    fi
fi

cat > /etc/r36s-usb-file-access.conf <<EOF
ACTIVE_DTB='$ACTIVE_DTB'
ORIGINAL_DTB='$STATE_DIR/original.dtb'
PERIPHERAL_DTB='$STATE_DIR/peripheral.dtb'
USB_NODE='$USB_NODE'
UDC='$UDC'
ORIGINAL_SHA='$ORIGINAL_SHA'
PERIPHERAL_SHA='$USB_SHA'
INSTALL_ACTIVE_SHA='$INSTALL_ACTIVE_SHA'
PACKAGE_DIR='$BASE'
EOF
chmod 600 /etc/r36s-usb-file-access.conf

systemctl daemon-reload
systemctl enable r36s-usb-gadget.service >/dev/null

{
    echo "Instalado: $(date -Is)"
    echo "DTB ativo no momento da instalação: $ACTIVE_MODE"
    echo "SHA do DTB ativo na instalação: $INSTALL_ACTIVE_SHA"
    echo "Backup original: $ORIGINAL_SHA"
    echo "DTB peripheral: $USB_SHA"
    echo "UDC: $UDC"
    echo "Credencial Samba ark: $SAMBA_CREDENTIAL"
} >> "$DATA_DIR/logs/install.log"

aviso "INSTALAÇÃO CONCLUÍDA\n\nNenhum reinício foi feito.\n\nSamba: $SAMBA_CREDENTIAL\nUse suas credenciais já configuradas.\nNenhuma senha padrão é criada pelo Doctor.\n\nUse 'Ativar USB por Cabo' para conectar.\nUse 'Restaurar USB e WiFi' para voltar ao Wi-Fi.\n\nfabriciopab - Byte Force Tecnologias" 10
