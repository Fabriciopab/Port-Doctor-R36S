local util=require('src.util')
local memory={}
function memory.actions()
    local helper=(os.getenv('PORTDOCTOR_HOME') or '')..'/tools/memory.py'
    local function action(id,label,value,detail)
        return {id='memory_'..id,label=label,value=value,detail=detail,enabled=util.testFile(helper),
            command='sudo -n python3 '..util.shellQuote(helper)..' '..id,immediate=id=='status',
            confirmation=detail..' Aplicar agora?',disabledReason='Componente de memória ausente'}
    end
    return {
        action('status','Ver memória e recomendação','RAM, zram e tamanhos calculados','Consulta somente; não altera a memória.'),
        action('restore','Padrão do aparelho','Recomendado se os jogos já funcionam','Remove somente a área criada pelo Doctor neste boot, se não houver páginas em uso. Não desativa swap do firmware.'),
        action('25','Zram leve: 25% da RAM','Opcional: menor área comprimida','Cria uma área própria em RAM. Não escreve swap no cartão. Pode aumentar uso de CPU; vale até reiniciar.'),
        action('50','Zram equilibrada: 50%','Sugestão inicial para falta de memória','Cria uma área própria em RAM, se não há zram do firmware. Recomendação conservadora do projeto, não ganho de FPS garantido. Vale até reiniciar.'),
        action('75','Zram ampliada: 75%','Avançado: testar consumo e travamentos','Maior espaço lógico comprimido, não RAM física adicional. Pode piorar desempenho. Não troca áreas com páginas em uso. Vale até reiniciar.'),
    }
end
return memory
