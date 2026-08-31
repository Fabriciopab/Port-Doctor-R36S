local util=require('src.util')
local json=require('src.json')
local storage={}
local networkCache
function storage.command(request)
    local home=os.getenv('PORTDOCTOR_HOME') or ''
    assert(home~='', 'Diretório do Port Doctor não configurado')
    return 'python3 '..util.shellQuote(home..'/tools/file_manager.py')..' '..util.shellQuote(json.encode(request))
end
function storage.decode(text) return json.decode(text) end
function storage.networkActions()
    if networkCache then return networkCache end
    local home=os.getenv('PORTDOCTOR_HOME') or ''
    local helper=home..'/tools/network_status.py'
    local enabled=home~='' and util.testFile(helper)
    local base='python3 '..util.shellQuote(helper)..' '
    networkCache={
        {id='network_info',label='Informações de rede',value='IP, MAC, DNS e conexão',enabled=enabled,immediate=true,command=base..'status',
            detail='Consulta interfaces USB, Wi-Fi e Ethernet sem exibir senhas.'},
        {id='wifi_on',label='Ativar Wi-Fi',value='Rádio / redes já salvas',enabled=enabled,command=base..'on',
            detail='Usa NetworkManager quando disponível. Sem dongle detectado, não haverá conexão. Para cadastrar rede/senha, use o menu do firmware.',
            confirmation='Habilitar o rádio Wi-Fi? Não muda o modo USB/OTG nem reinicia o aparelho.'},
        {id='wifi_off',label='Desativar Wi-Fi',value='Interrompe conexões sem fio',enabled=enabled,command=base..'off',
            detail='Transferências, SSH e jogos em rede pelo Wi-Fi serão desconectados. USB e Ethernet não são desligados.',
            confirmation='Desativar Wi-Fi? Termine transferências e saia dos jogos em rede antes de confirmar.'},
    }
    return networkCache
end
return storage
