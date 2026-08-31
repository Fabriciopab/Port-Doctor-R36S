local util = require("src.util")

local logdoctor = {}

local severityRank = { error = 3, warn = 2, info = 1 }

local function addIssue(issues, seen, issue)
    local key = issue.id .. ":" .. tostring(issue.badPath or issue.library or "")
    if seen[key] then
        return
    end
    seen[key] = true
    issues[#issues + 1] = issue
end

local function sortIssues(issues)
    table.sort(issues, function(left, right)
        local leftRank = severityRank[left.severity] or 0
        local rightRank = severityRank[right.severity] or 0
        if leftRank ~= rightRank then
            return leftRank > rightRank
        end
        local leftPriority = tonumber(left.priority) or 0
        local rightPriority = tonumber(right.priority) or 0
        if leftPriority ~= rightPriority then
            return leftPriority > rightPriority
        end
        return tostring(left.label or "") < tostring(right.label or "")
    end)
end

local function compactEvidence(line)
    line = util.trim(line)
    if #line > 220 then
        return line:sub(1, 217) .. "..."
    end
    return line
end

function logdoctor.analyze(text)
    local issues = {}
    local seen = {}
    local pipewireEvidence
    local audioBusyEvidence
    local cleanupEvidence
    local memoryEvidence
    local missingGameDataEvidence
    local compressedGameArchiveEvidence
    local invalidMemoryEvidence
    local missingOptionalAssetEvidence
    local missingOptionalAsset
    local localRuntimeEvidence
    local localRuntimeName
    local graphicsProviderEvidence
    local corruptJavaArchiveEvidence
    local emptyDisplayDimensionEvidence
    local corruptVorbisEvidence
    local wrongNativeArchitectureEvidence
    local memoryBytes = 0

    for rawLine in tostring(text or ""):gmatch("[^\r\n]+") do
        local line = util.trim(rawLine)
        local lowered = line:lower()

        local rejectedRuntime = line:match("[Uu]nknown runtime%s+([%w%._%-]+%.squashfs)")
            or line:match("Runtime%s+([%w%._%-]+%.squashfs)%s+n[aã]o encontrado")
        if rejectedRuntime then
            localRuntimeName = localRuntimeName or rejectedRuntime
            localRuntimeEvidence = localRuntimeEvidence or compactEvidence(line)
        end
        if lowered:find("failed to create sdl window", 1, true)
            and (lowered:find("can't load egl/gl library", 1, true)
                or lowered:find("egl not initialized", 1, true)) then
            graphicsProviderEvidence = graphicsProviderEvidence or compactEvidence(line)
        end
        if lowered:find("invalid or corrupt jarfile", 1, true) then
            corruptJavaArchiveEvidence = corruptJavaArchiveEvidence or compactEvidence(line)
        end
        if line:find("%-Dsts%.width=%s+%-Dsts%.height=") then
            emptyDisplayDimensionEvidence = emptyDisplayDimensionEvidence or compactEvidence(line)
        end
        if lowered:find("ov_open_callbacks error %-132") then
            corruptVorbisEvidence = corruptVorbisEvidence or compactEvidence(line)
        end
        if lowered:find("wrong elf class:%s*elfclass32") then
            wrongNativeArchitectureEvidence = wrongNativeArchitectureEvidence or compactEvidence(line)
        end

        local badPath = line:match("error while loading shared libraries:%s*([^:]+):%s*file too short")
        if badPath then
            badPath = util.trim(badPath)
            local failedExecutable = util.trim(line:match("^([^:]+):%s*error while loading shared libraries") or "")
            addIssue(issues, seen, {
                id = "truncated_library",
                kind = "truncated_library",
                severity = "error",
                label = "Biblioteca corrompida",
                value = util.basename(badPath) .. " está truncada",
                detail = "A biblioteca encontrada pelo carregador não é um ELF válido. O jogo não consegue iniciar.",
                evidence = compactEvidence(line),
                badPath = badPath,
                executable = failedExecutable,
                library = util.basename(badPath),
                repairable = true,
            })
        end

        local missing = line:match("error while loading shared libraries:%s*([^:]+):%s*cannot open shared object file")
        if missing then
            missing = util.trim(missing)
            local failedExecutable = util.trim(line:match("^([^:]+):%s*error while loading shared libraries") or "")
            addIssue(issues, seen, {
                id = "missing_library",
                kind = "missing_library",
                severity = "error",
                label = "Biblioteca ausente",
                value = util.basename(missing) .. " não encontrada",
                detail = "O carregador dinâmico não localizou uma dependência exigida pelo executável.",
                evidence = compactEvidence(line),
                badPath = missing,
                executable = failedExecutable,
                library = util.basename(missing),
                repairable = true,
            })
        end

        local symbol = line:match("undefined symbol:%s*([^,%s]+)")
        if symbol then
            addIssue(issues, seen, {
                id = "undefined_symbol",
                kind = "abi_mismatch",
                severity = "error",
                label = "Incompatibilidade de biblioteca",
                value = "símbolo " .. symbol .. " ausente",
                detail = "A biblioteca foi localizada, mas sua versão não fornece o símbolo esperado.",
                evidence = compactEvidence(line),
                repairable = false,
            })
        end

        local glibcVersion = line:match("GLIBC_([%d%.]+).-not found")
        local glibcxxVersion = line:match("GLIBCXX_([%d%.]+).-not found")
        if glibcVersion or glibcxxVersion then
            local family = glibcVersion and "GLIBC_" or "GLIBCXX_"
            local version = glibcVersion or glibcxxVersion
            addIssue(issues, seen, {
                id = "runtime_abi",
                kind = "runtime_abi",
                severity = "error",
                label = "Runtime incompatível",
                value = family .. version .. " é exigida",
                detail = "O executável foi compilado para uma versão de runtime diferente da disponível.",
                evidence = compactEvidence(line),
                repairable = false,
            })
        end

        if lowered:find("exec format error", 1, true) then
            addIssue(issues, seen, {
                id = "wrong_architecture",
                kind = "wrong_architecture",
                severity = "error",
                label = "Arquitetura incompatível",
                value = "formato do executável não suportado",
                detail = "O binário, o kernel ou a camada de compatibilidade usam arquiteturas diferentes.",
                evidence = compactEvidence(line),
                repairable = false,
            })
        end

        if lowered:find("permission denied", 1, true) then
            addIssue(issues, seen, {
                id = "permission_denied",
                kind = "permissions",
                severity = "error",
                label = "Permissão negada",
                value = "arquivo não pôde ser executado ou lido",
                detail = "O Port Doctor pode restaurar a permissão de execução de launchers, scripts e arquivos ELF.",
                evidence = compactEvidence(line),
                repairable = true,
            })
        end

        if lowered:find("segmentation fault", 1, true) or lowered:find("segfault", 1, true)
            or lowered:find("illegal instruction", 1, true)
            or lowered:find("sigbus", 1, true) or lowered:find("sigsegv", 1, true)
            or lowered:find("sigabrt", 1, true) or lowered:find("bus error", 1, true) then
            addIssue(issues, seen, {
                id = "native_crash",
                kind = "native_crash",
                severity = "error",
                label = "Falha do executável",
                value = lowered:find("sigbus", 1, true) and "falha nativa SIGBUS"
                    or (lowered:find("illegal instruction", 1, true) and "instrução ilegal" or "falha nativa do executável"),
                detail = "É necessário revisar arquitetura, ABI, drivers e o ponto exato da falha; não há correção genérica segura.",
                evidence = compactEvidence(line),
                repairable = false,
            })
        end

        if lowered:find("unable to find game!!", 1, true)
            or (lowered:find("game.droid", 1, true)
                and (lowered:find("failed to load file", 1, true)
                    or lowered:find("fileexists fail", 1, true)
                    or lowered:find("no such file", 1, true))) then
            missingGameDataEvidence = missingGameDataEvidence or compactEvidence(line)
        end

        if lowered:find("failed to create pipewire event context", 1, true)
            or (lowered:find("pw.conf", 1, true) and lowered:find("client.conf", 1, true)) then
            pipewireEvidence = pipewireEvidence or compactEvidence(line)
        end

        if lowered:find("device or resource busy", 1, true)
            and (lowered:find("openaudiodevice", 1, true) or lowered:find("alsa", 1, true)
                or lowered:find("audio device", 1, true)) then
            audioBusyEvidence = audioBusyEvidence or compactEvidence(line)
        end

        if (lowered:find("gptokeyb", 1, true) and lowered:find("killed", 1, true))
            or lowered:find("pkill %-9 %-f gptokeyb")
            or lowered:find("usage:%s*kill%s+%[options%]") then
            cleanupEvidence = cleanupEvidence or compactEvidence(line)
        end

        if lowered:find("game.droid is compressed", 1, true)
            or lowered:find("bitstream/page/packet is not vorbis data", 1, true) then
            compressedGameArchiveEvidence = compressedGameArchiveEvidence or compactEvidence(line)
        end

        local asset = line:match("Cannot locate assets/([^%s]+) in AAsset archive")
            or line:match("Failed to load ([^%s]+%.dat)")
        if asset then
            missingOptionalAsset = missingOptionalAsset or asset
            missingOptionalAssetEvidence = missingOptionalAssetEvidence or compactEvidence(line)
        end

        local reportedMemory = tonumber(line:match("Total memory used%s*=%s*(%d+)"))
        if reportedMemory and reportedMemory <= 8589934592 and reportedMemory > memoryBytes then
            memoryBytes = reportedMemory
            memoryEvidence = compactEvidence(line)
        elseif reportedMemory and reportedMemory > 8589934592 then
            invalidMemoryEvidence = invalidMemoryEvidence or compactEvidence(line)
        end
        if lowered:find("out of memory", 1, true) or lowered:find("oom-killer", 1, true)
            or (lowered:find("killed process", 1, true) and not lowered:find("gptokeyb", 1, true)) then
            memoryEvidence = compactEvidence(line)
            memoryBytes = math.max(memoryBytes, 734003201)
        end
    end

    if pipewireEvidence then
        addIssue(issues, seen, {
            id = "pipewire_unavailable",
            kind = "audio_backend",
            severity = "warn",
            label = "PipeWire indisponível",
            value = "OpenAL não abriu o PipeWire",
            detail = "Em firmwares sem PipeWire, o launcher pode direcionar o OpenAL para ALSA sem instalar pacotes no sistema.",
            evidence = pipewireEvidence,
            repairable = true,
        })
    end

    if audioBusyEvidence then
        addIssue(issues, seen, {
            id = "audio_device_busy",
            kind = "audio_device_busy",
            severity = "error",
            label = "Dispositivo de áudio ocupado",
            value = "ALSA não conseguiu abrir a saída",
            detail = "Outro processo ou servidor de áudio está usando a saída. O jogo FNA pode encerrar quando o AudioEngine falha.",
            evidence = audioBusyEvidence,
            repairable = true,
        })
    end

    if cleanupEvidence then
        addIssue(issues, seen, {
            id = "gptokeyb_cleanup",
            kind = "cleanup_noise",
            severity = "info",
            label = "Encerramento do controle",
            value = "mensagem secundária do gptokeyb",
            detail = "Normalmente aparece depois que o processo principal encerra e não é a causa inicial da falha.",
            evidence = cleanupEvidence,
            repairable = false,
        })
    end


    if memoryEvidence and memoryBytes > 734003200 then
        addIssue(issues, seen, {
            id = "memory_pressure",
            kind = "memory_pressure",
            severity = "error",
            label = "Memória insuficiente",
            value = string.format("jogo usa aproximadamente %.0f MB", memoryBytes / 1048576),
            detail = "O jogo ultrapassa a memória segura do R36S. O Port Doctor pode ativar zram comprimido sem criar swap no cartão SD.",
            evidence = memoryEvidence,
            repairable = true,
        })
    end


    if missingGameDataEvidence then
        addIssue(issues, seen, {
            id = "missing_game_data",
            kind = "missing_game_data",
            severity = "error",
            priority = 100,
            label = "Dados do jogo ausentes",
            value = "game.droid não foi encontrado",
            detail = "O executável e o runtime estão presentes, mas o pacote não contém os dados proprietários do jogo. Instale uma cópia completa e legítima que inclua assets/game.droid ou saves/game.droid.",
            evidence = missingGameDataEvidence,
            repairable = false,
        })
    end

    if compressedGameArchiveEvidence then
        addIssue(issues, seen, {
            id = "compressed_game_archive",
            kind = "compressed_game_archive",
            severity = "error",
            priority = 95,
            label = "Pacote GMLoader incompatível",
            value = "arquivos do jogo estão comprimidos no .port",
            detail = "O runner precisa acessar game.droid, áudio e grupos de recursos diretamente. O Port Doctor pode reconstruir o mesmo arquivo .port no modo armazenado, preservando todo o conteúdo e criando backup.",
            evidence = compressedGameArchiveEvidence,
            repairable = true,
        })
    end
    if localRuntimeEvidence then
        addIssue(issues, seen, {
            id = "local_runtime_rejected",
            kind = "local_runtime_rejected",
            severity = "error",
            priority = 115,
            label = "Runtime local recusado",
            value = tostring(localRuntimeName) .. " não foi aceito pelo launcher",
            detail = "O PortMaster não possui esse runtime no catálogo global, mas o port pode trazer uma imagem SquashFS própria. O Port Doctor só libera a cópia local depois de validar formato e tamanho.",
            evidence = localRuntimeEvidence,
            runtime = localRuntimeName,
            repairable = true,
        })
    end
    if graphicsProviderEvidence then
        addIssue(issues, seen, {
            id = "graphics_provider",
            kind = "graphics_provider",
            severity = "error",
            priority = 112,
            label = "Provedor gráfico incorreto",
            value = "SDL não inicializou EGL/GLES",
            detail = "O executável iniciou, mas o SDL não carregou o driver gráfico do R36S. O Port Doctor pode validar o provedor Mali da mesma arquitetura e configurá-lo apenas neste launcher.",
            evidence = graphicsProviderEvidence,
            repairable = true,
        })
    end
    if corruptJavaArchiveEvidence then
        addIssue(issues, seen, {
            id = "corrupt_java_archive",
            kind = "corrupt_java_archive",
            severity = "error",
            priority = 118,
            label = "Arquivo Java incompleto",
            value = "o Java recusou o JAR do jogo",
            detail = "O patch pode ter preservado os recursos em um arquivo e as classes executáveis em outro. O Port Doctor pode unir somente cópias locais, validar manifesto, classe principal e todo o ZIP, mantendo backup.",
            evidence = corruptJavaArchiveEvidence,
            repairable = true,
        })
    end
    if emptyDisplayDimensionEvidence then
        addIssue(issues, seen, {
            id = "empty_display_dimension",
            kind = "empty_display_dimension",
            severity = "error",
            priority = 105,
            label = "Largura de tela vazia",
            value = "launcher enviou a resolução incompleta",
            detail = "Uma expansão de variável do shell usou sintaxe de recorte no lugar de valor-padrão. O Port Doctor pode corrigir somente essa expressão, com backup.",
            evidence = emptyDisplayDimensionEvidence,
            repairable = true,
        })
    end
    if corruptVorbisEvidence then
        addIssue(issues, seen, {
            id = "corrupt_vorbis_audio",
            kind = "corrupt_vorbis_audio",
            severity = "error",
            priority = 116,
            label = "Áudio do jogo corrompido",
            value = "o decodificador Vorbis recusou as faixas",
            detail = "A compactação anterior terminou sem um codificador funcional e substituiu os áudios originais. É necessário recolocar o data.win legítimo para gerar game.droid novamente; os áudios perdidos não podem ser inventados nem baixados.",
            evidence = corruptVorbisEvidence,
            repairable = false,
        })
    end
    if wrongNativeArchitectureEvidence then
        addIssue(issues, seen, {
            id = "wrong_native_architecture",
            kind = "wrong_native_architecture",
            severity = "error",
            priority = 117,
            label = "Biblioteca nativa incompatível",
            value = "o JAR contém uma biblioteca x86 de 32 bits",
            detail = "O Java iniciou, mas o patch não forneceu a biblioteca AArch64 exigida pelo R36S. É necessário recolocar o JAR legítimo original para o patch oficial gerar os binários corretos; forçar uma biblioteca de outra versão é inseguro.",
            evidence = wrongNativeArchitectureEvidence,
            repairable = false,
        })
    end
    if invalidMemoryEvidence then
        addIssue(issues, seen, {
            id = "invalid_memory_counter",
            kind = "invalid_memory_counter",
            severity = "info",
            label = "Contador de memória inválido",
            value = "valor impossível ignorado",
            detail = "Algumas versões do GMLoader imprimem mallinfo com campos incompatíveis em AArch64. Esse número não representa o consumo real e não ativará zram.",
            evidence = invalidMemoryEvidence,
            repairable = false,
        })
    end
    if missingOptionalAssetEvidence then
        addIssue(issues, seen, {
            id = "missing_optional_asset",
            kind = "missing_optional_asset",
            severity = "warn",
            label = "Recurso adicional ausente",
            value = tostring(missingOptionalAsset) .. " não está no pacote",
            detail = "O jogo pode continuar sem esse grupo de vídeo, menu ou áudio, mas o recurso correspondente ficará indisponível. O Port Doctor não cria nem baixa dados proprietários ausentes.",
            evidence = missingOptionalAssetEvidence,
            repairable = false,
        })
    end

    sortIssues(issues)
    return issues
end

function logdoctor.append(issues, issue)
    issues = issues or {}
    local seen = {}
    for _, current in ipairs(issues) do
        seen[current.id .. ":" .. tostring(current.badPath or current.library or "")] = true
    end
    addIssue(issues, seen, issue)
    sortIssues(issues)
    return issues
end

function logdoctor.primary(issues)
    return issues and issues[1] or nil
end

return logdoctor
