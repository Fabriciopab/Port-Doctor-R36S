local diagnostics = require("src.diagnostics")
local util = require("src.util")

local repairs = {}

local function sudoPrefix()
    local value = util.trim(os.getenv("PORTDOCTOR_ESUDO") or "")
    if value ~= "" and value:match("^[%w%._/%s%-]+$") then
        if value:match('sudo%s') or value:match('sudo$') then value=value..' -n' end
        return value .. " "
    end
    if util.trim(util.run("command -v sudo 2>/dev/null")) ~= "" then
        return "sudo -n "
    end
    return ""
end

local function harbourmasterPath()
    return diagnostics.portMasterHome() .. "/harbourmaster"
end

local function helperPath()
    local home = os.getenv("PORTDOCTOR_HOME") or ""
    return home ~= "" and (home .. "/tools/repair_port.py") or ""
end

local function runtimeInstalled(runtime, details)
    local home = diagnostics.portMasterHome()
    local base = tostring(runtime or ""):gsub("%.squashfs$", "")
    if util.testFile(home .. "/runtimes/" .. runtime .. "/love.txt")
        or util.testFile(home .. "/runtimes/" .. runtime)
        or util.testFile(home .. "/libs/" .. runtime) then
        return true
    end
    for _, path in ipairs(details and details.localRuntimes or {}) do
        if util.basename(path) == runtime then
            return true
        end
    end
    local output = util.run("find " .. util.shellQuote(home .. "/libs")
        .. " " .. util.shellQuote(home .. "/runtimes")
        .. " -maxdepth 2 -name " .. util.shellQuote(base .. "*.squashfs") .. " -print -quit 2>/dev/null")
    return output ~= ""
end

local function validRuntime(runtime)
    return runtime and runtime:match("^[%w%._%-]+$") ~= nil
end

