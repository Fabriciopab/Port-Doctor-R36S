local util = {}

function util.trim(value)
    if value == nil then
        return ""
    end
    return tostring(value):gsub("^%s+", ""):gsub("%s+$", "")
end

function util.lines(value)
    local result = {}
    value = tostring(value or ""):gsub("\r\n", "\n")
    for line in (value .. "\n"):gmatch("(.-)\n") do
        line = util.trim(line)
        if line ~= "" then
            result[#result + 1] = line
        end
    end
    return result
end

function util.shellQuote(value)
    value = tostring(value or "")
    return "'" .. value:gsub("'", "'\"'\"'") .. "'"
end

function util.run(command)
    local handle = io.popen(command .. " 2>&1")
    if not handle then
        return "", false
    end

    local output = handle:read("*a") or ""
    local ok = handle:close()
    return util.trim(output), ok == true
end

function util.testFile(path, executable)
    local flag = executable and "-x" or "-e"
    local _, ok = util.run("test " .. flag .. " " .. util.shellQuote(path))
    return ok
end

function util.readFile(path, maxBytes)
    local file = io.open(path, "rb")
    if not file then
        return nil
    end

    local data
    if maxBytes then
        data = file:read(maxBytes)
    else
        data = file:read("*a")
    end
    file:close()
    return data
end

function util.readTail(path, maxBytes)
    local file = io.open(path, "rb")
    if not file then
        return nil
    end
    local size = file:seek("end") or 0
    local start = math.max(0, size - (maxBytes or size))
    file:seek("set", start)
    local data = file:read("*a")
    file:close()
    return data
end

function util.writeFile(path, data)
    local file = io.open(path, "wb")
    if not file then
        return false
    end
    file:write(data)
    file:close()
    return true
end

function util.clamp(value, minimum, maximum)
    if value < minimum then
        return minimum
    end
    if value > maximum then
        return maximum
    end
    return value
end

function util.basename(path)
    return tostring(path or ""):gsub("\\", "/"):match("([^/]+)$") or ""
end

function util.elfArchitecture(path)
    local file=io.open(path,'rb')
    if not file then return nil end
    local data=file:read(20) or ''
    local size=file:seek('end') or 0
    file:close()
    if #data<20 or size<4096 or data:sub(1,4)~='\127ELF' then return nil end
    if data:byte(6)~=1 and data:byte(6)~=2 then return nil end
    local machine=data:byte(19)+data:byte(20)*256
    if data:byte(6)==2 then machine=data:byte(20)+data:byte(19)*256 end
    if machine==183 and data:byte(5)==2 then return 'aarch64'
    elseif machine==40 and data:byte(5)==1 then return 'armhf'
    elseif machine==62 and data:byte(5)==2 then return 'x86_64' end
end

function util.firstLine(value)
    return util.trim(tostring(value or ""):match("([^\r\n]*)") or "")
end

function util.lastLine(value)
    local last = ""
    for line in tostring(value or ""):gmatch("[^\r\n]+") do
        if util.trim(line) ~= "" then
            last = util.trim(line)
        end
    end
    return last
end

return util
