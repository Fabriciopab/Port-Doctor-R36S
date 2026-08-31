-- Small strict JSON codec for helper messages. Never evaluates code from files.
local json = {}
function json.encode(value)
    local kind=type(value)
    if kind=='nil' then return 'null'
    elseif kind=='boolean' or kind=='number' then return tostring(value)
    elseif kind=='string' then
        return '"'..value:gsub('[%z\1-\31\\"]',function(c)
            local map={['"']='\\"',['\\']='\\\\'}
            return map[c] or string.format('\\u%04x',c:byte())
        end)..'"'
    elseif kind=='table' then
        local parts={}
        for key,item in pairs(value) do parts[#parts+1]=json.encode(tostring(key))..':'..json.encode(item) end
        return '{'..table.concat(parts,',')..'}'
    end
    error('Tipo JSON não suportado: '..kind)
end
local function utf8char(n)
    if n<128 then return string.char(n)
    elseif n<2048 then return string.char(192+math.floor(n/64),128+n%64)
    elseif n<65536 then return string.char(224+math.floor(n/4096),128+math.floor(n/64)%64,128+n%64)
    else return string.char(240+math.floor(n/262144),128+math.floor(n/4096)%64,128+math.floor(n/64)%64,128+n%64) end
end
function json.decode(text)
    local i,depth=1,0
    local function space() local _,e=text:find('^[ \r\n\t]*',i); i=(e or i-1)+1 end
    local parse
    local function stringValue()
        i=i+1; local result={}
        while i<=#text do
            local c=text:sub(i,i); i=i+1
            if c=='"' then return table.concat(result) end
            if c=='\\' then
                local e=text:sub(i,i); i=i+1
                local map={['"']='"',['\\']='\\',['/']='/',b='\b',f='\f',n='\n',r='\r',t='\t'}
                if e=='u' then
                    local h=text:sub(i,i+3); assert(h:match('^%x%x%x%x$'),'Escape JSON inválido')
                    local n=tonumber(h,16); i=i+4
                    if n>=0xD800 and n<=0xDBFF then
                        assert(text:sub(i,i+1)=='\\u','Surrogate inválido')
                        local tail=tonumber(text:sub(i+2,i+5),16); assert(tail and tail>=0xDC00 and tail<=0xDFFF,'Surrogate inválido')
                        n=0x10000+(n-0xD800)*1024+tail-0xDC00; i=i+6
                    else assert(n<0xDC00 or n>0xDFFF,'Surrogate inválido') end
                    result[#result+1]=utf8char(n)
                else assert(map[e],'Escape JSON inválido'); result[#result+1]=map[e] end
            else assert(c:byte()>=32,'Controle JSON inválido'); result[#result+1]=c end
        end
        error('Texto JSON incompleto')
    end
    parse=function()
        space(); depth=depth+1; assert(depth<=64,'JSON profundo demais')
        local c=text:sub(i,i); local result
        if c=='"' then result=stringValue()
        elseif c=='{' or c=='[' then
            local object=c=='{'; local close=object and '}' or ']'; result={}; i=i+1; space()
            if text:sub(i,i)~=close then
                while true do
                    space(); local key=#result+1
                    if object then assert(text:sub(i,i)=='"','Chave inválida'); key=stringValue(); space(); assert(text:sub(i,i)==':','Falta :'); i=i+1 end
                    result[key]=parse(); space()
                    if text:sub(i,i)~=',' then break end
                    i=i+1
                end
            end
            assert(text:sub(i,i)==close,'JSON incompleto'); i=i+1
        elseif text:sub(i,i+3)=='true' then result=true; i=i+4
        elseif text:sub(i,i+4)=='false' then result=false; i=i+5
        elseif text:sub(i,i+3)=='null' then result=nil; i=i+4
        else
            local number=text:match('^-?%d+%.?%d*[eE]?[+-]?%d*',i)
            result=tonumber(number); assert(result,'Número JSON inválido'); i=i+#number
        end
        depth=depth-1; return result
    end
    local result=parse(); space(); assert(i>#text,'Dados após JSON'); return result
end
return json
