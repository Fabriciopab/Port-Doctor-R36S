#!/bin/sh

# PortMaster Cover Fix v4 / Port Doctor R36S
# Coloque este script na pasta tools.
# As capas podem ficar em qualquer pasta ou subpasta dentro de port/ports.
# O nome da capa deve corresponder ao nome do arquivo .sh do jogo.

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" 2>/dev/null && pwd)
[ -n "$SCRIPT_DIR" ] || SCRIPT_DIR="$(pwd)"

if [ -n "${PORTDOCTOR_HOME:-}" ]; then
    mkdir -p "$PORTDOCTOR_HOME/conf/reports" 2>/dev/null || true
    LOGFILE="$PORTDOCTOR_HOME/conf/reports/portmaster-cover-fix.log"
else
    LOGFILE="$SCRIPT_DIR/portmaster-cover-fix.log"
fi
if ! : > "$LOGFILE" 2>/dev/null; then
    LOGFILE="/tmp/portmaster-cover-fix.log"
    : > "$LOGFILE"
fi

exec >> "$LOGFILE" 2>&1

echo "============================================================"
echo "PortMaster Cover Fix v4 / Port Doctor R36S"
echo "Data: $(date)"
echo "Script: $0"
echo "Pasta tools detectada: $SCRIPT_DIR"
echo "============================================================"

PROCESSED_PATHS="|"
PROCESSED_COUNT=0

restore_ports() {
    REQUESTED_PORTS=$1
    [ -d "$REQUESTED_PORTS" ] || return 0
    PORTS=$(CDPATH= cd -- "$REQUESTED_PORTS" 2>/dev/null && pwd -P)
    [ -n "$PORTS" ] || return 0
    GAMELIST="$PORTS/gamelist.xml"
    BACKUP=$(find "$PORTS" -maxdepth 1 -type f -name 'gamelist.xml.bak-*' 2>/dev/null | sort | tail -n 1)
    if [ -n "$BACKUP" ] && grep -q '<gameList' "$BACKUP" 2>/dev/null; then
        cp -p "$BACKUP" "$GAMELIST" && {
            echo "RESTAURADO: $GAMELIST"
            PROCESSED_COUNT=$((PROCESSED_COUNT + 1))
        }
    fi
}

