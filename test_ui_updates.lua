-- UI-only updater test: no downloads, shutdowns or installation of real files.
package.path='portdoctor/lovegame/?.lua;'..package.path
local json=require('src.json')
local draws,prepared={},0
local function noop() end
local function polygon(mode,...)
    local points={...}
    assert(#points>=6 and #points%2==0)
    assert(points[1]~=points[#points-1] or points[2]~=points[#points], 'Polygon closes itself; repeated endpoint breaks outline on GLES')
end
local font={getWidth=function(_,s) return #tostring(s)*8 end,getWrap=function(_,s)
    local lines={}; for line in (s..'\n'):gmatch('(.-)\n') do lines[#lines+1]=line end; return 500,lines end}
package.preload['utf8']=function() return {offset=function(s) local i=#s; while i>1 and s:byte(i)>=128 and s:byte(i)<192 do i=i-1 end; return i end} end
package.preload['src.diagnostics']=function() return {systemTasks=function() return {} end,scanPorts=function() return {},'/roms/ports' end} end
package.preload['src.repairs']=function() return {actions=function() return {} end} end
package.preload['src.tools']=function() return {actions=function() return {} end} end
package.preload['src.battery']=function() return {actions=function() return {} end} end
local channel={pop=function(self) local m=self.message; self.message=nil; return m end}
love={graphics={setColor=noop,rectangle=noop,push=noop,pop=noop,scale=noop,translate=noop,line=noop,circle=noop,polygon=polygon,setLineWidth=noop,setFont=noop,newFont=function() return font end,
    getDimensions=function() return 640,480 end,getRendererInfo=function() return 'GL' end,
    print=function(t) draws[#draws+1]=t end,printf=function(t) draws[#draws+1]=t end},
    timer={getTime=function() return 1 end},event={quit=function() love.exited=true end},
    thread={getChannel=function() return channel end,newThread=function() return {start=function(_,command)
        local data
        if command:find('prepare',1,true) then prepared=prepared+1; data={ok=true,kind='ready',title='Validado',text='Fechando para instalar'}
        else data={ok=true,kind='offer',title='Atualização disponível',text='DOWNLOAD REQUER CONFIRMAÇÃO',offer={id=123,sha256=string.rep('a',64)}} end
        channel.message='1'..json.encode(data)
    end,isRunning=function() return true end} end}}
dofile('portdoctor/lovegame/main.lua'); love.load()
local function draw() draws={}; love.draw(); return table.concat(draws,'\n') end
local function key(k) love.update(.2); love.keypressed(k); love.update(.2); return draw() end
assert(draw():find('R36S-V30-2025-11-18-2603',1,true))
for i=1,14 do key('down') end
assert(key('return'):find('fabriciopab@hotmail.com',1,true))
assert(draw():find('voluntária',1,true))
key('x'); key('down'); assert(key('return'):find('ATESTADO NO MODELO',1,true))
key('x'); key('up'); key('up'); key('return') -- updater at index 14
key('return'); assert(key('return'):find('DOWNLOAD REQUER CONFIRMAÇÃO',1,true))
assert(prepared==0 and not love.exited)
key('x'); assert(prepared==0 and not love.exited)
key('return'); assert(key('return'):find('Fechando para instalar',1,true))
assert(prepared==1 and not love.exited)
key('x'); assert(not love.exited) -- input cannot interrupt a queued, confirmed installation
love.update(2.1); assert(love.exited)
print('Icons, Pix, model notice and updater confirmation/exit workflow: OK')
