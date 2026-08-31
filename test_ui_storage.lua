package.path='portdoctor/lovegame/?.lua;'..package.path
local json=require('src.json')
assert(json.decode('{"path":"a\\n\\u00e7\\ud83c\\udfae","items":[true,false,12]}').path=='a\nç🎮')
assert(json.decode(json.encode({path="a'\"\\\nç"})).path=="a'\"\\\nç")
assert(not pcall(json.decode,'{"x":os.execute("anything")}'))
assert(not pcall(json.decode,'{"x":"\\ud800"}'))
local requests,draws={},{}
local function noop() end
local font={getWidth=function(_,s) return #tostring(s)*8 end,getWrap=function(_,s)
    local lines={}; for line in (s..'\n'):gmatch('(.-)\n') do lines[#lines+1]=line end; return 500,lines end}
package.preload['utf8']=function() return {offset=function(s) local i=#s; while i>1 and s:byte(i)>=128 and s:byte(i)<192 do i=i-1 end; return i end} end
package.preload['src.diagnostics']=function() return {systemTasks=function() return {} end,scanPorts=function() return {},'/roms/ports' end} end
package.preload['src.repairs']=function() return {actions=function() return {} end} end
package.preload['src.tools']=function() return {actions=function() return {} end} end
package.preload['src.battery']=function() return {actions=function() return {} end} end
package.preload['src.storage']=function() return {command=function(r) return json.encode(r) end,decode=json.decode,networkActions=function() return {} end} end
local function response(r)
    if r.action=='list' then
        local path=r.path or ''; local items={}; local parent=''
        if path=='' then items={{name='/roms',path='/roms',directory=true}}
        elseif path=='/roms' then items={{name='example',path='/roms/example',directory=true}}
        else parent='/roms'; items={{name='data.txt',path=path..'/data.txt',directory=false}} end
        return {ok=true,kind='files',path=path,parent=parent,items=items,free='1 GiB'}
    elseif r.action=='plan' then return {ok=true,kind='plan',title='Prévia',text='CONFIRA OS CAMINHOS',token='abc',root='/roms',permanent=r.operation=='purge',operation=r.operation}
    elseif r.action=='execute' then return {ok=true,kind='text',title='Concluído',text='TESTE'}
    elseif r.action=='trash' then return {ok=true,kind='trash',items={{name='Jogo excluído',path='/roms/.portdoctor-trash/abc'}}}
    end
    return {ok=true,kind='text',title='Detalhes',text='somente leitura'}
end
-- JSON encoder above intentionally only emits objects. Serialize fixture arrays explicitly.
local function encode(v)
    if type(v)~='table' then return json.encode(v) end
    if #v>0 then local t={}; for _,x in ipairs(v) do t[#t+1]=encode(x) end; return '['..table.concat(t,',')..']' end
    local t={}; for k,x in pairs(v) do t[#t+1]=json.encode(k)..':'..encode(x) end; return '{'..table.concat(t,',')..'}'
end
local channel={pop=function(self) local m=self.message; self.message=nil; return m end}
love={graphics={setColor=noop,rectangle=noop,push=noop,pop=noop,scale=noop,translate=noop,line=noop,circle=noop,polygon=noop,setLineWidth=noop,setFont=noop,newFont=function() return font end,
    getDimensions=function() return 640,480 end,getRendererInfo=function() return 'GL' end,
    print=function(t) draws[#draws+1]=t end,printf=function(t) draws[#draws+1]=t end},
    timer={getTime=function() return 1 end},event={quit=noop},
    thread={getChannel=function() return channel end,newThread=function() return {start=function(_,command)
        local r=json.decode(command); requests[#requests+1]=r; channel.message='1'..encode(response(r))
    end,isRunning=function() return true end} end}}
dofile('portdoctor/lovegame/main.lua'); love.load()
local function draw() draws={}; love.draw(); return table.concat(draws,'\n') end
local function key(k) love.update(.2); love.keypressed(k); love.update(.2); return draw() end
local function executions() local n=0; for _,r in ipairs(requests) do if r.action=='execute' then n=n+1 end end; return n end
key('down'); key('down'); assert(key('return'):find('Cartões de jogos',1,true))
key('return'); key('down'); assert(key('a'):find('Recortar',1,true)) -- X options
key('down'); key('return') -- copy selection, no execution
assert(executions()==0)
assert(draw():find('Colar aqui',1,true))
assert(key('return'):find('CONFIRA OS CAMINHOS',1,true))
key('x'); assert(executions()==0) -- cancelling preview never executes
key('return'); key('return'); assert(executions()==1)
key('x'); key('up'); key('return') -- folder options
assert(key('return'):find('Nome:',1,true)) -- full-screen keyboard
key('return') -- letter a
assert(draw():find('a_',1,true))
key('x'); key('x') -- keyboard cancellation
key('x'); key('x') -- root, home
key('down'); key('return') -- cleanup
assert(draw():find('Limpeza e lixeira',1,true))
key('down'); key('return'); key('return'); key('down'); key('return') -- purge preview
assert(executions()==1)
assert(key('return'):find('APAGAR DEFINITIVAMENTE',1,true)) -- second confirmation
key('x'); assert(executions()==1)
key('return'); key('return'); key('return'); assert(executions()==2)
print('Storage UI: JSON, browse, clipboard, preview cancel, keyboard, trash double confirmation: OK')