create_launcher_cover_aliases() {
    PORTS=$1
    find "$PORTS" -maxdepth 1 -type f -iname '*.sh' ! -name '.*' |
    while IFS= read -r SHFILE
    do
        SHBASE=$(basename "$SHFILE")
        SHSTEM=${SHBASE%.*}

        # Descobre a pasta real usada pelo launcher. Funciona com /roms/ports,
        # /roms2/ports e com a declaração GAMEDIR mais comum no PortMaster.
        GAME_FOLDER=$(sed -n '
            s,.*\/ports\/\([^/" '\''[:space:]]*\).*,\1,p
            s,.*\/port\/\([^/" '\''[:space:]]*\).*,\1,p
            s,^[[:space:]]*GAMEDIR=["'\'']*[^"'\'']*/\([^/"'\'']*\)["'\'']*[[:space:]]*$,\1,p
        ' "$SHFILE" 2>/dev/null | head -n 1)

        [ -n "$GAME_FOLDER" ] || continue
        GAME_DIR="$PORTS/$GAME_FOLDER"
        [ -d "$GAME_DIR" ] || continue

        # Se já existe uma imagem com o nome do .sh, não cria duplicata.
        EXISTING=$(find "$PORTS" -maxdepth 2 -type f \
            \( -iname "$SHSTEM.png" -o -iname "$SHSTEM.jpg" -o -iname "$SHSTEM.jpeg" \
               -o -iname "$SHSTEM.webp" -o -iname "$SHSTEM.bmp" -o -iname "$SHSTEM.gif" \) \
            -print -quit 2>/dev/null)
        [ -z "$EXISTING" ] || continue

        GENERIC=$(find "$GAME_DIR" -maxdepth 5 -type f \
            \( -iname 'cover.png' -o -iname 'cover.jpg' -o -iname 'cover.jpeg' \
               -o -iname 'cover.webp' -o -iname 'cover.bmp' -o -iname 'cover.gif' \
               -o -iname 'cove.png' -o -iname 'cove.jpg' -o -iname 'cove.jpeg' \
               -o -iname 'cove.webp' -o -iname 'cove.bmp' -o -iname 'cove.gif' \) \
            -print -quit 2>/dev/null)
        [ -n "$GENERIC" ] || continue

        EXT=${GENERIC##*.}
        ALIAS="$PORTS/$SHSTEM.$EXT"
        if cp -p "$GENERIC" "$ALIAS"; then
            echo "CAPA NORMALIZADA: $GENERIC -> $ALIAS"
        else
            echo "ERRO: não foi possível criar $ALIAS"
        fi
    done
}

process_ports() {
    REQUESTED_PORTS=$1
    [ -d "$REQUESTED_PORTS" ] || return 0

    PORTS=$(CDPATH= cd -- "$REQUESTED_PORTS" 2>/dev/null && pwd -P)
    [ -n "$PORTS" ] || return 0

    case "$PROCESSED_PATHS" in
        *"|$PORTS|"*) return 0 ;;
    esac
    PROCESSED_PATHS="${PROCESSED_PATHS}${PORTS}|"

    GAMELIST="$PORTS/gamelist.xml"
    echo
    echo "Pasta de ports encontrada: $PORTS"
    echo "Procurando capas recursivamente em todas as subpastas de: $PORTS"

    create_launcher_cover_aliases "$PORTS"

    if [ ! -f "$GAMELIST" ]; then
        echo "gamelist.xml não existia. Criando: $GAMELIST"
        printf '%s\n' '<?xml version="1.0"?>' '<gameList>' '</gameList>' > "$GAMELIST"
    fi

    TMP=$(mktemp) || return 1
    IMAGELIST=$(mktemp) || {
        rm -f "$TMP"
        return 1
    }

    find "$PORTS" -type f \
        \( -iname "*.png" -o -iname "*.jpg" -o -iname "*.jpeg" \
           -o -iname "*.webp" -o -iname "*.bmp" -o -iname "*.gif" \) \
        > "$IMAGELIST"

    IMAGE_COUNT=$(wc -l < "$IMAGELIST" | tr -d ' ')
    echo "Quantidade de imagens reconhecidas: $IMAGE_COUNT"

    if [ ! -s "$IMAGELIST" ]; then
        echo "ERRO: nenhuma imagem PNG, JPG, JPEG, WEBP, BMP ou GIF foi encontrada."
        rm -f "$TMP" "$IMAGELIST"
        return 0
    fi

    BACKUP="$GAMELIST.bak-$(date +%Y%m%d-%H%M%S)-$$"
    cp "$GAMELIST" "$BACKUP" || {
        echo "ERRO: não foi possível criar o backup do gamelist.xml."
        rm -f "$TMP" "$IMAGELIST"
        return 0
    }

    cp "$GAMELIST" "$TMP" || {
        echo "ERRO: não foi possível copiar o gamelist.xml."
        rm -f "$TMP" "$IMAGELIST"
        return 0
    }

    #########################################################################
    # Adiciona ao gamelist.xml os arquivos .sh que ainda não estão nele.
    #########################################################################

    find "$PORTS" -maxdepth 1 -type f -iname "*.sh" ! -name ".*" |
    while IFS= read -r SHFILE
    do
        SHNAME="./$(basename "$SHFILE")"
        SHNAME_WITHOUT_DOT=${SHNAME#./}

        if ! grep -Fiq "<path>$SHNAME</path>" "$TMP" && \
           ! grep -Fiq "<path>$SHNAME_WITHOUT_DOT</path>" "$TMP"; then
            awk -v path="$SHNAME" '
            /<\/gameList>/ {
                print "    <game>"
                print "        <path>" path "</path>"
                print "    </game>"
            }
            { print }
            ' "$TMP" > "$TMP.new" && mv "$TMP.new" "$TMP"
        fi
    done

    #########################################################################
    # Associa as capas pelo nome e atualiza/adiciona a tag <image>.
    #########################################################################

    awk -v ports_directory="$PORTS" '
    function priority(name, lower) {
        lower = tolower(name)
        if (lower ~ /\.png$/)  return 6
        if (lower ~ /\.jpg$/)  return 5
        if (lower ~ /\.jpeg$/) return 4
        if (lower ~ /\.webp$/) return 3
        if (lower ~ /\.bmp$/)  return 2
        if (lower ~ /\.gif$/)  return 1
        return 0
    }

    function normalized(value, result) {
        result = tolower(value)
        gsub(/[^[:alnum:]]/, "", result)
        return result
    }

    function choose_cover(value, key) {
        key = tolower(value)
        if (key in exact_image)
            return exact_image[key]

        key = normalized(value)
        if (key in normalized_image)
            return normalized_image[key]

        if (key in directory_cover)
            return directory_cover[key]

        return ""
    }

    function common_cover_priority(value, key) {
        key = normalized(value)
        if (key == "cover")      return 100
        if (key == "cove")       return 99
        if (key == "boxart")     return 95
        if (key == "poster")     return 90
        if (key == "screenshot") return 80
        if (key == "thumbnail")  return 75
        if (key == "thumb")      return 70
        if (key == "image")      return 65
        if (key == "logo")       return 60
        if (key == "icon")       return 55
        return 0
    }

    function game_directory(script, script_file, line, lower, pos, value) {
        script_file = script

        if (script_file !~ /^\//) {
            sub(/^\.\//, "", script_file)
            script_file = ports_directory "/" script_file
        }

        while ((getline line < script_file) > 0) {
            gsub(/\r/, "", line)
            lower = tolower(line)
            pos = index(lower, "/ports/")

            if (pos > 0 && substr(lower, pos + 7, 10) != "portmaster") {
                value = substr(line, pos + 7)
                sub(/[\/\" \t].*$/, "", value)
                gsub(apostrophe, "", value)

                if (value != "") {
                    close(script_file)
                    return value
                }
            }
        }
        close(script_file)

        while ((getline line < script_file) > 0) {
            gsub(/\r/, "", line)
            lower = tolower(line)

            if (lower ~ /^[ \t]*gamedir=/) {
                value = line
                sub(/^[^=]*=/, "", value)
                sub(/[ \t]+#.*/, "", value)
                gsub(/[\" \t]/, "", value)
                gsub(apostrophe, "", value)
                sub(/\/$/, "", value)
                sub(/^.*\//, "", value)

                if (value != "") {
                    close(script_file)
                    return value
                }
            }
        }
        close(script_file)
        return ""
    }

    function xml_escape(value, output, i, character) {
        output = ""

        for (i = 1; i <= length(value); i++) {
            character = substr(value, i, 1)

            if (character == "&")
                output = output "&amp;"
            else if (character == "<")
                output = output "&lt;"
            else if (character == ">")
                output = output "&gt;"
            else
                output = output character
        }

        return output
    }

    BEGIN {
        inside = 0
        apostrophe = sprintf("%c", 39)
        updated = 0
        missing = 0
    }

    # Primeiro arquivo: lista das imagens disponíveis.
    FNR == NR {
        full_name = $0
        gsub(/\r$/, "", full_name)

        relative_path = full_name
        path_prefix = ports_directory "/"
        if (index(relative_path, path_prefix) == 1)
            relative_path = substr(relative_path, length(path_prefix) + 1)

        file_name = relative_path
        sub(/^.*\//, "", file_name)

        stem = tolower(file_name)
        sub(/\.(png|jpg|jpeg|webp|bmp|gif)$/, "", stem)

        key = normalized(stem)
        path_for_depth = relative_path
        depth = gsub(/\//, "/", path_for_depth)
        current_priority = priority(file_name) + 1000 - depth

        if (!(stem in exact_image) || current_priority > exact_priority[stem]) {
            exact_image[stem] = relative_path
            exact_priority[stem] = current_priority
        }

        if (!(key in normalized_image) || current_priority > normalized_priority[key]) {
            normalized_image[key] = relative_path
            normalized_priority[key] = current_priority
        }

        # Se a imagem se chama cover/boxart/poster/etc., associa a capa aos
        # nomes das pastas ancestrais. Ex.: Jogo/assets/cover.png -> Jogo.sh.
        common_priority = common_cover_priority(stem)
        directory_path = relative_path
        sub(/\/[^\/]*$/, "", directory_path)

        if (common_priority > 0 && directory_path != relative_path) {
            component_count = split(directory_path, components, "/")

            for (component_index = 1; component_index <= component_count; component_index++) {
                directory_key = normalized(components[component_index])
                directory_priority_value = common_priority * 100 + \
                                           priority(file_name) - \
                                           (component_count - component_index)

                if (directory_key != "" && \
                    (!(directory_key in directory_cover) || \
                     directory_priority_value > directory_cover_priority[directory_key])) {
                    directory_cover[directory_key] = relative_path
                    directory_cover_priority[directory_key] = directory_priority_value
                }
            }
        }
        next
    }

    /<game>/ {
        inside = 1
        block = ""
    }

    {
        if (inside)
            block = block $0 "\n"
        else
            print
    }

    /<\/game>/ {
        inside = 0
        path = ""
        cover = ""

        if (match(block, /<path>[^<]*<\/path>/)) {
            path = substr(block, RSTART, RLENGTH)
            sub(/^<path>[[:space:]]*/, "", path)
            sub(/[[:space:]]*<\/path>$/, "", path)

            stem = path
            sub(/^.*\//, "", stem)
            sub(/\.[sS][hH]$/, "", stem)

            cover = choose_cover(stem)

            if (cover == "" && tolower(path) ~ /\.sh$/) {
                directory = game_directory(path)
                if (directory != "")
                    cover = choose_cover(directory)
            }

            if (cover != "") {
                image = xml_escape("./" cover)

                if (match(block, /<image>[^<]*<\/image>/)) {
                    block = substr(block, 1, RSTART - 1) \
                            "<image>" image "</image>" \
                            substr(block, RSTART + RLENGTH)
                } else if (match(block, /<\/game>/)) {
                    block = substr(block, 1, RSTART - 1) \
                            "    <image>" image "</image>\n    </game>" \
                            substr(block, RSTART + RLENGTH)
                }

                updated++
                print "OK: " path " -> ./" cover > "/dev/stderr"
            } else {
                missing++
                print "SEM CAPA: " path > "/dev/stderr"
            }
        }

        printf "%s", block
        block = ""
    }

    END {
        print "Jogos atualizados: " updated > "/dev/stderr"
        print "Jogos sem imagem correspondente: " missing > "/dev/stderr"
    }
    ' "$IMAGELIST" "$TMP" > "$TMP.new"

    if [ $? -eq 0 ] && [ -s "$TMP.new" ]; then
        mv "$TMP.new" "$GAMELIST"
        echo "SUCESSO: gamelist.xml atualizado."
        echo "Backup criado: $BACKUP"
        PROCESSED_COUNT=$((PROCESSED_COUNT + 1))
    else
        echo "ERRO: não foi possível atualizar o gamelist.xml."
        rm -f "$TMP.new"
    fi

    rm -f "$TMP" "$IMAGELIST"
}

ACTION=${1:-sync}

if [ "$ACTION" = "restore" ]; then
    [ -n "${PORTS_PATH:-}" ] && restore_ports "$PORTS_PATH"
    restore_ports "/roms/ports"
    restore_ports "/roms2/ports"
    restore_ports "/roms/port"
    restore_ports "/roms2/port"
    BASE_DIR=$(dirname "$SCRIPT_DIR")
    restore_ports "$BASE_DIR/ports"
    restore_ports "$BASE_DIR/port"
else
    # Caminho opcional definido manualmente.
    if [ -n "${PORTS_PATH:-}" ]; then
        process_ports "$PORTS_PATH"
    fi

# Caminhos mais utilizados pelos sistemas ArkOS, dArkOS e similares.
process_ports "/roms/ports"
process_ports "/roms2/ports"
process_ports "/roms/port"
process_ports "/roms2/port"

# Detecta automaticamente a pasta ports ao lado da pasta tools.
BASE_DIR=$(dirname "$SCRIPT_DIR")
process_ports "$BASE_DIR/ports"
    process_ports "$BASE_DIR/port"
fi

echo
if [ "$PROCESSED_COUNT" -gt 0 ]; then
    echo "Finalizado. Pastas atualizadas: $PROCESSED_COUNT"
    sync
else
    echo "NENHUMA PASTA FOI ATUALIZADA."
    echo "Confira se a pasta port/ports está no mesmo cartão da pasta tools."
fi

echo "Relatório salvo em: $LOGFILE"

# Reinicia o EmulationStation sem bloquear o script caso sudo não esteja disponível.
if [ "$PROCESSED_COUNT" -gt 0 ] && [ "${SKIP_RESTART:-0}" != "1" ] && \
   command -v systemctl >/dev/null 2>&1; then
    if [ "$(id -u)" = "0" ]; then
        systemctl restart emulationstation >/dev/null 2>&1 || true
    elif command -v sudo >/dev/null 2>&1; then
        sudo -n systemctl restart emulationstation >/dev/null 2>&1 || true
    fi
fi

exit 0
