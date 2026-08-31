local util=require('src.util')
local updates={}
function updates.action(verb,extra)
    local helper=(os.getenv('PORTDOCTOR_HOME') or '')..'/tools/updater.py'
    return {label='Atualizar Port Doctor',update=true,enabled=true,immediate=true,
        command='python3 '..util.shellQuote(helper)..' '..verb..(extra or '')}
end
function updates.prepare(offer)
    return updates.action('prepare',' --release-id '..tostring(tonumber(offer.id))..' --sha256 '..util.shellQuote(offer.sha256))
end
function updates.configure(name) return updates.action('configure',' --repository '..util.shellQuote(name)) end
function updates.cancelAction()
    local action=updates.action('cancel'); action.immediate=false; action.label='Descartar atualização pendente'
    action.detail='Remove somente o download e o agendamento. Não desfaz alterações já aplicadas; preserva registros e backups.'
    action.confirmation='Descartar o pacote baixado e liberar uma nova tentativa de atualização?'
    return action
end
return updates
