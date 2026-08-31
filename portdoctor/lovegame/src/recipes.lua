local recipes = {}

local known = {
    blazingbeaks = {
        id = "blazingbeaks",
        title = "Blazing Beaks",
        runtimes = {
            "dotnet-8.0.12.squashfs",
            "gmtoolkit.squashfs",
        },
        notes = "Receita baseada nos runtimes declarados pelo pacote oficial do PortMaster.",
    },
}

local function normalized(value)
    return tostring(value or ""):lower():gsub("[^%w]", "")
end

function recipes.forPort(name)
    return known[normalized(name)]
end

function recipes.addRuntimes(name, runtimes, seen)
    local recipe = recipes.forPort(name)
    if not recipe then
        return nil
    end
    for _, runtime in ipairs(recipe.runtimes or {}) do
        if not seen[runtime] then
            seen[runtime] = true
            runtimes[#runtimes + 1] = runtime
        end
    end
    return recipe
end

return recipes
