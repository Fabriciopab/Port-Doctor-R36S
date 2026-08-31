#!/bin/bash
set -u

HOME_DIR="${PORTDOCTOR_HOME:-}"
PORTS_DIR="${PORTS_ROOT:-}"
REPORT_DIR="${HOME_DIR:-/tmp}/conf/reports"
mkdir -p "$REPORT_DIR" 2>/dev/null || REPORT_DIR="/tmp"
REPORT="$REPORT_DIR/storage-doctor-$(date +%Y%m%d-%H%M%S).log"

exec > >(tee "$REPORT") 2>&1

FAILURES=0
TOKEN="portdoctor-$$-$(date +%s)"

show_mount() {
    path="$1"
    label="$2"
    if command -v findmnt >/dev/null 2>&1; then
        info="$(findmnt -no TARGET,FSTYPE,OPTIONS -T "$path" 2>/dev/null || true)"
    else
        info="$(mount 2>/dev/null | grep " $(df -P "$path" 2>/dev/null | awk 'NR==2 {print $6}') " | head -n 1)"
    fi
    printf 'MONTAGEM %s: %s\n' "$label" "${info:-não identificada}"
}

test_user_write() {
    directory="$1"
    label="$2"
    test_file="$directory/.portdoctor-write-test-$$"
    if [ ! -d "$directory" ]; then
        printf 'FALHA %s: pasta inexistente: %s\n' "$label" "$directory"
        FAILURES=$((FAILURES + 1))
        return
    fi
    if printf '%s\n' "$TOKEN" > "$test_file" 2>/dev/null && \
       [ "$(cat "$test_file" 2>/dev/null || true)" = "$TOKEN" ]; then
        rm -f "$test_file"
        printf 'OK %s: gravação, leitura e remoção confirmadas em %s\n' "$label" "$directory"
    else
        rm -f "$test_file" 2>/dev/null || true
        printf 'FALHA %s: não foi possível persistir um arquivo temporário em %s\n' "$label" "$directory"
        FAILURES=$((FAILURES + 1))
    fi
}

test_root_write() {
    if [ ! -d /boot ]; then
        printf 'FALHA BOOT: /boot não existe.\n'
        FAILURES=$((FAILURES + 1))
        return
    fi
    root_test="/boot/.portdoctor-root-write-test-$$"
    if [ "$(id -u)" -eq 0 ]; then
        if printf '%s\n' "$TOKEN" > "$root_test" 2>/dev/null && \
           [ "$(cat "$root_test" 2>/dev/null || true)" = "$TOKEN" ]; then
            rm -f "$root_test"
            printf 'OK BOOT: gravação administrativa confirmada em /boot.\n'
            return
        fi
    elif command -v sudo >/dev/null 2>&1 && \
         sudo -n sh -c 'printf "%s\n" "$1" > "$2" && test "$(cat "$2")" = "$1" && rm -f "$2"' \
             sh "$TOKEN" "$root_test"; then
        printf 'OK BOOT: sudo sem senha e gravação administrativa confirmados em /boot.\n'
        return
    fi
    printf 'FALHA BOOT: não foi possível elevar e persistir o teste em /boot.\n'
    FAILURES=$((FAILURES + 1))
}

printf 'Port Doctor R36S - Diagnóstico de gravação\n'
printf 'Data: %s\n' "$(date -Is)"
printf 'Usuário: %s uid=%s grupos=%s\n' "$(id -un)" "$(id -u)" "$(id -Gn)"
printf 'Port Doctor: %s\nPasta de ports: %s\n' "${HOME_DIR:-não definida}" "${PORTS_DIR:-não definida}"

[ -n "$HOME_DIR" ] && show_mount "$HOME_DIR" PORTDOCTOR
[ -n "$PORTS_DIR" ] && show_mount "$PORTS_DIR" PORTS
show_mount /boot BOOT

if [ -n "$HOME_DIR" ]; then
    test_user_write "$HOME_DIR/conf" PORTDOCTOR
else
    printf 'FALHA PORTDOCTOR: PORTDOCTOR_HOME não foi definido.\n'
    FAILURES=$((FAILURES + 1))
fi
if [ -n "$PORTS_DIR" ]; then
    test_user_write "$PORTS_DIR" PORTS
else
    printf 'FALHA PORTS: PORTS_ROOT não foi definido.\n'
    FAILURES=$((FAILURES + 1))
fi
test_root_write

printf 'Espaço disponível:\n'
df -h "$HOME_DIR" "$PORTS_DIR" /boot 2>/dev/null | awk '!seen[$1]++' || true

if [ "$FAILURES" -gt 0 ]; then
    printf 'RESULTADO: FALHOU (%s teste(s)). Relatório: %s\n' "$FAILURES" "$REPORT"
    exit 1
fi

printf 'Relatório: %s\n' "$REPORT"
sync
printf 'RESULTADO: APROVADO. O sistema consegue gravar nos três destinos.\n'
exit 0
