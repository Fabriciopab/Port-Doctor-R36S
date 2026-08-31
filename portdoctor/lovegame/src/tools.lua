local util = require("src.util")

local tools = {}

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

local function homePath(relative)
    local home = os.getenv("PORTDOCTOR_HOME") or ""
    return home ~= "" and (home .. "/" .. relative) or ""
end

local function command(path, arguments, root)
    if path == "" or not util.testFile(path) then
        return nil
    end
    return (root and sudoPrefix() or "") .. util.shellQuote(path) .. (arguments and (" " .. arguments) or "")
end

local function hasCoverBackup(portsRoot)
    local output = util.run("find " .. util.shellQuote(portsRoot)
        .. " -maxdepth 1 -type f -name 'gamelist.xml.bak-*' -print -quit 2>/dev/null")
    return output ~= ""
end

local function networkConfigAvailable()
    local candidates = {
        homePath("conf/Jogos-em-Rede-R36S.conf"),
        "/roms/tools/Jogos-em-Rede-R36S.conf",
        "/roms2/tools/Jogos-em-Rede-R36S.conf",
    }
    for _, path in ipairs(candidates) do
        if path ~= "" and util.testFile(path) then return true end
    end
    return false
end

function tools.actions()
    local home = os.getenv("PORTDOCTOR_HOME") or ""
    local portsRoot = os.getenv("PORTS_ROOT") or "/roms/ports"
    local coverHelper = homePath("integrations/covers/portmaster-cover-fix.sh")
    local storageHelper = homePath("integrations/system/storage-doctor.sh")
    local usbHelper = homePath("integrations/usb/usb-bridge.sh")
    local networkHelper = homePath("integrations/network/network-manager.sh")
    local usbInstalled = util.testFile("/usr/local/sbin/r36s-usb-control", true)
        and util.testFile("/etc/r36s-usb-file-access.conf")
    local networkConfigured = util.testFile("/etc/r36s-network/config")
        and util.testFile("/etc/r36s-network/credentials")

    local coverEnv = "PORTDOCTOR_HOME=" .. util.shellQuote(home)
        .. " PORTS_PATH=" .. util.shellQuote(portsRoot) .. " SKIP_RESTART=1 "
    local coverSync = command(coverHelper, "sync", false)
    local coverRestore = command(coverHelper, "restore", false)
    if coverSync then
        coverSync = coverEnv .. coverSync .. "; status=$?; tail -n 120 "
            .. util.shellQuote(homePath("conf/reports/portmaster-cover-fix.log"))
            .. " 2>/dev/null; exit $status"
    end
    if coverRestore then
        coverRestore = coverEnv .. coverRestore .. "; status=$?; tail -n 80 "
            .. util.shellQuote(homePath("conf/reports/portmaster-cover-fix.log"))
            .. " 2>/dev/null; exit $status"
    end

    return {
        {
            id = "storage_check", group = "SISTEMA", label = "Testar gravação e permissões",
            value = "ports + Port Doctor + /boot",
            detail = "Cria, confirma e remove arquivos temporários; também testa sudo sem senha e detecta montagem somente leitura.",
            enabled = command(storageHelper, nil, false) ~= nil,
            command = command(storageHelper, nil, false), immediate = true,
        },
        {
            id = "covers_sync", group = "CAPAS", label = "Reconhecer capas dos ports",
            value = "cover/cove → nome do .sh",
            detail = "Usa o método PortMaster Cover Fix validado: cria uma cópia com o nome do launcher, atualiza o gamelist.xml e preserva o original.",
            enabled = coverSync ~= nil, command = coverSync,
            confirmation = "Procurar capas dentro de todos os ports instalados e atualizar a lista do EmulationStation?",
        },
        {
            id = "covers_restore", group = "CAPAS", label = "Desfazer ajuste de capas",
            value = hasCoverBackup(portsRoot) and "backup disponível" or "sem backup",
            detail = "Restaura o gamelist.xml anterior. As imagens originais permanecem intactas.",
            enabled = coverRestore ~= nil and hasCoverBackup(portsRoot), command = coverRestore,
            confirmation = "Restaurar a lista anterior à última atualização de capas?",
        },
        {
            id = "usb_preflight", group = "USB", label = "Verificar USB por cabo",
            value = "somente leitura",
            detail = "Confere DTB, UDC, ConfigFS e módulos RNDIS antes de permitir a instalação.",
            enabled = command(usbHelper, "preflight", false) ~= nil,
            command = command(usbHelper, "preflight", false), immediate = true,
        },
        {
            id = "usb_status", group = "USB", label = "Estado do acesso USB",
            value = usbInstalled and "instalado" or "não instalado",
            detail = "Mostra modo do DTB, modo deste boot, serviço e endereço usb0.",
            enabled = command(usbHelper, "status", false) ~= nil,
            command = command(usbHelper, "status", false), immediate = true,
        },
        {
            id = "usb_install", group = "USB", label = "Instalar acesso USB",
            value = usbInstalled and "já instalado" or "RNDIS + Samba/SSH",
            detail = "Instala só dependências ausentes, valida o aparelho, salva duas cópias do DTB e não reinicia.",
            enabled = not usbInstalled and command(usbHelper, "install", true) ~= nil,
            command = command(usbHelper, "install", true),
            confirmation = "Instalar o acesso USB e, se necessário, somente seus componentes Debian pela internet?",
        },
        {
            id = "usb_activate", group = "USB", label = "Ativar USB e reiniciar",
            value = usbInstalled and "reinicia o R36S" or "instale primeiro",
            detail = "Troca somente para o DTB peripheral validado; o dongle Wi-Fi deixa de funcionar neste modo.",
            enabled = usbInstalled and command(usbHelper, "activate", true) ~= nil,
            command = command(usbHelper, "activate", true), confirmations = 2,
            confirmation = "Preparar o modo USB por cabo? O R36S será reiniciado e o Wi-Fi pela porta OTG ficará indisponível.",
            finalConfirmation = "Confirma a troca para USB peripheral e o reinício imediato do aparelho?",
        },
        {
            id = "usb_restore", group = "USB", label = "Restaurar USB e Wi-Fi",
            value = usbInstalled and "reinicia o R36S" or "não instalado",
            detail = "Valida o SHA-256, repõe o DTB OTG original e reinicia para permitir novamente o dongle Wi-Fi.",
            enabled = usbInstalled and command(usbHelper, "restore", true) ~= nil,
            command = command(usbHelper, "restore", true), confirmations = 2,
            confirmation = "Restaurar o modo OTG original para voltar a usar Wi-Fi pela porta USB?",
            finalConfirmation = "Confirma a restauração do backup validado e o reinício imediato do aparelho?",
        },
        {
            id = "network_import", group = "REDE", label = "Importar configuração de rede",
            value = networkConfigAvailable() and "arquivo encontrado" or "arquivo .conf ausente",
            detail = "Importa a configuração criada no Windows, protege a credencial e remove a senha do arquivo de transporte.",
            enabled = networkConfigAvailable() and command(networkHelper, "import", true) ~= nil,
            command = command(networkHelper, "import", true),
            confirmation = "Importar ou substituir a configuração dos jogos em rede?",
        },
        {
            id = "network_status", group = "REDE", label = "Estado dos jogos em rede",
            value = networkConfigured and "configurado" or "não configurado",
            detail = "Consulta servidor, compartilhamento, montagem CIFS e quantidade de sistemas ligados.",
            enabled = command(networkHelper, "status", true) ~= nil,
            command = command(networkHelper, "status", true), immediate = true,
        },
        {
            id = "network_connect", group = "REDE", label = "Conectar jogos do Windows",
            value = networkConfigured and "SMB/CIFS" or "importe o .conf",
            detail = "Monta o compartilhamento e cria pastas Rede somente nos sistemas compatíveis do EmulationStation.",
            enabled = networkConfigured and command(networkHelper, "connect", true) ~= nil,
            command = command(networkHelper, "connect", true),
            confirmation = "Conectar as pastas de jogos compartilhadas pelo computador e recarregar o menu?",
        },
        {
            id = "network_disconnect", group = "REDE", label = "Desconectar jogos em rede",
            value = "não apaga ROMs",
            detail = "Desmonta somente as pastas registradas pelo módulo e preserva jogos e saves no computador.",
            enabled = networkConfigured and command(networkHelper, "disconnect", true) ~= nil,
            command = command(networkHelper, "disconnect", true),
            confirmation = "Desconectar todas as pastas Rede e recarregar o menu?",
        },
        {
            id = "network_diagnostic", group = "REDE", label = "Criar diagnóstico de rede",
            value = "relatório local",
            detail = "Registra IP, rota, porta 445, CIFS, montagens e erros recentes sem incluir a senha.",
            enabled = command(networkHelper, "diagnostic", true) ~= nil,
            command = command(networkHelper, "diagnostic", true), immediate = true,
        },
        {
            id = "network_install_smb", group = "REDE", label = "Instalar suporte SMB",
            value = "internet necessária",
            detail = "Instala somente cifs-utils pelo Debian e valida o driver CIFS; não executa atualização geral do sistema.",
            enabled = command(networkHelper, "install-smb", true) ~= nil,
            command = command(networkHelper, "install-smb", true),
            confirmation = "Atualizar a lista de pacotes e instalar somente cifs-utils pela internet?",
        },
    }
end

return tools
