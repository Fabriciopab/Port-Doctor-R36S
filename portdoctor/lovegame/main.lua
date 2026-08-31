local diagnostics = require('src.diagnostics')
local repairs = require('src.repairs')
local integrations = require('src.tools')
local battery = require('src.battery')
local memory = require('src.memory')
local storage = require('src.storage')
local icons = require('src.icons')
local updates = require('src.updates')
local util = require('src.util')
local lg = love.graphics
local fonts = {}
local colors = {bg={.035,.055,.075},panel={.065,.10,.13},selected={.06,.26,.23},text={.93,.96,.97},
    muted={.67,.74,.77},accent={.17,.91,.68},error={1,.40,.38},warn={1,.78,.32},info={.43,.74,1}}
local state = {page={id='home',title='Port Doctor R36S',selection=1},stack={},results={},tasks={},taskIndex=1,
    scanning=false,ports={},portsRoot='/roms/ports',portResults={},repairActions={},toolActions={},cooldown=0,
    toastTime=0,lastOutput=''}
local function color(c) lg.setColor(unpack(c or colors.text)) end
local function panel(x,y,w,h,c) color(c or colors.panel); lg.rectangle('fill',x,y,w,h,10,10) end
local function toast(text) state.toast=tostring(text or ''); state.toastTime=3 end
local function push(page)
    state.stack[#state.stack+1]=state.page; page.selection=page.selection or 1; page.scroll=0; state.page=page
end
local function back()
    if #state.stack>0 then state.page=table.remove(state.stack)
    else push({id='exit',title='Sair do Port Doctor?',text='Os relatórios e backups salvos serão preservados.\n\nA confirma a saída. B volta ao menu.'}) end
end
local function textPage(title,text) push({id='text',title=title,text=tostring(text or 'Sem detalhes disponíveis.')}) end
local startStorage
local function refreshSystem()
    local ok,name,version,vendor,device=pcall(lg.getRendererInfo)
    state.results={}; state.tasks=diagnostics.systemTasks(ok and {name=name,version=version,vendor=vendor,device=device} or nil)
    state.taskIndex=1; state.scanning=true
end
local function refreshPorts() state.ports,state.portsRoot=diagnostics.scanPorts() end
local function refreshActions()
    state.repairActions=repairs.actions(state.portDetails); state.toolActions=integrations.actions()
end
local function recommendedRepairAction()
    for _,action in ipairs(state.repairActions) do if action.id=='auto_repair' then return action end end
end
local function reanalyze()
    if not state.analyzedPort then return end
    if state.analysis then return end
    local channel='portdoctor-analysis-'..tostring(love.timer.getTime())
    local thread=love.thread.newThread([[
        local name,root,channel=...
        local ok,results,details=pcall(require('src.diagnostics').analyzePort,name,root)
        love.thread.getChannel(channel):push({ok=ok,results=ok and results or nil,
            details=ok and details or nil,error=not ok and tostring(results) or nil})
    ]])
    state.analysis={thread=thread,channel=love.thread.getChannel(channel)}
    thread:start(state.analyzedPort,state.portsRoot,channel)
end
local function report()
    local ok=diagnostics.exportReport(state.results,state.portResults,state.analyzedPort)
    if state.lastOutput~='' and os.getenv('PORTDOCTOR_HOME') then
        ok=util.writeFile(os.getenv('PORTDOCTOR_HOME')..'/conf/reports/ultima-acao.txt',state.lastOutput..'\n') and ok
    end
    toast(ok and 'Relatório salvo em conf/reports' or 'Falha ao salvar o relatório')
end
local function entries()
    local p=state.page
    if p.id=='home' then return {
        {label='Meus ports',hint='Diagnosticar e corrigir',page='ports',icon='game'},
        {label='Bateria e desempenho',hint='4 perfis, brilho e memória zram',page='battery',icon='battery'},
        {label='Gerenciador de arquivos',hint='Copiar, recortar e excluir',storage={action='list'},icon='folder'},
        {label='Limpeza e lixeira',hint='Prévia, recuperação e espaço',page='cleanup'},
        {label='Rede e Wi-Fi',hint='IP, MAC e ligar/desligar',page='network'},
        {label='Sistema',hint='Memória e compatibilidade',page='system'},
        {label='Vídeo e áudio',hint='Imagem, som e controles',page='av'},
        {label='PortMaster',hint='Bibliotecas e runtimes',page='pm'},
        {label='Capas dos jogos',hint='Reconhecer e restaurar',page='tools',group='CAPAS',icon='image'},
        {label='USB / OTG',hint='Modo do cabo ou dongle',page='tools',group='USB',icon='usb'},
        {label='Jogos em rede',hint='Pastas do Windows',page='tools',group='REDE',icon='network'},
        {label='Armazenamento',hint='Gravação e permissões',page='tools',group='SISTEMA',icon='disk'},
        {label='Manutenção avançada',hint='Atualizações e ferramentas',page='repair'},
        {label='Atualizar Port Doctor',hint='Nova versão pelo GitHub',page='updates',icon='update'},
        {label='Contribuir com o projeto',hint='Pix opcional para apoiar',page='support',icon='heart'},
        {label='Modelo testado',hint='R36S-V30-2025-11-18-2603',page='compatibility',icon='shield'},
        {label='Sobre e créditos',hint='fabriciopab',page='about'},
    } elseif p.id=='ports' then
        local result={}; for _,name in ipairs(state.ports) do result[#result+1]={label=name,port=name} end; return result
    elseif p.id=='port' then
        local action=recommendedRepairAction()
        local result={
            {label=action and action.enabled and 'Corrigir problema identificado' or 'Ver opções de correção',
                hint=action and action.enabled and 'Reparo protegido disponível' or 'Consultar motivo e alternativas',
                action=action and action.enabled and action or nil,subpage='repair'},
            {label='Ler diagnóstico completo',hint='Causa, evidências e dependências',subpage='port_results'},
        }
        for _,a in ipairs(state.repairActions) do
            if a.id=='verify_repair' or a.id=='verify' or a.id=='restore_repair' or a.id=='restore' then
                result[#result+1]={label=a.label,hint=a.value,action=a}
            end
        end
        result[#result+1]={label='Todas as opções deste port',hint='Reparos, verificação e backup',subpage='repair'}
        result[#result+1]={label='Analisar novamente',hint='Atualizar após testar o jogo',reanalyze=true}
        result[#result+1]={label='Desinstalar este jogo',hint='Prévia da pasta e launcher; usa lixeira',
            storage={action='plan',operation='uninstall',path=state.portsRoot..'/'..state.analyzedPort}}
        return result
    elseif p.id=='cleanup' then return {
        {label='Procurar resíduos seguros',hint='Varredura sem apagar; prévia primeiro',storage={action='plan',operation='cleanup'}},
        {label='Abrir lixeira',hint='Restaurar ou apagar definitivamente',storage={action='trash'}},
        {label='Esvaziar lixeira',hint='Libera espaço; duas confirmações',storage={action='plan',operation='purge_all'}},
        {label='O que a limpeza preserva?',hint='Saves, jogos, bibliotecas e backups',
            detail='A limpeza reconhece metadados antigos do explorador do computador e registros nativos antigos repetidos. Mantém o registro nativo mais recente. Nunca classifica ROMs, saves, BIOS, runtimes, bibliotecas, arquivos desconhecidos ou backups como lixo.\n\nMover para a lixeira não libera espaço. Para liberar, abra cada item da lixeira, confira e escolha Apagar definitivamente.'},
    }
    elseif p.id=='files' then
        local result={}
        if p.path~='' then
            result[#result+1]={label='Opções desta pasta',hint=p.path,folderOptions=true}
            if state.clipboard then result[#result+1]={label='Colar aqui',hint=state.clipboard.name,
                storage={action='plan',operation=state.clipboard.operation,path=state.clipboard.path,destination=p.path}} end
        end
        for _,item in ipairs(p.items or {}) do result[#result+1]={label=item.name,hint=item.hint,file=item} end
        if (p.offset or 0)>0 then result[#result+1]={label='Página anterior de arquivos',storage={action='list',path=p.path,offset=math.max(0,p.offset-150)}} end
        if (p.offset or 0)+150<(p.total or 0) then result[#result+1]={label='Mais arquivos',storage={action='list',path=p.path,offset=(p.offset or 0)+150}} end
        return result
    elseif p.id=='file_options' then
        local item=p.item; local parent=item.path:match('^(.*)/[^/]+$')
        local result={}
        if item.directory then result[#result+1]={label='Abrir pasta',hint=item.path,storage={action='list',path=item.path}} end
        result[#result+1]={label='Copiar',hint='Mantém o original',clipboard='copy',file=item}
        result[#result+1]={label='Recortar',hint='Move após colar no mesmo cartão',clipboard='move',file=item}
        result[#result+1]={label='Renomear',hint='Não sobrescreve destinos',keyboard={operation='rename',path=item.path,destination=parent,name=item.name}}
        result[#result+1]={label='Excluir para a lixeira',hint='Inclui todo o conteúdo da pasta',storage={action='plan',operation='delete',path=item.path}}
        result[#result+1]={label='Propriedades / caminho',hint='Tamanho e local completo',storage={action='info',path=item.path}}
        if item.directory and parent and parent:match('/ports$') then result[#result+1]={label='Desinstalar jogo',hint='Associar pasta + launcher com segurança',
            storage={action='plan',operation='uninstall',path=item.path}} end
        return result
    elseif p.id=='folder_options' then return {
        {label='Criar pasta',hint='Digite usando o direcional',keyboard={operation='mkdir',destination=p.path,name=''}},
        {label='Caminho e espaço disponível',hint=p.path,detail='Livre: '..tostring(p.free or '?')..'\n\nX abre as opções do arquivo selecionado. A entra nas pastas. B sobe uma pasta. Y recarrega a lista.'},
        {label='Abrir lixeira',storage={action='trash'}},
        {label='Limpar área de transferência',clearClipboard=true},
    }
    elseif p.id=='trash' then
        local result={}; for _,item in ipairs(p.items or {}) do result[#result+1]={label=item.name,hint=item.hint,trash=item} end
        if #result>0 then result[#result+1]={label='Esvaziar lixeira',hint='Todos os itens do cartão; irreversível',storage={action='plan',operation='purge_all'}} end
        if #result==0 then result[1]={label='Lixeira vazia',detail='Nenhum item excluído pelo Port Doctor foi encontrado.'} end
        return result
    elseif p.id=='trash_options' then return {
        {label='Restaurar item completo',hint='Nos caminhos originais',storage={action='plan',operation='restore',path=p.item.path}},
        {label='Apagar definitivamente',hint='Libera espaço; não pode ser desfeito',storage={action='plan',operation='purge',path=p.item.path}},
    }
    elseif p.id=='updates' then return {
        {label='Verificar atualizações',hint='Consulta a última release estável',action=updates.action('check'),icon='update'},
        {label='Estado da atualização',hint='Origem, versão e última tentativa',action=updates.action('status'),icon='info'},
        {label='Configurar repositório',hint='Somente da conta Fabriciopab',keyboard={updateRepository=true,name=''},icon='edit'},
        {label='Descartar pacote pendente',hint='Preserva registros e backups',action=updates.cancelAction(),icon='trash'},
        {label='Como funciona?',hint='Confirmação, download, validação e backup',icon='shield',
            detail='Busca releases públicas e estáveis no GitHub do mantenedor. Após sua confirmação, baixa o ZIP, confere SHA-256 e estrutura, fecha o app e instala automaticamente.\n\nPreserva conf, backups e jogos. Não atualiza o dArkOS nem o PortMaster. Não desligue o console.\n\nO repositório oficial e uma release com o pacote correto precisam estar publicados. A chave Pix não é necessária para atualizar.'},
    }
    elseif p.id=='memory' then
        local result={}; for _,a in ipairs(memory.actions()) do result[#result+1]={label=a.label,hint=a.value,action=a,icon='system'} end
        return result
    elseif p.id=='repair' or p.id=='tools' or p.id=='battery' or p.id=='network' then
        local actions=p.id=='repair' and state.repairActions or (p.id=='battery' and battery.actions()
            or (p.id=='network' and storage.networkActions() or state.toolActions))
        local result={}
        if p.id=='tools' and p.group=='REDE' then
            result[#result+1]={label='Comece aqui: preparar o PC',hint='Pasta dos jogos, senha e arquivo .conf',icon='info',detail=[[
1. NO WINDOWS
Copie a pasta inteira portdoctor/extras/network-windows do cartão para o computador. Ou extraia o ZIP Port-Doctor-R36S-Windows-Rede da release do GitHub.

2. ABRA O PREPARADOR
Dê dois cliques em "1 - Preparar no Windows.cmd" e aceite o pedido de administrador. Mantenha o .ps1 ao lado. Ele roda no PC, não no R36S.

3. PASTA E SENHA
Informe uma pasta dedicada, por exemplo D:\Jogos-R36S, com subpastas nes, snes, gba etc. Crie uma senha exclusiva. O assistente configura a conta R36SNetwork e o compartilhamento.

4. COPIE A CONFIGURAÇÃO
O PC gera Jogos-em-Rede-R36S.conf ao lado do preparador. Copie SOMENTE esse .conf para /roms/tools ou /roms2/tools do console. Não precisa instalar outro .sh nem usar SSH.

5. NO DOCTOR
Com PC e R36S na mesma rede local: Jogos em rede → Importar configuração → Conectar jogos do Windows. A pasta Rede aparece nos emuladores compatíveis.

IMPORTANTE
O PC deve ficar ligado. Não desconecte durante gravações de saves. O .conf transporta uma senha apenas codificada: não compartilhe nem envie ao GitHub. Após importar, apague a cópia restante no PC.

Use somente rede privada de confiança. Isso não executa .exe do Windows e não carrega as pastas ports, bios ou tools pela rede.]]}
        end
        for _,a in ipairs(actions) do if not p.group or a.group==p.group then
            result[#result+1]={label=a.label,hint=a.enabled and a.value or 'Consultar disponibilidade',action=a}
        end end
        if p.id=='battery' then
            result[#result+1]={label='Memória e zram',hint='Tamanhos recomendados e restauração',page='memory',icon='system'}
            result[#result+1]={label='Sobre overclock e segurança',hint='Não altera tensão ou frequências',icon='shield',detail='Os quatro perfis são modos de uso, não quatro níveis de overclock.\n\nNão instalamos kernel/DTB nem aumentamos tensão ou limites de frequência. Desempenho usa apenas o limite atual em RK3326 até 1,512 GHz.\n\n65 °C é um bloqueio preventivo do Doctor na ativação; não é limite certificado do fabricante e não há monitor contínuo do app. As proteções do firmware permanecem ativas.\n\nAumento de consumo e calor pode ocorrer. Se aquecer ou ficar instável, restaure o Padrão. Nenhuma configuração é garantida para todas as revisões, clones ou jogos.\n\nPadrão restaura ajustes anteriores do Doctor, não valores de fábrica desconhecidos. Perfis e zram valem até reiniciar; jogos podem substituir o governor.'}
        end
        return result
    elseif p.id=='system' or p.id=='av' or p.id=='pm' or p.id=='port_results' then
        local result={}
        for _,r in ipairs(p.id=='port_results' and state.portResults or state.results) do
            if p.id=='port_results' or r.group==p.id then result[#result+1]={label=r.label,hint=r.value,detail=r.detail,status=r.status} end
        end
        return result
    end
    return {}
end
local function startJob(action)
    if not action or not action.command or state.job then return end
    local channel='portdoctor-job-'..tostring(love.timer.getTime())
    local thread=love.thread.newThread([[
        local command,channel=...
        local h=io.popen(command..' 2>&1'); local output,success='',false
        if h then
            output=h:read('*a') or ''; local ok,_,status=h:close(); success=ok==true or status==0
        else output='Não foi possível iniciar a ação.' end
        love.thread.getChannel(channel):push((success and '1' or '0')..output)
    ]])
    if state.page.id=='confirm' then back() end
    push({id='job',title=action.label})
    state.job={thread=thread,channel=love.thread.getChannel(channel),action=action}; thread:start(action.command,channel)
end
startStorage=function(request)
    startJob({label='Gerenciador de arquivos',command=storage.command(request),storage=true,request=request})
end
local function finishJob(message)
    local success=message:sub(1,1)=='1'; local action=state.job.action; local output=util.trim(message:sub(2))
    if action.update then
        local ok,data=pcall(storage.decode,output)
        state.job=nil; back()
        if not ok or type(data)~='table' then textPage('Resposta não reconhecida',output); return end
        if data.ok and data.kind=='offer' then
            push({id='confirm',title=data.title,text=data.text,stage=1,scroll=0,action=updates.prepare(data.offer)})
        else
            textPage(data.title or 'Atualizar Port Doctor',data.text or output)
            state.lastOutput=tostring(data.title)..'\n'..tostring(data.text)
            if data.ok and data.kind=='ready' then state.updateExitTimer=2 end
        end
        return
    end
    if action.storage then
        local ok,data=pcall(storage.decode,output)
        state.job=nil; back()
        if not ok or type(data)~='table' then textPage('Falha no gerenciador','Não foi possível interpretar a resposta.\n'..output); return end
        if data.kind=='plan' and data.ok then
            push({id='confirm',title=data.title,stage=1,scroll=0,text=data.text,
                action={label=data.title,storage=true,operation=data.operation,command=storage.command({action='execute',root=data.root,token=data.token}),
                    confirmations=data.permanent and 2 or 1,finalConfirmation='APAGAR DEFINITIVAMENTE?\nNão será possível recuperar estes arquivos ou saves.\n\n'..data.text}})
        elseif (data.kind=='files' or data.kind=='trash') and data.ok then
            local page={id=data.kind,title=data.kind=='trash' and 'Lixeira' or (data.path=='' and 'Cartões de jogos' or data.path),
                path=data.path,parent=data.parent,items=data.items,offset=data.offset,total=data.total,free=data.free,selection=1}
            -- Keep one browser page in history, rather than a page per folder.
            while state.page.id=='file_options' or state.page.id=='folder_options' do back() end
            if state.page.id==data.kind then state.page=page else push(page) end
        else
            if data.ok and action.operation=='move' then state.clipboard=nil end
            state.lastOutput=(data.title or 'Arquivos')..'\n'..tostring(data.text or output)
            textPage(data.title or 'Arquivos',data.text or output)
            refreshPorts()
        end
        return
    end
    local heading=success and (action.requiresTest and 'Alteração aplicada. Teste o jogo no menu Ports.' or 'Ação executada.') or 'A ação não foi concluída.'
    if action.requiresTest and success then heading=heading..'\nIsso ainda NÃO confirma que o jogo funciona.' end
    state.lastOutput=action.label..'\n'..heading..'\n\n'..output; print('Port Doctor: '..state.lastOutput)
    state.job=nil; state.page={id='text',title='Resultado: '..action.label,text=heading..'\n\n'..output,scroll=0}
    refreshActions()
end
local function openAction(action)
    push({id='action',title=action.label,action=action,text=table.concat({tostring(action.value or ''),tostring(action.detail or ''),
        action.enabled and (action.requiresTest and 'Após aplicar: saia do Doctor, teste o jogo e volte para verificar. Há backup para desfazer.' or 'Pressione A para continuar.')
            or ('Indisponível: '..tostring(action.disabledReason or action.value or 'componente não disponível'))},'\n\n')})
end
local function primaryAction()
    local p=state.page
    if p.id=='exit' then love.event.quit(); return end
    if p.id=='action' then
        local action=p.action
        if not action.enabled then toast('Leia o motivo acima. B para voltar.'); return end
        if action.immediate then startJob(action) else
            local confirmation=action.confirmation
            confirmation = confirmation or "Executar esta ação de manutenção?"
            push({id='confirm',title='Confirmar manutenção',action=action,stage=1,text=confirmation..'\n\n'..tostring(action.detail or '')})
        end
        return
    elseif p.id=='confirm' then
        if p.stage<(p.action.confirmations or 1) then
            p.stage=p.stage+1; p.scroll=0; p.title='Confirmação final'; p.text=p.action.finalConfirmation or p.action.confirmation or 'Confirmar manutenção?'
        else startJob(p.action) end
        return
    end
    local entry=entries()[p.selection]; if not entry then return end
    if entry.storage then startStorage(entry.storage)
    elseif entry.folderOptions then push({id='folder_options',title='Opções da pasta',path=p.path,free=p.free})
    elseif entry.clipboard then state.clipboard={operation=entry.clipboard,path=entry.file.path,name=entry.file.name}; back(); toast('Escolha o destino e use Colar aqui')
    elseif entry.clearClipboard then state.clipboard=nil; toast('Área de transferência limpa')
    elseif entry.keyboard then push({id='keyboard',title=entry.label,request=entry.keyboard,typed=entry.keyboard.name or '',selection=1})
    elseif entry.trash then push({id='trash_options',title=entry.trash.name,item=entry.trash})
    elseif entry.file then
        if entry.file.directory then startStorage({action='list',path=entry.file.path})
        else push({id='file_options',title=entry.file.name,item=entry.file}) end
    elseif entry.action then openAction(entry.action)
    elseif entry.port then state.analyzedPort=entry.port; reanalyze(); push({id='port',title=entry.port})
    elseif entry.reanalyze then reanalyze(); toast('Diagnóstico atualizado')
    elseif entry.subpage then push({id=entry.subpage,title=(entry.subpage=='repair' and 'Correções: ' or 'Diagnóstico: ')..state.analyzedPort})
    elseif entry.page=='compatibility' then textPage('Modelo testado',
        'ATESTADO NO MODELO\nR36S-V30-2025-11-18-2603\n\nIdentificação da revisão informada pelo mantenedor.\n\nFirmware de referência: dArkOSRE, baseado em Debian 13, no aparelho usado para os testes do projeto.\n\nOutras revisões, clones e firmwares podem se comportar de forma diferente. Atestado neste modelo não significa que todos os jogos ou reparos funcionam.\n\nMantenha cópia dos seus saves e arquivos importantes.')
    elseif entry.page=='about' then textPage('Sobre o Port Doctor',
        'Port Doctor R36S 0.11.1\n\nCriado por fabriciopab\nhttps://github.com/Fabriciopab\nfabricio@byteforce-ai.com\n\nPix para contribuir:\nfabriciopab@hotmail.com\n\nAtestado no R36S-V30-2025-11-18-2603.\n\nProjeto comunitário com reparos protegidos e reversíveis.\n\nNão existe correção universal: dados ausentes, builds incompatíveis e falhas internas podem exigir intervenção do autor do port.\n\nObrigado às comunidades PortMaster, dArkOSRE e ArkOS.')
    elseif entry.page then push({id=entry.page,title=entry.label,group=entry.group,icon=entry.icon})
    else textPage(entry.label,tostring(entry.hint or '')..'\n\n'..tostring(entry.detail or '')) end
end
local function keyboardKeys()
    local keys={}; for c in ('abcdefghijklmnopqrstuvwxyz0123456789-_.'):gmatch('.') do keys[#keys+1]=c end
    keys[#keys+1]='ABC'; keys[#keys+1]='Espaço'; keys[#keys+1]='Apagar'; keys[#keys+1]='OK'; return keys
end
local function keyboardAction(action)
    local p=state.page; local keys=keyboardKeys()
    if action=='back' then back(); return end
    if action=='confirm' then
        local key=keys[p.selection]
        if key=='OK' then
            local r=p.request
            if r.updateRepository then local name=p.typed; back(); startJob(updates.configure(name))
            else r.action='plan'; r.name=p.typed; back(); startStorage(r) end
        elseif key=='ABC' then p.upper=not p.upper
        elseif key=='Apagar' then p.typed=p.typed:sub(1,(require('utf8').offset(p.typed,-1) or 1)-1)
        elseif #p.typed<160 then p.typed=p.typed..(key=='Espaço' and ' ' or (p.upper and key:upper() or key)) end
    else
        local delta=({up=-8,down=8,left=-1,right=1})[action]
        if delta then p.selection=util.clamp(p.selection+delta,1,#keys) end
    end
end
local function handleAction(action)
    if state.cooldown>0 or state.job or state.analysis or state.updateExitTimer then return end
    state.cooldown=.13; local p=state.page
    if p.id=='keyboard' then keyboardAction(action); return end
    if action=='confirm' then primaryAction()
    elseif action=='back' then
        if p.id=='files' and p.path~='' then startStorage({action='list',path=p.parent}) else back() end
    elseif action=='export' then
        if p.id=='files' then local e=entries()[p.selection]; if e and e.file then push({id='file_options',title=e.file.name,item=e.file}) end
        else report() end
    elseif action=='refresh' then
        if p.id=='files' then startStorage({action='list',path=p.path,offset=p.offset})
        elseif p.id=='trash' then startStorage({action='trash'})
        elseif p.id=='network' then startJob(storage.networkActions()[1])
        elseif p.id=='ports' then refreshPorts()
        elseif p.id=='port' or p.id=='port_results' then reanalyze()
        elseif p.id=='repair' or p.id=='tools' then refreshActions()
        elseif p.id=='battery' then startJob(battery.actions()[1])
        elseif p.id=='memory' then startJob(memory.actions()[1])
        else refreshSystem() end
    else
        local delta=(action=='up' or action=='left') and -1 or 1
        if p.text then p.scroll=util.clamp((p.scroll or 0)+delta*((action=='left' or action=='right') and 9 or 1),0,p.maxScroll or 0)
        else p.selection=util.clamp((p.selection or 1)+delta*((action=='left' or action=='right') and 5 or 1),1,math.max(1,#entries())) end
    end
end
function love.load()
    fonts.small=lg.newFont(18); fonts.body=lg.newFont(22); fonts.title=lg.newFont(26); fonts.badge=lg.newFont(16)
    refreshSystem(); refreshPorts(); refreshActions()
    if os.getenv('PORTDOCTOR_SMOKE_TEST')=='1' then state.smokeTimer=2 end
    if os.getenv('PORTDOCTOR_UI_TEST')=='1' then state.uiTest=0; state.uiIndex=0; state.scanning=false end
end
function love.update(dt)
    state.cooldown=math.max(0,state.cooldown-dt); state.toastTime=math.max(0,state.toastTime-dt)
    if state.updateExitTimer then
        state.updateExitTimer=state.updateExitTimer-dt
        if state.updateExitTimer<=0 then love.event.quit(); return end
    end
    if state.job then
        local message=state.job.channel:pop()
        if message then finishJob(message)
        elseif not state.job.thread:isRunning() then finishJob('0'..(state.job.thread:getError() or 'Tarefa terminou sem resposta.')) end
    end
    if state.analysis then
        local message=state.analysis.channel:pop()
        if not message and not state.analysis.thread:isRunning() then
            message={ok=false,error=state.analysis.thread:getError() or 'Análise terminou sem resposta.'}
        end
        if message then
            state.analysis=nil
            if message.ok then
                state.portResults=message.results; state.portDetails=message.details
                state.repairActions=repairs.actions(state.portDetails)
            else
                state.portDetails=nil; state.repairActions=repairs.actions(nil)
                textPage('Falha na análise',message.error)
            end
        end
    end
    if state.scanning and not state.job and not state.analysis then
        local task=state.tasks[state.taskIndex]
        if task then
            local ok,result=pcall(task)
            state.results[#state.results+1]=ok and result or {group='system',label='Verificação interna',value='falhou',detail=tostring(result),status='error'}
            state.taskIndex=state.taskIndex+1
        else state.scanning=false end
    end
    if state.smokeTimer then state.smokeTimer=state.smokeTimer-dt
        if state.smokeTimer<=0 then print('Port Doctor: smoke test concluído'); love.event.quit() end
    end
    if state.uiTest then
        state.uiTest=state.uiTest+dt
        if state.uiTest>.4 then
            state.uiTest=0; state.uiIndex=state.uiIndex+1
            if state.uiIndex==1 then
                local ok,data=pcall(function() return storage.decode(util.run(storage.command({action='list',path=state.portsRoot}))) end)
                state.previewFiles=ok and data.items or {}
            end
            local tour={
                {id='home',title='Port Doctor R36S',selection=1},
                {id='ports',title='Meus ports',selection=1},
                {id='battery',title='Bateria',selection=1},
                {id='action',title='Diagnóstico do port',text='O jogo registrou SIGBUS.\n\nO diagnóstico identifica a falha, mas não prova sua causa.\n\nUma alteração aplicada não é garantia de que o jogo abriu.',action={enabled=false}},
                {id='text',title='Resultado do diagnóstico',text=string.rep('Mensagem longa para testar leitura e rolagem em tela inteira.\n',30)},
                {id='tools',title='USB e Wi-Fi',selection=3,group='USB'},
                {id='files',title=state.portsRoot,path=state.portsRoot,parent='/roms',items=state.previewFiles,selection=2},
                {id='cleanup',title='Limpeza e lixeira',selection=1},
                {id='network',title='Rede e Wi-Fi',selection=1},
                {id='keyboard',title='Criar pasta',typed='Nova pasta',selection=1},
                {id='support',title='Contribuir com o projeto',icon='heart',selection=1},
                {id='updates',title='Atualizar Port Doctor',icon='update',selection=1},
                {id='home',title='Port Doctor R36S',selection=14},
                {id='memory',title='Memória e zram',selection=4,icon='system'},
                {id='battery',title='Bateria e desempenho',selection=5,icon='battery'},
                {id='tools',title='Jogos em rede',group='REDE',selection=1,icon='network'},
                {id='battery',title='Bateria e desempenho',selection=8,icon='battery'},
            }
            if tour[state.uiIndex] then state.page=tour[state.uiIndex]; state.page.scroll=0; state.capture='ui-'..state.uiIndex..'.png'
            else print('Port Doctor: UI tour OK'); love.event.quit() end
        end
    end
end
local function fit(text,font,width)
    text=tostring(text or '')
    if font:getWidth(text)<=width then return text end
    local utf8=require('utf8')
    while #text>0 and font:getWidth(text..'…')>width do text=text:sub(1,(utf8.offset(text,-1) or 1)-1) end
    return text..'…'
end
local function drawText(p)
    lg.setFont(fonts.body); local _,lines=fonts.body:getWrap(tostring(p.text or ''),574); local visible=10
    p.maxScroll=math.max(0,#lines-visible); p.scroll=util.clamp(p.scroll or 0,0,p.maxScroll); color(colors.text)
    for i=1,visible do if lines[p.scroll+i] then lg.print(lines[p.scroll+i],30,100+(i-1)*29) end end
    if p.maxScroll>0 then
        lg.setFont(fonts.small); color(colors.muted)
        lg.printf('D-pad: rolar   '..(p.scroll+1)..'–'..math.min(#lines,p.scroll+visible)..' / '..#lines,28,403,584,'right')
    end
end
local function drawList(p)
    local list=entries(); p.selection=util.clamp(p.selection or 1,1,math.max(1,#list)); local start=math.floor((p.selection-1)/5)*5+1
    if #list==0 then
        lg.setFont(fonts.body); color(colors.muted)
        lg.printf(state.scanning and 'Verificando… aguarde.' or 'Nenhum item disponível.\nY atualiza esta página.',30,170,580,'center')
    end
    for row=0,4 do
        local index=start+row; local entry=list[index]
        if entry then
            local y=92+row*65; panel(22,y,596,59,index==p.selection and colors.selected or colors.panel)
            panel(30,y+7,44,44,{.075,.145,.17})
            icons.draw(icons.forEntry(entry,p.id),37,y+14,30)
            color(index==p.selection and colors.accent or colors.text); lg.setFont(fonts.body)
            lg.print(fit(entry.label,fonts.body,505),87,y+5)
            lg.setFont(fonts.small); color(colors[entry.status] or colors.muted); lg.print(fit(entry.hint or 'A para abrir',fonts.small,505),87,y+34)
        end
    end
    lg.setFont(fonts.small); color(colors.muted)
    lg.printf(#list>0 and (p.selection..' / '..#list..'   L/R muda página') or '',24,66,592,'right')
end
local function drawSupport()
    icons.draw('heart',289,80,62)
    lg.setFont(fonts.body); color(colors.text); lg.printf('Ajude no avanço do Port Doctor',28,166,584,'center')
    lg.setFont(fonts.small); color(colors.muted); lg.printf('Sua contribuição apoia melhorias e novos testes.',30,205,580,'center')
    panel(26,250,588,90,colors.selected)
    lg.setFont(fonts.small); color(colors.accent); lg.printf('CHAVE PIX — E-MAIL',38,263,564,'center')
    lg.setFont(fonts.title); color(colors.text); lg.printf('fabriciopab@hotmail.com',38,293,564,'center')
    lg.setFont(fonts.small); color(colors.muted)
    lg.printf('Contribuição voluntária. O app continua gratuito.\nConfira o destinatário no seu banco antes de confirmar.',26,369,588,'center')
end
local function drawKeyboard(p)
    lg.setFont(fonts.body); color(colors.text); lg.printf(p.typed..'_',26,86,588,'left')
    lg.setFont(fonts.small); color(colors.muted); lg.print('Nome: até 160 bytes. Sem / ou \\',26,126)
    for i,key in ipairs(keyboardKeys()) do
        local x=24+((i-1)%8)*74; local y=165+math.floor((i-1)/8)*42
        panel(x,y,69,36,i==p.selection and colors.selected or colors.panel)
        color(i==p.selection and colors.accent or colors.text)
        lg.printf(p.upper and #key==1 and key:upper() or key,x,y+7,69,'center')
    end
end
function love.draw()
    local width,height=lg.getDimensions(); lg.push(); lg.scale(width/640,height/480)
    color(colors.bg); lg.rectangle('fill',0,0,640,480); color(colors.panel); lg.rectangle('fill',0,0,640,60)
    color(colors.accent); lg.rectangle('fill',0,0,6,60); lg.setFont(fonts.title); color(colors.text)
    icons.draw(state.page.id=='home' and 'handheld' or state.page.icon or icons.forEntry({},state.page.id),24,14,32)
    lg.print(fit(state.page.title,fonts.title,544),72,15)
    if state.page.id=='home' then lg.setFont(fonts.small); color(colors.muted); lg.print('v0.11.1',24,66) end
    if state.analysis then
        lg.setFont(fonts.body); color(colors.info)
        lg.printf('Analisando '..tostring(state.analyzedPort)..'…\n\nVerificando arquivos, dependências e logs.\nAguarde a conclusão.',35,150,570,'center')
    elseif state.job then
        lg.setFont(fonts.body); color(colors.info); lg.printf('Executando…\n\nNão desligue o aparelho.\nO resultado aparecerá nesta tela.',35,160,570,'center')
    elseif state.page.id=='support' then drawSupport()
    elseif state.page.id=='keyboard' then drawKeyboard(state.page)
    elseif state.page.text then drawText(state.page) else drawList(state.page) end
    color(colors.panel); lg.rectangle('fill',0,436,640,44); lg.setFont(fonts.small); color(colors.text)
    local footer='A abrir   B voltar   Y atualizar   X relatório'
    if state.updateExitTimer then footer='Fechando para instalar. Não desligue o console.'
    elseif state.page.id=='home' then footer='A abrir   B sair   D-pad escolher'
    elseif state.page.id=='confirm' then footer='A confirmar   B cancelar   D-pad ler'
    elseif state.page.id=='action' then footer='A continuar   B voltar   D-pad ler'
    elseif state.page.id=='text' then footer='B voltar   D-pad rolar   X relatório'
    elseif state.page.id=='exit' then footer='A sair   B cancelar'
    elseif state.page.id=='files' then footer='A abrir   X opções   B subir   Y atualizar'
    elseif state.page.id=='keyboard' then footer='D-pad escolher   A digitar   B cancelar'
    elseif state.page.id=='support' then footer='B voltar   Obrigado por apoiar o projeto!'
    elseif state.job or state.analysis then footer='Aguarde a conclusão da tarefa' end
    lg.printf(footer,18,449,604,'center')
    if state.page.id=='home' then
        lg.setFont(fonts.badge); color(colors.muted)
        lg.printf('Atestado: R36S-V30-2025-11-18-2603',24,415,592,'center')
    end
    if state.toastTime>0 then panel(22,355,596,72,colors.selected); lg.setFont(fonts.body); color(colors.text); lg.printf(state.toast,35,366,570,'center') end
    lg.pop()
    if state.capture then lg.captureScreenshot(state.capture); state.capture=nil end
end
function love.keypressed(key)
    local map={up='up',down='down',left='left',right='right',['return']='confirm',kpenter='confirm',z='confirm',escape='back',x='back',a='export',q='refresh',s='left',w='right',r='refresh'}
    if map[key] then handleAction(map[key]) end
end
function love.gamepadpressed(_,button)
    local map={dpup='up',dpdown='down',dpleft='left',dpright='right',a='confirm',b='back',x='export',y='refresh',leftshoulder='left',rightshoulder='right'}
    if map[button] then handleAction(map[button]) end
end
function love.joystickpressed(joystick,button)
    if joystick:isGamepad() then return end
    local map={[1]='back',[2]='confirm',[3]='export',[4]='refresh',[5]='left',[6]='right'}
    if map[button] then handleAction(map[button]) end
end
