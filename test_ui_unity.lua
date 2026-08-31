-- Repair actions exposed only for recognized builds; no real files are modified.
package.path='portdoctor/lovegame/?.lua;'..package.path
local realenv=os.getenv
os.getenv=function(name) if name=='PORTDOCTOR_HOME' then return '/roms/ports/portdoctor' end; return realenv(name) end
package.preload['src.diagnostics']=function() return {portMasterHome=function() return '/PortMaster' end} end
package.preload['src.util']=function() return {
    trim=function(x) return tostring(x or ''):match('^%s*(.-)%s*$') end,
    testFile=function() return true end,run=function() return '' end,lines=function() return {} end,
    shellQuote=function(x) return "'"..x.."'" end,basename=function(x) return x:match('[^/]+$') end,
} end
local repairs=require('src.repairs')
local details={name='hollowknight',path='/roms/ports/hollowknight',launchers={'/roms/ports/HollowKnight.sh'},
    architectures={'aarch64'},runtimes={},missing={},issues={{kind='unity_egl'}}}
local function actions()
    local found={}
    for _,action in ipairs(repairs.actions(details)) do found[action.id]=action end
    return found
end
local found=actions()
assert(found.auto_repair.enabled and found.auto_repair.command:find('auto%-repair'))
assert(found.unity_egl.enabled and found.unity_egl.command:find('unity%-egl'))
assert(found.unity_egl.confirmation and found.unity_egl.requiresTest)
details.issues={{kind='unity_graphics'}}
found=actions()
assert(found.auto_repair.enabled)
assert(found.unity_graphics.enabled and found.unity_graphics.command:find('unity%-graphics'))
assert(found.unity_graphics.confirmation and found.unity_graphics.requiresTest)
assert(found.unity_graphics.detail:find('limite de quadros',1,true))
details.issues={{kind='native_crash'}}
found=actions()
assert(not found.unity_egl and not found.unity_graphics and not found.auto_repair.enabled)
details.issues={}
found=actions()
assert(not found.unity_egl and not found.unity_graphics)
print('Unity actions, confirmation, tested-build gating and frame-cap preservation notice: OK')
