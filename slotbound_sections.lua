return function(upgrade, history, confirmedUnit)
    local requirement = upgrade.sectionRequirement
    local _, nodes = debug.getupvalue(requirement, 2)
    assert(type(nodes) == "table" and nodes.maxunit, "Unexpected Slotbound upgrade data")

    function upgrade.sectionRequirement(id)
        local section = upgrade.SECTION_REWARDS[id]
        if not section or GameEditionMode ~= "full" then
            return requirement(id)
        end
        if id == "growthbranch" and confirmedUnit then
            local _, required, label = requirement(id)
            return required, required, label
        end

        -- Count previously purchased nodes only for this check.
        local restored = {}
        for _, key in ipairs(section.nodes) do
            local node = nodes[key]
            if node and history[key] and node.maxed ~= true then
                restored[#restored + 1] = {node = node, maxed = node.maxed}
                node.maxed = true
            end
        end
        local ok, current, required, label = pcall(requirement, id)
        for _, entry in ipairs(restored) do
            entry.node.maxed = entry.maxed
        end
        if not ok then error(current, 0) end
        return current, required, label
    end
    return upgrade
end
