-- Headless navigation regression. Stubs isolate the UI from system writes.
package.path='portdoctor/lovegame/?.lua;'..package.path
local draws,executed={},0
local function noop() end
local font={}
function font:getWidth(s) return #tostring(s)*10 end
function font:getWrap(s,w)
    local lines={}; for line in (s..'\n'):gmatch('(.-)\n') do lines[#lines+1]=line end
    return w,lines
end
package.preload['utf8']=function() return {offset=function(s) local i=#s; while i>1 and s:byte(i)>=128 and s:byte(i)<192 do i=i-1 end; return i end} end
local function result(label) return {group='system',label=label,value='OK',detail=string.rep('Detalhe\n',25),status='info'} end
package.preload['src.diagnostics']=function() return {
    systemTasks=function() return {function() return result('Sistema') end} end,
    scanPorts=function() return {'hollowknight','blazingbeaks'},'/roms/ports' end,
    analyzePort=function() return {result('Causa provável')},{name='hollowknight'} end,
    exportReport=function() return true end,
} end
local action={id='auto_repair',label='Corrigir',value='Disponível',detail='Backup',enabled=true,command='TEST',requiresTest=true}
local verify={id='verify',label='Verificar',value='Novo log',enabled=true,command='TEST',immediate=true}
package.preload['src.repairs']=function() return {actions=function() return {action,verify} end} end
package.preload['src.tools']=function() return {actions=function() return {{id='usb',label='USB',group='USB',value='Reinicia',detail='Teste',enabled=true,command='TEST',confirmations=2}} end} end
package.preload['src.battery']=function() return {actions=function() return {verify} end} end
local channel={pop=function(self) local m=self.message; self.message=nil; return m end}
love={
    graphics={setColor=noop,rectangle=noop,push=noop,pop=noop,scale=noop,translate=noop,line=noop,circle=noop,polygon=noop,setLineWidth=noop,setFont=noop,newFont=function() return font end,
        getRendererInfo=function() return 'GL' end,getDimensions=function() return 640,480 end,
        print=function(text) draws[#draws+1]=text end,printf=function(text) draws[#draws+1]=text end},
    timer={getTime=function() return 1 end},event={quit=function() love.exited=true end},
    thread={getChannel=function() return channel end,newThread=function(code) return {start=function()
        if code:find('analyzePort',1,true) then
            channel.message={ok=true,results={result('Causa provável')},details={name='hollowknight'}}
        else executed=executed+1; channel.message='1Testado' end
    end,isRunning=function() return true end} end},
}
dofile('portdoctor/lovegame/main.lua')
love.load()
local function draw()
    draws={}; love.draw(); return table.concat(draws,'\n')
end
local function key(k) love.update(.2); love.keypressed(k); love.update(.2); return draw() end
assert(draw():find('Port Doctor R36S',1,true))
assert(key('return'):find('Meus ports',1,true))
assert(key('return'):find('hollowknight',1,true))
assert(key('return'):find('Após aplicar',1,true))
assert(key('return'):find('Confirmar manutenção',1,true)) -- nil confirmation must not crash
assert(executed==0)
assert(key('x'):find('Após aplicar',1,true)) -- cancel
key('return'); local output=key('return')
assert(executed==1 and output:find('NÃO confirma',1,true))
key('x'); key('x'); key('down')
assert(key('return'):find('Diagnóstico:',1,true))
assert(key('return'):find('Causa provável',1,true))
key('down'); key('right'); key('right') -- scrolling and clamping
key('x'); key('x'); key('down')
assert(key('return'):find('Verificar',1,true))
key('return'); assert(executed==2) -- immediate, read-only action
key('x'); key('x'); key('x'); key('x')
assert(draw():find('Port Doctor R36S',1,true))
key('down'); key('return')
assert(draw():find('Bateria',1,true))
key('x'); key('x'); assert(not love.exited)
key('x'); assert(not love.exited)
key('x'); key('return'); assert(love.exited)
print('UI navigation, cancel, nil confirmation, result, scroll, immediate action and exit: OK')
