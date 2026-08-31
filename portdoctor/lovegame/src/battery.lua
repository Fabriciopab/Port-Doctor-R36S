local util = require('src.util')
local battery = {}
local cached
function battery.actions()
    if cached then return cached end
    local helper=(os.getenv('PORTDOCTOR_HOME') or '')..'/tools/battery.py'
    local exists=util.testFile(helper)
    local function action(id,label,value,detail,root)
        return {id='battery_'..id,label=label,value=value,detail=detail,enabled=exists,
            command=(root and 'sudo -n ' or '')..'python3 '..util.shellQuote(helper)..' '..id,
            immediate=not root,confirmation=detail..' Aplicar agora?',area='battery',
            disabledReason=exists and nil or 'componente de bateria ausente'}
    end
    cached={
        action('status','Ver estado da bateria','Carga, consumo e temperatura','Consulta os sensores disponíveis. Não modifica o aparelho.',false),
        action('restore','1. Padrão do aparelho','Recomendado: ajustes anteriores','Restaura somente o que o Doctor mudou neste boot, sem inventar valores de fábrica. Preserva mudanças posteriores do firmware.',true),
        action('balanced','2. Equilibrado','Recomendado para o uso diário','CPU sob demanda, usando ondemand, schedutil ou interactive disponível. Não muda brilho nem limites de frequência. Vale neste boot.',true),
        action('economy','3. Economia','Recomendado para jogos leves','Reduz o brilho para no máximo 30% e usa conservative se suportado. Pode reduzir o desempenho dos jogos. Vale neste boot e tem restauração.',true),
        action('performance','4. Desempenho','Opcional: maior consumo e calor','Usa performance dentro do limite já configurado, sem overclock. Só RK3326 até 1,512 GHz, sensor abaixo de 65 °C e carga não inferior a 20% quando informada. A checagem térmica é apenas na ativação. Se aquecer, volte ao Equilibrado.',true),
        action('dimmer','Diminuir brilho','Menos 10 pontos percentuais','Reduz o brilho sem apagar a tela; mínimo de 15%.',true),
        action('brighter','Aumentar brilho','Mais 10 pontos percentuais','Aumenta o brilho dentro do limite do aparelho; pode aumentar o consumo.',true),
    }
    return cached
end
return battery