local function permissionsCommand(details)
    if not details or not details.path then
        return nil
    end

    local prefix = sudoPrefix()
    local commands = {}
    for _, launcher in ipairs(details.launchers or {}) do
        commands[#commands + 1] = prefix .. "chmod u+x " .. util.shellQuote(launcher)
    end
    commands[#commands + 1] = prefix .. "find " .. util.shellQuote(details.path)
        .. " -maxdepth 6 -type f -name '*.sh' -exec chmod u+x {} +"
    commands[#commands + 1] = prefix .. "find " .. util.shellQuote(details.path)
        .. " -maxdepth 6 -type f -exec sh -c 'file -b \"$1\" 2>/dev/null | grep -q \"^ELF \" && chmod u+x \"$1\" || true' sh {} \\;"
    return table.concat(commands, " && ")
end

local function runtimeCommands(details, onlyMissing)
    if not details then
        return {}, {}
    end
    local missing = {}
    local commands = {}
    local hm = harbourmasterPath()
    if not util.testFile(hm) then
        return commands, missing
    end
    for _, runtime in ipairs(details.runtimes or {}) do
        if validRuntime(runtime) then
            local installed = runtimeInstalled(runtime, details)
            if not installed then
                missing[#missing + 1] = runtime
            end
            if not onlyMissing or not installed then
                commands[#commands + 1] = sudoPrefix() .. util.shellQuote(hm)
                    .. " --no-colour --no-check runtime_check " .. util.shellQuote(runtime)
            end
        end
    end
    return commands, missing
end

local function findIssue(details, kind)
    for _, issue in ipairs(details and details.issues or {}) do
        if issue.kind == kind then
            return issue
        end
    end
    return nil
end

local function architectureFor(details, issue)
    local badPath = issue and issue.badPath or ""
    if badPath:find("aarch64", 1, true) then
        return "aarch64"
    elseif badPath:find("arm%-linux%-gnueabihf") then
        return "armhf"
    end
    for _, architecture in ipairs(details and details.architectures or {}) do
        if architecture == "aarch64" or architecture == "armhf" or architecture == "x86_64" then
            return architecture
        end
    end
    return nil
end

local function helperBase(command, details)
    local launcher = details and details.launchers and details.launchers[1]
    local helper = helperPath()
    if not launcher or helper == "" or not util.testFile(helper) then
        return nil
    end
    return "python3 " .. util.shellQuote(helper) .. " " .. command
        .. " --launcher " .. util.shellQuote(launcher)
        .. " --port-home " .. util.shellQuote(details.path)
        .. " --doctor-home " .. util.shellQuote(os.getenv("PORTDOCTOR_HOME") or "")
end

local function repairLibraryCommand(details, issue)
    local architecture = architectureFor(details, issue)
    local library = issue and issue.library
    local base = helperBase("repair-library", details)
    if not details then
        return nil, "analise um port primeiro"
    elseif not details.launchers or #details.launchers == 0 then
        return nil, "launcher não associado"
    elseif helperPath() == "" or not util.testFile(helperPath()) then
        return nil, "componente de reparo ausente"
    elseif not architecture then
        return nil, "arquitetura não identificada"
    elseif not library then
        return nil, "biblioteca não identificada"
    elseif not base then
        return nil, "reparo não pôde ser preparado"
    end
    local commands = runtimeCommands(details, false)
    local installSquashfs = "command -v unsquashfs >/dev/null 2>&1 || ("
        .. sudoPrefix() .. "apt-get update && " .. sudoPrefix()
        .. "apt-get install -y --no-install-recommends squashfs-tools)"
    commands[#commands + 1] = installSquashfs
    commands[#commands + 1] = base
        .. " --pm-home " .. util.shellQuote(diagnostics.portMasterHome())
        .. " --library " .. util.shellQuote(library)
        .. " --architecture " .. util.shellQuote(architecture)
    for _, runtime in ipairs(details.runtimes or {}) do
        if validRuntime(runtime) then
            commands[#commands] = commands[#commands] .. " --runtime " .. util.shellQuote(runtime)
        end
    end
    local badPath = issue and issue.badPath or ""
    if badPath:sub(1, 1) == "/" then
        commands[#commands] = commands[#commands] .. " --bad-path " .. util.shellQuote(badPath)
        local installPatchelf = "command -v patchelf >/dev/null 2>&1 || ("
            .. sudoPrefix() .. "apt-get update && " .. sudoPrefix()
            .. "apt-get install -y --no-install-recommends patchelf)"
        table.insert(commands, #commands, installPatchelf)
    end
    local failedExecutable = issue and issue.executable or ""
    if failedExecutable ~= "" then
        commands[#commands] = commands[#commands] .. " --failed-executable " .. util.shellQuote(failedExecutable)
    end
    return table.concat(commands, " && "), nil
end

local function audioCommand(details)
    return helperBase("audio-alsa", details)
end

local function audioBusyCommand(details)
    return helperBase("audio-busy", details)
end

local function memoryCommand(details)
    return helperBase("memory-zram", details)
end

local function gameDataCommand(details)
    local source = details and details.gameDataCandidates and details.gameDataCandidates[1]
    local base = helperBase("install-game-data", details)
    if not source or source == "" or not base then
        return nil
    end
    return base .. " --source " .. util.shellQuote(source)
end

local function repackGameArchiveCommand(details)
    return helperBase("repack-game-archive", details)
end

local function launcherHeaderCommand(details)
    return helperBase("repair-launcher-header", details)
end

local function localRuntimeCommand(details, issue)
    local base = helperBase("repair-local-runtime", details)
    local runtime = issue and issue.runtime
    if not base or not validRuntime(runtime) then
        return nil
    end
    return base .. " --runtime " .. util.shellQuote(runtime)
end

local function graphicsProviderCommand(details)
    local base = helperBase("graphics-provider", details)
    local architecture = architectureFor(details)
    if not base or (architecture ~= "aarch64" and architecture ~= "armhf") then
        return nil
    end
    return base .. " --architecture " .. util.shellQuote(architecture)
end

local function javaArchiveCommand(details)
    return helperBase("repair-java-archive", details)
end

local function shellDefaultsCommand(details)
    return helperBase("repair-shell-defaults", details)
end

local function autoRepairCommand(details)
    local base = helperBase("auto-repair", details)
    if not details then
        return nil, "analise um port primeiro"
    elseif not details.launchers or #details.launchers == 0 then
        return nil, "launcher não associado"
    elseif not base then
        return nil, "componente de reparo ausente"
    end
    local commands = runtimeCommands(details, true)
    commands[#commands + 1] = base .. " --pm-home " .. util.shellQuote(diagnostics.portMasterHome())
    for _, architecture in ipairs(details.architectures or {}) do
        if architecture == "aarch64" or architecture == "armhf" or architecture == "x86_64" then
            commands[#commands] = commands[#commands] .. " --architecture " .. util.shellQuote(architecture)
        end
    end
    for _, runtime in ipairs(details.runtimes or {}) do
        if validRuntime(runtime) then
            commands[#commands] = commands[#commands] .. " --runtime " .. util.shellQuote(runtime)
        end
    end
    return table.concat(commands, " && "), nil
end

local function backupAvailable(details)
    local home = os.getenv("PORTDOCTOR_HOME") or ""
    if home == "" or not details then
        return false
    end
    local slug = tostring(details.name or "port"):lower():gsub("[^%w%._%-]+", "-"):gsub("^[%-%.]+", ""):gsub("[%-%.]+$", "")
    local root = home .. "/conf/backups/" .. (slug ~= "" and slug or "port")
    local output = util.run("grep -rl '\"restored\": false' " .. util.shellQuote(root)
        .. " --include manifest.json 2>/dev/null | head -n 1")
    return output ~= ""
end

local function restoreCommand(details)
    if not backupAvailable(details) then
        return nil
    end
    return helperBase("restore", details)
end

local function verifyCommand(details)
    if not backupAvailable(details) then
        return nil
    end
    return helperBase("verify", details)
end

function repairs.actions(details)
    local hm = harbourmasterPath()
    local hmAvailable = util.testFile(hm)
    local permissionCount = details and #(details.nonExecutable or {}) or 0
    local missingRuntimeCommands, missingRuntimes = runtimeCommands(details, true)
    local runtimeCommand = #missingRuntimeCommands > 0 and table.concat(missingRuntimeCommands, " && ") or nil
    local selected = details and details.name or "nenhum port analisado"
    local actions = {}

    local truncated = findIssue(details, "truncated_library") or findIssue(details, "missing_library")
    local audioIssue = findIssue(details, "audio_backend")
    local audioBusyIssue = findIssue(details, "audio_device_busy")
    local memoryIssue = findIssue(details, "memory_pressure")
    local missingGameData = findIssue(details, "missing_game_data")
    local incompatiblePlatform = findIssue(details, "platform_incompatible")
    local compressedGameArchive = findIssue(details, "compressed_game_archive")
    local invalidLauncherHeader = findIssue(details, "invalid_launcher_header")
    local localRuntimeIssue = findIssue(details, "local_runtime_rejected")
    local graphicsProviderIssue = findIssue(details, "graphics_provider")
    local corruptJavaArchiveIssue = findIssue(details, "corrupt_java_archive")
    local emptyDisplayDimensionIssue = findIssue(details, "empty_display_dimension")
    local corruptVorbisIssue = findIssue(details, "corrupt_vorbis_audio")
    local wrongNativeArchitectureIssue = findIssue(details, "wrong_native_architecture")
    local nativeCrash = findIssue(details, "native_crash")
    local availableGameData = gameDataCommand(details)
    local automaticIssue = truncated or memoryIssue or audioBusyIssue or audioIssue
        or compressedGameArchive
        or invalidLauncherHeader
        or localRuntimeIssue
        or graphicsProviderIssue
        or corruptJavaArchiveIssue
        or emptyDisplayDimensionIssue
        or (missingGameData and availableGameData)
        or (not nativeCrash and details and #(details.missing or {}) > 0)
    local automatic, automaticReason = autoRepairCommand(details)
    if not automaticIssue then
        automatic = nil
        if missingGameData then
            automaticReason = "game.droid não foi incluído no pacote"
        elseif corruptVorbisIssue then
            automaticReason = "recoloque o data.win original para recuperar os áudios"
        elseif wrongNativeArchitectureIssue then
            automaticReason = "recoloque o desktop-1.0.jar original para gerar a biblioteca AArch64"
        elseif incompatiblePlatform then
            automaticReason = "este build foi feito para H700/ROCKNIX"
        elseif nativeCrash then
            automaticReason = "falha nativa; veja o diagnóstico detalhado"
        else
            automaticReason = details and "nenhuma falha segura reconhecida no log" or "analise um port primeiro"
        end
    end
    actions[#actions + 1] = {
        id = "auto_repair",
        label = "Corrigir port automaticamente",
        value = automatic and "aplicar reparo; teste manual necessário" or automaticReason,
        detail = automatic
            and "Cria um plano, fecha dependências transitivas, usa somente fontes validadas e executa o pré-teste do carregador."
            or ("Indisponível: " .. tostring(automaticReason) .. "."),
        enabled = automatic ~= nil,
        disabledReason = automaticReason,
        command = automatic,
        requiresTest = true,
        confirmation = "Executar o reparo automático protegido para " .. selected .. "? Todas as alterações terão backup.",
    }

    if nativeCrash then
        local command=helperBase('inspect-native',details)
        actions[#actions+1]={id='inspect_native',label='Investigar falha nativa',value='SIGBUS / SIGSEGV',
            detail='Lê os registros nativos com versão, sinal e horário. Não altera saves, bibliotecas ou configurações. X salva o resultado para análise.',
            enabled=command~=nil,command=command,immediate=true}
    end

    if invalidLauncherHeader then
        local command = launcherHeaderCommand(details)
        actions[#actions + 1] = {
            id = "invalid_launcher_header",
            label = "Corrigir início do launcher",
            value = command and "shebang na primeira linha" or "launcher ausente",
            detail = "Remove somente texto ou linhas vazias anteriores ao #!/bin/bash, preservando o restante do script e criando backup.",
            enabled = command ~= nil,
            command = command,
            requiresTest = true,
            confirmation = "Corrigir o cabeçalho do launcher de " .. selected .. "?",
            disabledReason = command and nil or "launcher ou componente de reparo ausente",
        }
    end

    if localRuntimeIssue then
        local command = localRuntimeCommand(details, localRuntimeIssue)
        actions[#actions + 1] = {
            id = "local_runtime_rejected",
            label = "Usar runtime incluído no port",
            value = command and tostring(localRuntimeIssue.runtime) .. " validado" or "cópia local inválida ou ausente",
            detail = "Valida a imagem SquashFS local e ajusta somente a verificação do launcher. Não instala nem sobrescreve arquivos do sistema.",
            enabled = command ~= nil,
            command = command,
            requiresTest = true,
            confirmation = "Validar e liberar o runtime local de " .. selected .. "? O launcher original ficará no backup.",
            disabledReason = command and nil or "runtime local válido ou componente de reparo ausente",
        }
    end

    if graphicsProviderIssue then
        local command = graphicsProviderCommand(details)
        actions[#actions + 1] = {
            id = "graphics_provider",
            label = "Corrigir driver gráfico do port",
            value = command and "provedor Mali validado" or "provedor compatível não identificado",
            detail = "Confere arquitetura e símbolos EGL/GLES do driver Mali e configura o SDL somente neste launcher; não substitui drivers do sistema.",
            enabled = command ~= nil,
            command = command,
            requiresTest = true,
            confirmation = "Validar e configurar o provedor gráfico do R36S para " .. selected .. "?",
            disabledReason = command and nil or "arquitetura, launcher ou componente de reparo não identificado",
        }
    end

    if corruptJavaArchiveIssue then
        local command = javaArchiveCommand(details)
        actions[#actions + 1] = {
            id = "corrupt_java_archive",
            label = "Reconstruir arquivo Java",
            value = command and "manifesto + classes + recursos" or "base íntegra não identificada",
            detail = "Une o JAR-base íntegro aos recursos que sobreviveram ao patch, valida todo o ZIP e preserva o arquivo atual no backup.",
            enabled = command ~= nil,
            command = command,
            requiresTest = true,
            confirmation = "Reconstruir o arquivo Java de " .. selected .. " usando somente os dados locais preservados?",
            disabledReason = command and nil or "launcher ou componente de reparo ausente",
        }
    end

    if emptyDisplayDimensionIssue then
        local command = shellDefaultsCommand(details)
        actions[#actions + 1] = {
            id = "empty_display_dimension",
            label = "Corrigir resolução do launcher",
            value = command and "usar largura e altura do aparelho" or "launcher ausente",
            detail = "Corrige a sintaxe do valor-padrão que deixou uma dimensão vazia; mantém o launcher original no backup.",
            enabled = command ~= nil,
            command = command,
            requiresTest = true,
            confirmation = "Corrigir a resolução enviada pelo launcher de " .. selected .. "?",
            disabledReason = command and nil or "launcher ou componente de reparo ausente",
        }
    end

    if compressedGameArchive then
        local command = repackGameArchiveCommand(details)
        actions[#actions + 1] = {
            id = "compressed_game_archive",
            label = "Reconstruir pacote GMLoader",
            value = command and "modo armazenado + backup" or "launcher ausente",
            detail = "Recria o .port sem compressão para permitir leitura direta de game.droid, áudio e grupos de recursos. O original fica no backup.",
            enabled = command ~= nil,
            command = command,
            requiresTest = true,
            confirmation = "Reconstruir o arquivo .port de " .. selected .. " sem compressão? O processo pode levar alguns minutos.",
            disabledReason = command and nil or "launcher ou componente de reparo ausente",
        }
    end

    if missingGameData then
        actions[#actions + 1] = {
            id = "missing_game_data",
            label = "Instalar dados legítimos do jogo",
            value = availableGameData and "cópia local encontrada" or "game.droid ausente",
            detail = availableGameData
                and "Valida e instala em saves/game.droid a cópia encontrada dentro da própria pasta do port, com backup."
                or "Use um pacote completo que contenha assets/game.droid ou coloque sua cópia legítima dentro da pasta do port. O Port Doctor não baixa dados proprietários.",
            enabled = availableGameData ~= nil,
            command = availableGameData,
            requiresTest = true,
            confirmation = "Instalar a cópia local de game.droid para " .. selected .. "?",
            disabledReason = availableGameData and nil or "o arquivo proprietário game.droid precisa ser fornecido pelo usuário",
        }
    end

    if incompatiblePlatform then
        actions[#actions + 1] = {
            id = "platform_incompatible",
            label = "Usar build compatível com R36S",
            value = "H700/ROCKNIX não compatível",
            detail = "Procure uma versão compilada para RK3326/dArkOS. Trocar bibliotecas ou permissões não corrige o backend KMSDRM deste executável.",
            enabled = false,
            disabledReason = "é necessário outro executável compilado para RK3326/dArkOS",
        }
    end

    if truncated then
        local command, unavailableReason = repairLibraryCommand(details, truncated)
        actions[#actions + 1] = {
            id = "repair_library",
            label = "Reparar " .. tostring(truncated.library or "biblioteca"),
            value = command and "fonte local validada" or unavailableReason,
            detail = command and (truncated.badPath and truncated.badPath:sub(1, 1) == "/"
                and "Copia uma biblioteca válida localmente e troca no executável a dependência absoluta incorreta; nunca sobrescreve /lib."
                or "Procura nos runtimes e ports instalados, valida o conjunto ELF com o carregador e copia para libs.portdoctor; nunca sobrescreve /lib.")
                or ("Indisponível: " .. tostring(unavailableReason or "motivo não identificado") .. "."),
            enabled = command ~= nil,
            disabledReason = unavailableReason,
            command = command,
            requiresTest = true,
            confirmation = "Buscar um conjunto compatível nos runtimes e ports instalados, testá-lo e criar um reparo local para " .. selected .. "?",
        }
    end

    if audioIssue then
        local command = audioCommand(details)
        actions[#actions + 1] = {
            id = "audio_alsa",
            label = "Usar áudio ALSA",
            value = command and "reversível" or "launcher ausente",
            detail = "Evita o PipeWire indisponível definindo ALSOFT_DRIVERS=alsa apenas neste launcher.",
            enabled = command ~= nil,
            command = command,
            requiresTest = true,
            confirmation = "Criar backup e direcionar o OpenAL de " .. selected .. " para ALSA?",
        }
    end

    if audioBusyIssue then
        local command = audioBusyCommand(details)
        actions[#actions + 1] = {
            id = "audio_busy",
            label = "Liberar dispositivo de áudio",
            value = command and "reversível" or "launcher ausente",
            detail = "Usa Pulse quando disponível; senão seleciona ALSA/dmix e encerra somente clientes de áudio conhecidos do usuário.",
            enabled = command ~= nil,
            command = command,
            requiresTest = true,
            confirmation = "Criar backup e corrigir a saída de áudio ocupada de " .. selected .. "?",
        }
    end

    if memoryIssue then
        local command = memoryCommand(details)
        actions[#actions + 1] = {
            id = "memory_zram",
            label = "Ativar memória comprimida",
            value = command and "768 MB zram" or "launcher ausente",
            detail = "Cria swap comprimido na RAM somente quando necessário; não grava swap no cartão SD.",
            enabled = command ~= nil,
            disabledReason = command and nil or "launcher ou componente zram ausente",
            command = command,
            requiresTest = true,
            confirmation = "Ativar zram e ajustar o launcher de " .. selected .. " para evitar encerramento por falta de memória?",
        }
    end

    actions[#actions + 1] = {
        id = "runtime",
        label = "Instalar runtimes oficiais",
        value = #missingRuntimes > 0 and table.concat(missingRuntimes, ", ") or "nenhum ausente",
        detail = "Usa runtime_check do HarbourMaster; não altera bibliotecas do sistema-base.",
        enabled = runtimeCommand ~= nil,
        command = runtimeCommand,
        confirmation = "Baixar os runtimes declarados para " .. selected .. "?",
    }

    actions[#actions + 1] = {
        id = "permissions",
        label = "Corrigir permissões",
        value = permissionCount > 0 and (permissionCount .. " itens") or "verificar",
        detail = "Aplica execução somente a launchers, scripts .sh e arquivos ELF de " .. selected .. ".",
        enabled = details ~= nil,
        command = permissionsCommand(details),
        confirmation = "Corrigir permissões de " .. selected .. "?",
    }

    local verify = verifyCommand(details)
    local verifyReason = details and "nenhum reparo foi aplicado a este port" or "analise um port primeiro"
    actions[#actions + 1] = {
        id = "verify",
        label = "Verificar resultado do reparo",
        value = verify and "comparar novo log" or "aplique um reparo antes",
        detail = verify
            and "Depois do teste, procura falhas no novo log e nos registros nativos. Sem falha detectada ainda exige confirmação visual; nunca comprova que o jogo funciona só pela ausência de erros."
            or "Esta ação não faz o reparo. Primeiro execute uma ação Reparar ou Usar áudio acima e depois teste o jogo.",
        enabled = verify ~= nil,
        disabledReason = verify and nil or verifyReason,
        command = verify,
        immediate = true,
    }

    local restore = restoreCommand(details)
    local restoreReason = details and "nenhum backup de reparo disponível" or "analise um port primeiro"
    actions[#actions + 1] = {
        id = "restore",
        label = "Desfazer último reparo",
        value = restore and "backup disponível" or "sem backup",
        detail = "Restaura o launcher e remove somente arquivos criados pelo Port Doctor.",
        enabled = restore ~= nil,
        disabledReason = restore and nil or restoreReason,
        command = restore,
        confirmation = "Restaurar o último backup do Port Doctor para " .. selected .. "?",
    }

    actions[#actions + 1] = {
        id = "catalog",
        label = "Atualizar catálogos",
        value = hmAvailable and "online" or "indisponível",
        detail = "Baixa os índices mais recentes das fontes configuradas no PortMaster.",
        enabled = hmAvailable,
        command = hmAvailable and (sudoPrefix() .. util.shellQuote(hm) .. " --no-colour update all") or nil,
        confirmation = "Atualizar os catálogos do PortMaster pela internet?",
    }

    actions[#actions + 1] = {
        id = "backend",
        label = "Atualizar HarbourMaster",
        value = hmAvailable and "verificar" or "indisponível",
        detail = "Atualiza o gerenciador e suas bibliotecas após conferir os hashes publicados.",
        enabled = hmAvailable,
        command = hmAvailable and (sudoPrefix() .. util.shellQuote(hm) .. " --no-colour --no-check upgrade harbourmaster") or nil,
        confirmation = "Verificar e atualizar o backend HarbourMaster?",
    }

    return actions
end

return repairs
