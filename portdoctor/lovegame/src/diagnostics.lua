local util = require("src.util")
local logdoctor = require("src.logdoctor")
local recipes = require("src.recipes")

local diagnostics = {}

local function item(id, group, label, status, value, detail)
    return {
        id = id,
        group = group,
        label = label,
        status = status,
        value = value or "",
        detail = detail or "",
    }
end

local function commandValue(command, fallback)
    local output = util.run(command)
    if output == "" then
        return fallback or "não detectado"
    end
    return output
end

local function addUnique(list, seen, value)
    if value and value ~= "" and not seen[value] then
        seen[value] = true
        list[#list + 1] = value
    end
end

local function sortedKeys(map)
    local keys = {}
    for key in pairs(map or {}) do
        keys[#keys + 1] = key
    end
    table.sort(keys)
    return keys
end

local function normalizedName(value)
    return tostring(value or ""):lower():gsub("%.sh$", ""):gsub("[^%w]", "")
end

local function findPortLaunchers(name, root)
    local allText = util.run("find " .. util.shellQuote(root)
        .. " -maxdepth 1 -type f -name '*.sh' -print 2>/dev/null | sort")
    local allLaunchers = util.lines(allText)
    local selected = {}
    local seen = {}

    local contentMatches = util.run("find " .. util.shellQuote(root)
        .. " -maxdepth 1 -type f -name '*.sh' -exec grep -IlFi -- "
        .. util.shellQuote(name) .. " {} + 2>/dev/null | head -n 4")
    for _, launcher in ipairs(util.lines(contentMatches)) do
        addUnique(selected, seen, launcher)
    end

    local acceptedNames = { [normalizedName(name)] = true }
    local recipe = recipes.forPort(name)
    if recipe and recipe.title then
        acceptedNames[normalizedName(recipe.title)] = true
    end
    for _, launcher in ipairs(allLaunchers) do
        if acceptedNames[normalizedName(util.basename(launcher))] then
            addUnique(selected, seen, launcher)
        end
    end
    return table.concat(selected, "\n")
end

local function portMasterHome()
    local configured = os.getenv("PORTMASTER_HOME")
    local candidates = {
        configured,
        "/opt/system/Tools/PortMaster",
        "/opt/tools/PortMaster",
        "/roms/tools/PortMaster",
        "/roms/ports/PortMaster",
    }
    for _, path in ipairs(candidates) do
        if path and path ~= "" and util.testFile(path .. "/control.txt") then
            return path
        end
    end
    return configured or "/roms/ports/PortMaster"
end

function diagnostics.portMasterHome()
    return portMasterHome()
end

function diagnostics.systemTasks(renderer)
    local tasks = {}

    tasks[#tasks + 1] = function()
        local arch = commandValue("uname -m", "desconhecida")
        local good = arch:match("aarch64") or arch:match("armv7") or arch:match("armhf")
        return item("arch", "system", "Arquitetura nativa", good and "ok" or "warn", arch,
            "Arquitetura informada pelo kernel e pelo userspace principal.")
    end

    tasks[#tasks + 1] = function()
        local kernel = commandValue("uname -r", "desconhecido")
        return item("kernel", "system", "Kernel Linux", "info", kernel,
            "Versão do kernel em execução.")
    end

    tasks[#tasks + 1] = function()
        local release = util.firstLine(commandValue("sed -n 's/^PRETTY_NAME=//p' /etc/os-release | tr -d '\"'", "Linux"))
        return item("os", "system", "Sistema", "info", release,
            "Distribuição detectada em /etc/os-release.")
    end

    tasks[#tasks + 1] = function()
        local glibc = commandValue("getconf GNU_LIBC_VERSION 2>/dev/null || ldd --version | head -n 1", "não detectada")
        local version = glibc:match("(%d+%.%d+)")
        return item("glibc", "system", "glibc", version and "ok" or "warn", glibc,
            "Usada por executáveis Linux vinculados dinamicamente.")
    end

    tasks[#tasks + 1] = function()
        local memory = commandValue("awk '/MemTotal/ {printf \"%.0f MB\", $2/1024}' /proc/meminfo", "não detectada")
        return item("memory", "system", "Memória RAM", "info", memory,
            "Memória física total informada pelo kernel.")
    end

    tasks[#tasks + 1] = function()
        local root = os.getenv("PORTS_ROOT") or "/roms/ports"
        local storage = commandValue("df -h " .. util.shellQuote(root) .. " | awk 'NR==2 {print $4 \" livres de \" $2}'", "não detectado")
        return item("storage", "system", "Armazenamento", "info", storage,
            "Espaço disponível na partição que contém os ports.")
    end

    tasks[#tasks + 1] = function()
        local loader = "/lib/ld-linux-armhf.so.3"
        local ok = util.testFile(loader, true)
        local version = commandValue("dpkg-query -W -f='${Version}' libc6:armhf 2>/dev/null", "")
        local value = ok and (version ~= "" and "disponível · libc " .. version or "disponível") or "ausente"
        return item("armhf", "system", "Compatibilidade ARMHF", ok and "ok" or "warn", value,
            ok and loader or "Ports ARM de 32 bits não poderão iniciar sem o carregador ARMHF.")
    end

    tasks[#tasks + 1] = function()
        local home = portMasterHome()
        local version = os.getenv("PM_VERSION") or commandValue(
            "grep -Rhs '^PM_VERSION=' /opt/system/Tools/PortMaster 2>/dev/null | head -n 1 | cut -d= -f2-", "")
        local found = util.testFile(home .. "/control.txt")
        return item("portmaster", "system", "PortMaster", found and "ok" or "warn",
            version ~= "" and version or (found and "instalado" or "não localizado"),
            found and home or "Integração usada para controles, runtime e restauração do frontend.")
    end

    tasks[#tasks + 1] = function()
        local home = portMasterHome()
        local harbourmaster = home .. "/harbourmaster"
        local found = util.testFile(harbourmaster)
        return item("hm_backend", "pm", "HarbourMaster", found and "ok" or "error",
            found and "disponível" or "ausente", harbourmaster)
    end

    tasks[#tasks + 1] = function()
        local home = portMasterHome()
        local output = commandValue("find " .. util.shellQuote(home .. "/runtimes")
            .. " -mindepth 1 -maxdepth 1 -type d -printf '%f\\n' 2>/dev/null | sort", "")
        local runtimes = util.lines(output)
        return item("pm_runtimes", "pm", "Runtimes instalados", #runtimes > 0 and "ok" or "warn",
            tostring(#runtimes), #runtimes > 0 and table.concat(runtimes, ", ") or "Nenhum runtime em runtimes/.")
    end

    tasks[#tasks + 1] = function()
        local home = portMasterHome()
        local count = commandValue("find " .. util.shellQuote(home .. "/libs") .. " "
            .. util.shellQuote(home .. "/runtimes") .. " -type f 2>/dev/null | wc -l", "0")
        return item("pm_files", "pm", "Arquivos de runtime", tonumber(count) and tonumber(count) > 0 and "ok" or "warn",
            count, "Bibliotecas e imagens de runtime gerenciadas pelo PortMaster.")
    end

    tasks[#tasks + 1] = function()
        local home = portMasterHome()
        local catalog = commandValue("find " .. util.shellQuote(home)
            .. " -maxdepth 3 -type f \\( -name 'ports.json' -o -name 'sources.json' -o -name 'ports_info.json' \\) 2>/dev/null | wc -l", "0")
        return item("pm_catalog", "pm", "Catálogos locais", tonumber(catalog) and tonumber(catalog) > 0 and "ok" or "warn",
            catalog, "Use Reparos para atualizar os índices por meio do HarbourMaster.")
    end

    tasks[#tasks + 1] = function()
        local nodes = {}
        for _, path in ipairs({ "/dev/dri/card0", "/dev/mali0", "/dev/fb0" }) do
            if util.testFile(path) then
                nodes[#nodes + 1] = util.basename(path)
            end
        end
        return item("video_nodes", "av", "Dispositivos gráficos", #nodes > 0 and "ok" or "error",
            #nodes > 0 and table.concat(nodes, ", ") or "nenhum encontrado",
            "Nós de dispositivo usados por KMS/DRM, Mali e framebuffer.")
    end

    tasks[#tasks + 1] = function()
        local output = commandValue("ldconfig -p 2>/dev/null | grep -E 'libSDL2-2.0.so.0|libEGL.so.1|libGLESv(1_CM|2).so'", "")
        local haveSDL = output:find("libSDL2%-2%.0%.so%.0") ~= nil
        local haveEGL = output:find("libEGL%.so%.1") ~= nil
        local haveGLES = output:find("libGLES") ~= nil
        local count = (haveSDL and 1 or 0) + (haveEGL and 1 or 0) + (haveGLES and 1 or 0)
        local value = string.format("SDL2 %s · EGL %s · GLES %s",
            haveSDL and "OK" or "—", haveEGL and "OK" or "—", haveGLES and "OK" or "—")
        return item("graphics_libs", "av", "Bibliotecas gráficas", count == 3 and "ok" or "warn", value,
            output ~= "" and output or "Nenhuma entrada correspondente encontrada em ldconfig.")
    end

    tasks[#tasks + 1] = function()
        local output = commandValue("ldconfig -p 2>/dev/null | grep 'libasound.so.2'", "")
        local have = output:find("libasound%.so%.2") ~= nil
        local armhf = output:find("hard%-float") ~= nil
        local value = have and (armhf and "AArch64 + ARMHF" or "disponível") or "ausente"
        return item("audio", "av", "ALSA", have and "ok" or "warn", value,
            output ~= "" and output or "libasound.so.2 não foi encontrada em ldconfig.")
    end

    tasks[#tasks + 1] = function()
        local uinput = util.testFile("/dev/uinput")
        local devices = commandValue("find /dev/input -maxdepth 1 -name 'event*' 2>/dev/null | wc -l", "0")
        return item("input", "av", "Controles", tonumber(devices) and tonumber(devices) > 0 and "ok" or "warn",
            devices .. " entradas · uinput " .. (uinput and "OK" or "—"),
            "Eventos físicos e dispositivo virtual usado pelo gptokeyb.")
    end

    tasks[#tasks + 1] = function()
        local name = renderer and renderer.name or "não disponível"
        local detail = renderer and table.concat({ renderer.version or "", renderer.vendor or "", renderer.device or "" }, " · ") or ""
        return item("renderer", "av", "Renderizador ativo", name ~= "não disponível" and "ok" or "warn", name, detail)
    end

    tasks[#tasks + 1] = function()
        local width, height = love.graphics.getDimensions()
        return item("display", "av", "Área de desenho", "ok", string.format("%d × %d", width, height),
            "Resolução entregue pelo runtime Love2D.")
    end

    return tasks
end

function diagnostics.scanPorts()
    local root = os.getenv("PORTS_ROOT") or "/roms/ports"
    local command = "find " .. util.shellQuote(root)
        .. " -mindepth 1 -maxdepth 1 -type d -printf '%f\\n' 2>/dev/null | sort"
    local output = util.run(command)
    local ports = {}

    for _, name in ipairs(util.lines(output)) do
        if name ~= "PortMaster" and name ~= "portdoctor" and name:sub(1, 1) ~= "." then
            ports[#ports + 1] = name
        end
    end

    return ports, root
end

function diagnostics.analyzePort(name, root)
    root = root or os.getenv("PORTS_ROOT") or "/roms/ports"
    local path = root .. "/" .. name
    local quoted = util.shellQuote(path)
    local results = {}

    results[#results + 1] = item("port_path", "port", "Pasta", "info", path,
        "Análise somente leitura.")

    local size = commandValue("du -sh " .. quoted .. " 2>/dev/null | awk '{print $1}'", "não calculado")
    local files = commandValue("find " .. quoted .. " -type f 2>/dev/null | wc -l", "0")
    results[#results + 1] = item("port_size", "port", "Conteúdo", "info", size .. " · " .. files .. " arquivos", "")

    local elfPathsOutput = commandValue("find " .. quoted
        .. " -maxdepth 5 -type f -exec file {} + 2>/dev/null | sed -n 's/: ELF .*//p' | head -n 24", "")
    local elfPaths = util.lines(elfPathsOutput)
    local elfLines = {}
    local architectures = {}
    local architectureSeen = {}
    local dependencies = {}
    local localFiles = {}

    for _, localPath in ipairs(util.lines(commandValue("find " .. quoted
        .. " -maxdepth 6 \\( -type f -o -type l \\) -name '*.so*' -print 2>/dev/null", ""))) do
        local arch=util.elfArchitecture(localPath)
        if arch then
            local filename=util.basename(localPath)
            localFiles[filename]=localFiles[filename] or {}
            localFiles[filename][arch]=true
        end
    end

    for _, elfPath in ipairs(elfPaths) do
        local description = commandValue("file -b " .. util.shellQuote(elfPath), "ELF")
        elfLines[#elfLines + 1] = elfPath .. ": " .. description
        local arch = "desconhecida"
        local lowered = description:lower()
        if lowered:find("aarch64", 1, true) then
            arch = "aarch64"
        elseif lowered:find("arm", 1, true) and lowered:find("32%-bit") then
            arch = "armhf"
        elseif lowered:find("x86%-64") or lowered:find("x86_64", 1, true) then
            arch = "x86_64"
        end
        addUnique(architectures, architectureSeen, arch)

        local needed = commandValue("readelf -d " .. util.shellQuote(elfPath)
            .. " 2>/dev/null | sed -n 's/.*Shared library: \\[\\(.*\\)\\]/\\1/p'", "")
        for _, library in ipairs(util.lines(needed)) do
            dependencies[library] = dependencies[library] or {}
            dependencies[library][arch] = true
        end
    end

    results[#results + 1] = item("port_elf", "port", "Executáveis ELF",
        #elfLines > 0 and "ok" or "info", #elfLines > 0 and tostring(#elfLines) .. " detectados" or "nenhum detectado",
        #elfLines > 0 and table.concat(elfLines, "\n") or "O port pode usar script, runtime ou conteúdo interpretado.")

    results[#results + 1] = item("port_arch", "port", "Arquiteturas",
        #architectures > 0 and "info" or "info", #architectures > 0 and table.concat(architectures, ", ") or "via runtime/script",
        "Arquiteturas encontradas nos primeiros 24 arquivos ELF.")

    local globalEntries = {}
    for _, line in ipairs(util.lines(commandValue("ldconfig -p 2>/dev/null", ""))) do
        local library = line:match("^([^%s]+)")
        local libraryPath=line:match('=>%s+(.+)$')
        local nativeArch=libraryPath and util.elfArchitecture(libraryPath)
        if library and nativeArch then
            globalEntries[library] = globalEntries[library] or {}
            globalEntries[library][#globalEntries[library] + 1] = nativeArch
        end
    end

    local missing = {}
    for _, library in ipairs(sortedKeys(dependencies)) do
        do
            local entries = globalEntries[library] or {}
            for arch in pairs(dependencies[library]) do
                local found = localFiles[library] and localFiles[library][arch] or false
                for _, nativeArch in ipairs(entries) do
                    found = found or nativeArch==arch
                end
                if not found then
                    missing[#missing + 1] = library .. " (" .. arch .. ")"
                end
            end
        end
    end

    for _, arch in ipairs(architectures) do
        local loader
        if arch == "armhf" then
            loader = "/lib/ld-linux-armhf.so.3"
        elseif arch == "aarch64" then
            loader = "/lib/ld-linux-aarch64.so.1"
        end
        if loader and not util.testFile(loader) then
            missing[#missing + 1] = util.basename(loader) .. " (" .. arch .. ")"
        end
    end

    results[#results + 1] = item("port_deps", "port", "Dependências ELF",
        #missing == 0 and "ok" or "warn",
        tostring(#sortedKeys(dependencies)) .. " exigidas · " .. tostring(#missing) .. " ausentes",
        #missing == 0 and "As dependências diretas têm cabeçalho ELF e arquitetura compatível. Presença não garante resolução em execução."
            or (table.concat(missing, "\n").."\nAnálise estática: runtimes e pontes Android podem fornecer símbolos de outra forma. Não substitui o pré-teste do carregador."))

    local nonExecutable = util.lines(commandValue("find " .. quoted
        .. " -maxdepth 5 -type f \\( -name '*.sh' -o -name '*.armhf' -o -name '*.aarch64' \\) ! -perm -111 -print 2>/dev/null", ""))
    local nonExecutableSeen = {}
    for _, pathValue in ipairs(nonExecutable) do
        nonExecutableSeen[pathValue] = true
    end
    for _, elfPath in ipairs(elfPaths) do
        if not util.testFile(elfPath, true) then
            addUnique(nonExecutable, nonExecutableSeen, elfPath)
        end
    end
    results[#results + 1] = item("port_permissions", "port", "Permissões de execução",
        #nonExecutable == 0 and "ok" or "warn", #nonExecutable == 0 and "OK" or tostring(#nonExecutable) .. " para corrigir",
        #nonExecutable == 0 and "Scripts e binários nomeados estão executáveis."
            or table.concat(nonExecutable, "\n"))

    local launcherText = findPortLaunchers(name, root)
    local runtimeText = ""
    for _, launcher in ipairs(util.lines(launcherText)) do
        runtimeText = runtimeText .. "\n" .. (util.readFile(launcher, 65536) or "")
    end
    local runtimes = {}
    local runtimeSeen = {}
    for runtime in runtimeText:gmatch("runtimes/[\"']?([%w%._%-]+)") do
        addUnique(runtimes, runtimeSeen, runtime)
    end
    for runtime in runtimeText:gmatch("[Rr][Uu][Nn][Tt][Ii][Mm][Ee]%s*=%s*[\"']([%w%._%-]+)") do
        addUnique(runtimes, runtimeSeen, runtime)
    end
    local localRuntimes = {}
    for _, runtime in ipairs(runtimes) do
        local found = commandValue("find " .. quoted .. " -type f -name "
            .. util.shellQuote(runtime) .. " -size +1048575c -print -quit 2>/dev/null", "")
        if found ~= "" then
            localRuntimes[#localRuntimes + 1] = util.firstLine(found)
        end
    end
    local recipe = recipes.addRuntimes(name, runtimes, runtimeSeen)
    results[#results + 1] = item("port_runtime", "port", "Runtime PortMaster",
        #runtimes > 0 and "info" or "info", #runtimes > 0 and table.concat(runtimes, ", ") or "não declarado",
        recipe and recipe.notes or "Runtimes ausentes podem ser instalados com segurança na seção Reparos.")

    local metadataText = runtimeText
        .. "\n" .. (util.readFile(path .. "/README.md", 131072) or "")
        .. "\n" .. (util.readFile(path .. "/readme.md", 131072) or "")
        .. "\n" .. (util.readFile(path .. "/port.json", 131072) or "")
    local metadataLower = metadataText:lower()
    local deviceIdentity = table.concat({
        os.getenv("DEVICE_NAME") or "",
        os.getenv("DEVICE_CPU") or "",
        commandValue("tr -d '\\000' </proc/device-tree/model 2>/dev/null", ""),
        commandValue("tr -d '\\000' </proc/device-tree/compatible 2>/dev/null", ""),
    }, " ")
    local deviceLower = deviceIdentity:lower()

    local logPath = path .. "/log.txt"
    local issues = {}
    local invalidLaunchers = {}
    for _, launcher in ipairs(util.lines(launcherText)) do
        local header = util.readFile(launcher, 512) or ""
        if header:sub(1, 2) ~= "#!" and header:find("#!/", 1, true) then
            invalidLaunchers[#invalidLaunchers + 1] = launcher
        end
    end
    local gameDataCandidates = util.lines(commandValue("find " .. quoted
        .. " -type f -iname 'game.droid' ! -path '*/saves/game.droid' -size +1048575c -print 2>/dev/null | head -n 8", ""))
    if util.testFile(logPath) then
        local logText = util.readTail(logPath, 262144) or ""
        -- Correlate tombstones with the current launch; ignore old bundled crashes.
        local logTime=tonumber(commandValue("stat -c %Y "..util.shellQuote(logPath).." 2>/dev/null", "0")) or 0
        local crashPaths = util.lines(commandValue("find " .. quoted
            .. " -maxdepth 2 -type f -name 'tombstone_*' -print 2>/dev/null | head -n 8", ""))
        for _,crashPath in ipairs(crashPaths) do
            local crashTime=tonumber(commandValue("stat -c %Y "..util.shellQuote(crashPath).." 2>/dev/null", "0")) or 0
            if logTime>0 and crashTime>=logTime-1800 then
                local crashText=util.readFile(crashPath,65536) or ""
                logText=logText.."\nRegistro nativo recente (correlação aproximada): "..crashPath.."\n"..crashText
            end
        end
        issues = logdoctor.analyze(logText)
        if #invalidLaunchers > 0 then
            issues = logdoctor.append(issues, {
                id = "invalid_launcher_header",
                kind = "invalid_launcher_header",
                severity = "error",
                priority = 120,
                label = "Launcher inválido",
                value = "texto aparece antes do #!",
                detail = "O Linux exige que o interpretador esteja na primeira linha. O Port Doctor pode remover somente o prefixo indevido e preservar o restante do launcher com backup.",
                evidence = invalidLaunchers[1],
                repairable = true,
            })
        end
        local hasNativeCrash = false
        for _, issue in ipairs(issues) do
            hasNativeCrash = hasNativeCrash or issue.kind == "native_crash"
        end
        local declaresH700Rocknix = metadataLower:find("h700", 1, true)
            and metadataLower:find("rocknix", 1, true)
        local isRk3326Device = deviceLower:find("rk3326", 1, true)
            or deviceLower:find("r36s", 1, true)
            or deviceLower:find("darkos", 1, true)
        if hasNativeCrash and declaresH700Rocknix and isRk3326Device then
            issues = logdoctor.append(issues, {
                id = "platform_incompatible",
                kind = "platform_incompatible",
                severity = "error",
                priority = 110,
                label = "Build incompatível com o aparelho",
                value = "port H700/ROCKNIX em R36S RK3326",
                detail = "Este pacote declara o backend gráfico H700/ROCKNIX. No R36S com RK3326/dArkOSRE ele falha ao iniciar KMSDRM; bibliotecas adicionais não tornam esse executável compatível. É necessário um build próprio para RK3326/dArkOS.",
                evidence = "Metadados do port: H700/ROCKNIX · aparelho: " .. util.trim(deviceIdentity),
                repairable = false,
            })
        end
        local primary = logdoctor.primary(issues)
        if primary then
            results[#results + 1] = item("port_cause", "port", "Causa provável",
                primary.severity, primary.value,
                primary.detail .. "\nEvidência: " .. primary.evidence)
        else
            results[#results + 1] = item("port_cause", "port", "Causa provável", "info", "diagnóstico inconclusivo",
                "Nenhuma assinatura conhecida. Isso não confirma que o jogo funciona; uma tela preta exige diagnóstico adicional.")
        end
        local errors = commandValue("grep -Eic 'error|failed|missing|not found|segfault|illegal instruction' "
            .. util.shellQuote(logPath) .. " 2>/dev/null", "0")
        local tail = commandValue("tail -n 18 " .. util.shellQuote(logPath) .. " 2>/dev/null", "log vazio")
        local count = tonumber(errors) or 0
        results[#results + 1] = item("port_log", "port", "Último log",
            count > 0 and "warn" or "ok", count .. " linhas suspeitas", tail)
    else
        results[#results + 1] = item("port_log", "port", "Último log", "info", "não encontrado",
            "O port ainda pode não ter sido iniciado ou grava logs em outro local.")
    end

    local launchers = launcherText
    results[#results + 1] = item("port_launcher", "port", "Launcher relacionado",
        launchers ~= "" and "ok" or "info", launchers ~= "" and util.firstLine(launchers) or "não associado automaticamente",
        launchers ~= "" and launchers or "A associação pode usar um título diferente do nome da pasta.")

    return results, {
        name = name,
        path = path,
        architectures = architectures,
        dependencies = sortedKeys(dependencies),
        missing = missing,
        nonExecutable = nonExecutable,
        runtimes = runtimes,
        localRuntimes = localRuntimes,
        launchers = util.lines(launchers),
        issues = issues,
        gameDataCandidates = gameDataCandidates,
        invalidLaunchers = invalidLaunchers,
        deviceIdentity = deviceIdentity,
        metadataText = metadataText,
        logPath = logPath,
        recipe = recipe,
    }
end

function diagnostics.summary(results)
    local counts = { ok = 0, warn = 0, error = 0, info = 0 }
    for _, result in ipairs(results) do
        counts[result.status] = (counts[result.status] or 0) + 1
    end
    return counts
end

function diagnostics.exportReport(systemResults, portResults, selectedPort)
    local home = os.getenv("PORTDOCTOR_HOME")
    local reportDir
    if home and home ~= "" then
        reportDir = home .. "/conf/reports"
    else
        reportDir = love.filesystem.getSaveDirectory() .. "/reports"
    end

    util.run("mkdir -p " .. util.shellQuote(reportDir))
    local stamp = os.date("%Y%m%d-%H%M%S")
    local path = reportDir .. "/portdoctor-" .. stamp .. ".txt"
    local lines = {
        "Port Doctor R36S 0.11.2",
        "Autor: fabriciopab · https://github.com/Fabriciopab",
        "Gerado em: " .. os.date("%Y-%m-%d %H:%M:%S"),
        "Modo: somente leitura",
        "",
        "[Sistema]",
    }

    local function appendResults(items)
        for _, result in ipairs(items or {}) do
            lines[#lines + 1] = string.format("[%s] %s: %s", result.status:upper(), result.label, result.value)
            if result.detail ~= "" then
                lines[#lines + 1] = "  " .. result.detail:gsub("\n", "\n  ")
            end
        end
    end

    appendResults(systemResults)
    if portResults and #portResults > 0 then
        lines[#lines + 1] = ""
        lines[#lines + 1] = "[Port: " .. (selectedPort or "") .. "]"
        appendResults(portResults)
    end

    local ok = util.writeFile(path, table.concat(lines, "\n") .. "\n")
    return ok, path
end

return diagnostics
