-- Original code-drawn icons: no fonts, external downloads or bitmap scaling.
local icons={}
local g=love.graphics
local function line(...) g.line(...) end
local function box(x,y,w,h,r) g.rectangle('line',x,y,w,h,r or 2,r or 2) end
local function circle(x,y,r) g.circle('line',x,y,r) end
local drawings={
    handheld=function() box(5,1,22,30,4); box(8,4,16,13,1); line(9,23,15,23); line(12,20,12,26); circle(22,22,1); circle(19,25,1); circle(12,28,1); circle(22,28,1) end,
    game=function() box(2,8,28,18,6); line(7,17,15,17); line(11,13,11,21); circle(23,14,1.3); circle(20,20,1.3) end,
    battery=function() box(2,8,26,16,3); line(30,13,30,19); line(8,12,8,20); line(13,12,13,20); line(18,12,18,20) end,
    folder=function() g.polygon('line',2,8,13,8,16,11,30,11,28,27,3,27); line(3,8,3,5,13,5,16,8) end,
    file=function() g.polygon('line',7,2,20,2,27,9,27,30,7,30); line(20,2,20,10,27,10); line(11,16,22,16); line(11,21,22,21) end,
    trash=function() box(7,9,18,21,2); line(4,7,28,7); line(11,7,11,3,21,3,21,7); line(12,13,12,25); line(20,13,20,25) end,
    wifi=function() line(2,11,7,7,12,5,20,5,25,7,30,11); line(7,17,11,13,16,12,21,13,25,17); line(12,23,16,20,20,23); circle(16,28,1) end,
    system=function() box(7,7,18,18,3); box(12,12,8,8,1); for n=10,22,6 do line(n,2,n,6); line(n,26,n,30); line(2,n,6,n); line(26,n,30,n) end end,
    display=function() box(2,4,28,21,3); line(16,25,16,30); line(9,30,23,30); line(7,19,12,14,16,17,23,10) end,
    package=function() g.polygon('line',16,2,29,9,29,24,16,31,3,24,3,9); line(3,9,16,16,29,9); line(16,16,16,31); line(10,6,23,13) end,
    image=function() box(3,3,26,26,3); circle(11,11,3); line(5,26,14,17,19,22,24,15,28,19) end,
    usb=function() line(16,29,16,4,12,8); line(16,4,20,8); line(16,22,7,17,7,11); circle(7,9,2); line(16,17,24,13,24,8); box(22,4,4,4,0) end,
    network=function() box(10,2,12,8); box(1,22,12,8); box(19,22,12,8); line(16,10,16,17); line(7,22,7,17,25,17,25,22) end,
    disk=function() box(3,5,26,23,4); line(4,20,28,20); circle(24,24,1); line(8,11,23,11) end,
    wrench=function() line(20,4,17,10,22,15,29,12,28,18,22,21,17,19,8,29,3,24,13,14,11,8,14,3,20,4); circle(7,25,1) end,
    info=function() circle(16,16,13); circle(16,9,1); line(14,14,17,14,17,24); line(13,24,20,24) end,
    heart=function() g.polygon('line',16,28,3,16,2,10,5,5,11,4,16,9,21,4,27,5,30,10,29,16) end,
    update=function() line(4,12,7,6,14,3,22,5,27,11); line(27,3,27,11,19,11); line(28,20,25,26,18,29,10,27,5,21); line(5,29,5,21,13,21) end,
    shield=function() g.polygon('line',16,2,28,7,27,20,23,26,16,31,9,26,5,20,4,7); line(10,16,14,20,23,11) end,
    copy=function() box(3,3,20,22); box(10,10,19,21) end,
    cut=function() circle(7,24,5); circle(25,24,5); line(10,20,26,3); line(22,20,6,3) end,
    paste=function() box(6,6,22,25); box(12,2,10,7); line(11,15,23,15); line(11,20,23,20); line(11,25,20,25) end,
    edit=function() g.polygon('line',4,22,22,4,29,11,11,29,3,31); line(18,8,25,15); line(4,22,11,29) end,
    search=function() circle(13,13,10); line(21,21,30,30); line(13,7,13,19); line(7,13,19,13) end,
    check=function() circle(16,16,13); line(8,16,14,22,25,10) end,
    warning=function() g.polygon('line',16,2,31,29,1,29); line(16,11,16,20); circle(16,25,1) end,
    power=function() line(16,2,16,16); line(9,5,4,11,4,22,10,28,22,28,28,22,28,11,23,5) end,
}
local palette={folder={1,.76,.35},file={.54,.77,1},heart={1,.48,.58},trash={1,.57,.42},warning={1,.78,.32},battery={.30,.90,.59},shield={.4,.8,1},update={.43,.77,1}}
function icons.draw(name,x,y,size,tint)
    g.push('all'); g.translate(x,y); g.scale(size/32,size/32); g.setLineWidth(1.8)
    g.setColor(unpack(tint or palette[name] or {.27,.90,.75}))
    local draw=drawings[name] or drawings.info; draw(); g.pop()
end
function icons.forEntry(e,page)
    if e.icon then return e.icon end
    if e.file then return e.clipboard=='copy' and 'copy' or e.clipboard=='move' and 'cut' or e.file.directory and 'folder' or 'file' end
    if e.port then return 'game' end
    if e.trash then return 'package' end
    if e.keyboard then return 'edit' end
    local text=(e.label or ''):lower()
    if e.storage then
        local op=e.storage.operation or e.storage.action
        return ({list='folder',info='info',copy='paste',move='paste',delete='trash',uninstall='trash',purge='trash',purge_all='trash',cleanup='search',trash='trash',restore='update'})[op] or 'folder'
    end
    if text:find('atual',1,true) then return 'update' end
    if text:find('copiar',1,true) then return 'copy' end
    if text:find('desativ',1,true) or text:find('ativar wi',1,true) then return 'power' end
    if text:find('restaur',1,true) or text:find('desfazer',1,true) then return 'update' end
    if text:find('verificar',1,true) or e.reanalyze then return 'search' end
    if text:find('corrigir',1,true) or text:find('reparo',1,true) then return 'wrench' end
    if e.status then return e.status=='ok' and 'check' or e.status=='error' and 'warning' or e.status=='warn' and 'warning' or 'info' end
    return ({ports='game',port='wrench',files='folder',folder_options='folder',file_options='file',trash='trash',cleanup='trash',network='wifi',battery='battery',system='system',av='display',pm='package',repair='wrench',updates='update',support='heart',compatibility='shield'})[e.page or page] or 'info'
end
return icons
