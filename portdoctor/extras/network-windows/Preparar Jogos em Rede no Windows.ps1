#Requires -Version 5.1

[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$NomeConta = 'R36SNetwork'
$NomeCompartilhamentoPadrao = 'R36S-Jogos'
$NomeConfig = 'Jogos-em-Rede-R36S.conf'

function Test-Administrador {
    $identidade = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = New-Object Security.Principal.WindowsPrincipal($identidade)
    return $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

function Converter-SenhaParaTexto {
    param([Parameter(Mandatory = $true)][Security.SecureString]$Senha)

    $ponteiro = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($Senha)
    try {
        return [Runtime.InteropServices.Marshal]::PtrToStringBSTR($ponteiro)
    }
    finally {
        [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($ponteiro)
    }
}

function Ler-SenhaConfirmada {
    while ($true) {
        $senha1 = Read-Host 'Crie uma senha para o R36S acessar esta pasta' -AsSecureString
        $senha2 = Read-Host 'Digite a mesma senha novamente' -AsSecureString
        $texto1 = Converter-SenhaParaTexto -Senha $senha1
        $texto2 = Converter-SenhaParaTexto -Senha $senha2

        if ($texto1.Length -lt 8 -or $texto1 -match '[\r\n\x00]') {
            Write-Host 'Use pelo menos 8 caracteres, sem quebras de linha.' -ForegroundColor Yellow
            continue
        }
        if ($texto1 -ne $texto2) {
            Write-Host 'As senhas nao conferem. Tente novamente.' -ForegroundColor Yellow
            continue
        }

        return [PSCustomObject]@{
            Segura = $senha1
            Texto  = $texto1
        }
    }
}

function Obter-IPv4Principal {
    $rota = Get-NetRoute -AddressFamily IPv4 -DestinationPrefix '0.0.0.0/0' -ErrorAction SilentlyContinue |
        Where-Object { $_.NextHop -ne '0.0.0.0' } |
        Sort-Object RouteMetric, InterfaceMetric |
        Select-Object -First 1

    if ($null -ne $rota) {
        $ip = Get-NetIPAddress -AddressFamily IPv4 -InterfaceIndex $rota.InterfaceIndex -AddressState Preferred -ErrorAction SilentlyContinue |
            Where-Object { $_.IPAddress -notlike '169.254.*' -and $_.IPAddress -ne '127.0.0.1' } |
            Select-Object -First 1
        if ($null -ne $ip) {
            return $ip
        }
    }

    return Get-NetIPAddress -AddressFamily IPv4 -AddressState Preferred -ErrorAction SilentlyContinue |
        Where-Object { $_.IPAddress -notlike '169.254.*' -and $_.IPAddress -ne '127.0.0.1' } |
        Select-Object -First 1
}

if (-not (Test-Administrador)) {
    Write-Host 'Solicitando permissao de administrador...'
    $argumentos = '-NoProfile -ExecutionPolicy Bypass -File "{0}"' -f $PSCommandPath
    # Visible interactive assistant explicitly opened by the user.
    Start-Process -FilePath 'powershell.exe' -Verb RunAs -ArgumentList $argumentos -Wait
    exit
}

Clear-Host
Write-Host '============================================================'
Write-Host '  Jogos em Rede R36S - preparacao do Windows'
Write-Host '  Creditos: Fabricio Bastos - github.com/Fabriciopab'
Write-Host '============================================================'
Write-Host ''
Write-Host 'Este assistente compartilha a pasta de ROMs somente com uma'
Write-Host 'conta local exclusiva chamada R36SNetwork.'
Write-Host ''
Write-Host 'A pasta deve conter subpastas com os mesmos nomes usados no R36S:'
Write-Host 'nes, snes, gba, megadrive, psx, psp, dreamcast etc.'
Write-Host ''

do {
    $PastaJogos = (Read-Host 'Digite ou cole o caminho completo da pasta de jogos').Trim().Trim('"')
    if (-not (Test-Path -LiteralPath $PastaJogos -PathType Container)) {
        Write-Host 'Pasta nao encontrada. Confira o caminho.' -ForegroundColor Yellow
        $PastaJogos = $null
    }
} while ([string]::IsNullOrWhiteSpace($PastaJogos))

$PastaJogos = (Resolve-Path -LiteralPath $PastaJogos).Path
$raizPasta = [IO.Path]::GetPathRoot($PastaJogos)
if ($PastaJogos.StartsWith('\\') -or $PastaJogos.TrimEnd('\') -eq $raizPasta.TrimEnd('\') -or
    $PastaJogos.TrimEnd('\') -eq $env:USERPROFILE.TrimEnd('\')) {
    throw 'Escolha uma pasta local dedicada aos jogos, nunca um disco inteiro, pasta de usuario ou compartilhamento de rede.'
}
foreach ($protegida in @($env:WINDIR, $env:ProgramFiles, ${env:ProgramFiles(x86)}, $env:ProgramData)) {
    if ($protegida -and ($PastaJogos -eq $protegida -or $PastaJogos.StartsWith($protegida.TrimEnd('\') + '\', [StringComparison]::OrdinalIgnoreCase))) {
        throw 'Pasta do sistema recusada. Use uma pasta dedicada aos jogos.'
    }
}
$verificarPasta = Get-Item -LiteralPath $PastaJogos
while ($null -ne $verificarPasta) {
    if ($verificarPasta.Attributes -band [IO.FileAttributes]::ReparsePoint) { throw 'Links e juncoes nao sao aceitos como pasta de jogos.' }
    $verificarPasta = $verificarPasta.Parent
}
$NomeCompartilhamento = (Read-Host "Nome do compartilhamento [$NomeCompartilhamentoPadrao]").Trim()
if ([string]::IsNullOrWhiteSpace($NomeCompartilhamento)) {
    $NomeCompartilhamento = $NomeCompartilhamentoPadrao
}
if ($NomeCompartilhamento -notmatch '^[A-Za-z0-9_-]{1,40}$') {
    throw 'Use somente letras, numeros, hifen e sublinhado no nome do compartilhamento.'
}

$compartilhamentoExistente = Get-SmbShare -Name $NomeCompartilhamento -ErrorAction SilentlyContinue
if ($null -ne $compartilhamentoExistente -and $compartilhamentoExistente.Path -ne $PastaJogos) {
    throw 'Esse compartilhamento ja aponta para outra pasta. Escolha outro nome; nada foi alterado.'
}
$ipPrincipal = Obter-IPv4Principal
if ($null -eq $ipPrincipal) { throw 'Conecte o computador a sua rede local antes de continuar.' }
$perfil = Get-NetConnectionProfile -InterfaceIndex $ipPrincipal.InterfaceIndex -ErrorAction SilentlyContinue
if ($null -eq $perfil -or $perfil.NetworkCategory -ne 'Private') {
    throw 'Use uma rede de confianca marcada como Privada nas Configuracoes do Windows. Nao vamos liberar compartilhamento em rede Publica.'
}
Write-Host "Sera permitido acesso de leitura e gravacao a: $PastaJogos"
Write-Host 'Isso inclui criar/alterar saves e excluir arquivos nessa pasta. Permissoes preexistentes serao mantidas.'
if ((Read-Host 'Confirma configurar esta pasta e a conta R36SNetwork? Digite SIM') -cne 'SIM') { throw 'Cancelado; nenhuma configuracao aplicada.' }
$senha = Ler-SenhaConfirmada
$ContaCompleta = "$env:COMPUTERNAME\$NomeConta"
$contaExistente = Get-LocalUser -Name $NomeConta -ErrorAction SilentlyContinue

if ($null -eq $contaExistente) {
    New-LocalUser -Name $NomeConta -Password $senha.Segura -Description 'Acesso do R36S aos jogos em rede' -PasswordNeverExpires -UserMayNotChangePassword | Out-Null
    Write-Host "Conta $NomeConta criada."
}
else {
    $resposta = (Read-Host "A conta $NomeConta ja existe. Atualizar a senha? [S/n]").Trim()
    if ([string]::IsNullOrWhiteSpace($resposta) -or $resposta -match '^[SsYy]') {
        Set-LocalUser -Name $NomeConta -Password $senha.Segura -PasswordNeverExpires $true -UserMayNotChangePassword $true
        Enable-LocalUser -Name $NomeConta
        Write-Host "Senha da conta $NomeConta atualizada."
    }
    else {
        Write-Host 'A senha informada sera gravada na configuracao, mas a conta nao foi alterada.' -ForegroundColor Yellow
        Write-Host 'Se a senha nao for a atual, a conexao do R36S falhara.' -ForegroundColor Yellow
    }
}

Write-Host 'Adicionando leitura e gravacao para a conta do R36S; demais permissoes preservadas...'
& icacls.exe $PastaJogos /grant ('{0}:(OI)(CI)M' -f $ContaCompleta) | Out-Null
if ($LASTEXITCODE -ne 0) {
    throw 'O Windows nao conseguiu aplicar a permissao na pasta.'
}

$compartilhamentoExistente = Get-SmbShare -Name $NomeCompartilhamento -ErrorAction SilentlyContinue
if ($null -eq $compartilhamentoExistente) {
    New-SmbShare -Name $NomeCompartilhamento -Path $PastaJogos -ChangeAccess $ContaCompleta -CachingMode None -FolderEnumerationMode AccessBased -Description 'Jogos em rede para o R36S' | Out-Null
    Write-Host "Compartilhamento $NomeCompartilhamento criado."
}
elseif ($compartilhamentoExistente.Path -ne $PastaJogos) {
    throw "Ja existe um compartilhamento chamado $NomeCompartilhamento apontando para outra pasta. Execute novamente e escolha outro nome."
}
else {
    Grant-SmbShareAccess -Name $NomeCompartilhamento -AccountName $ContaCompleta -AccessRight Change -Force | Out-Null
    Set-SmbShare -Name $NomeCompartilhamento -CachingMode None -Force | Out-Null
    Write-Host 'O compartilhamento existente foi atualizado.'
}

# Dedicated rule: do not enable broad built-in groups or SMB1.
$nomeRegra = 'PortDoctor-R36S-SMB-Private'
$regra = Get-NetFirewallRule -Name $nomeRegra -ErrorAction SilentlyContinue
if ($null -eq $regra) {
    New-NetFirewallRule -Name $nomeRegra -DisplayName 'Port Doctor R36S - SMB rede privada local' -Direction Inbound -Action Allow -Protocol TCP -LocalPort 445 -RemoteAddress LocalSubnet -Profile Private | Out-Null
} else {
    Write-Host 'Regra propria existente preservada. Confira se ela continua limitada a rede Privada e LocalSubnet.'
}

$ipPrincipal = Obter-IPv4Principal
if ($null -eq $ipPrincipal) {
    throw 'Nao encontrei um endereco IPv4 ativo. Conecte o computador a rede e execute novamente.'
}

$perfil = Get-NetConnectionProfile -InterfaceIndex $ipPrincipal.InterfaceIndex -ErrorAction SilentlyContinue
if ($null -ne $perfil -and $perfil.NetworkCategory -eq 'Public') {
    Write-Host ''
    Write-Host 'A rede atual esta marcada como Publica. O compartilhamento pode ser bloqueado.' -ForegroundColor Yellow
    $mudarPerfil = (Read-Host 'Mudar esta rede para Privada? [S/n]').Trim()
    if ([string]::IsNullOrWhiteSpace($mudarPerfil) -or $mudarPerfil -match '^[SsYy]') {
        Set-NetConnectionProfile -InterfaceIndex $ipPrincipal.InterfaceIndex -NetworkCategory Private
        Write-Host 'Rede alterada para Privada.'
    }
}

$senhaBase64 = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($senha.Texto))
$linhasConfig = @(
    '# Configuracao de importacao unica - Jogos em Rede R36S'
    '# A senha abaixo esta apenas codificada. O R36S apagara esta linha apos importar.'
    "SERVIDOR=$($ipPrincipal.IPAddress)"
    "COMPARTILHAMENTO=$NomeCompartilhamento"
    "USUARIO=$NomeConta"
    "DOMINIO=$env:COMPUTERNAME"
    'VERSAO_SMB=3.0'
    "SENHA_BASE64=$senhaBase64"
)

$caminhoConfig = Join-Path $PSScriptRoot $NomeConfig
$textoConfig = ($linhasConfig -join "`n") + "`n"
[IO.File]::WriteAllText($caminhoConfig, $textoConfig, (New-Object Text.UTF8Encoding($false)))

$senha.Texto = $null
$senhaBase64 = $null

Write-Host ''
Write-Host '============================================================' -ForegroundColor Green
Write-Host '  Preparacao concluida' -ForegroundColor Green
Write-Host '============================================================' -ForegroundColor Green
Write-Host "Pasta:  $PastaJogos"
Write-Host "Rede:   \\$($ipPrincipal.IPAddress)\$NomeCompartilhamento"
Write-Host "Conta:  $ContaCompleta"
Write-Host ''
Write-Host "Arquivo criado: $caminhoConfig"
Write-Host ''
Write-Host 'Copie SOMENTE o arquivo abaixo para /roms/tools ou /roms2/tools do R36S:' -ForegroundColor Cyan
Write-Host "  $NomeConfig"
Write-Host 'No Port Doctor: Jogos em rede > Importar configuracao > Conectar jogos do Windows.'
Write-Host 'Nao precisa copiar outro .sh nem acessar SSH.'
Write-Host 'IMPORTANTE: o .conf contem senha codificada, nao criptografada. Nao publique esse arquivo.'
Write-Host 'Depois de importar no console, apague a copia restante do .conf no PC.'
Write-Host ''
Write-Host 'Mantenha o computador ligado e conectado a mesma rede do R36S.'
Write-Host 'Creditos: Fabricio Bastos - https://github.com/Fabriciopab'
Write-Host ''
[void](Read-Host 'Pressione ENTER para fechar')
