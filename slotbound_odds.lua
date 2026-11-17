return function(loadUpgrade, weights, symbols)
    return function(...)
        local constants = require("src.data.constants")
        if symbols then
            local ordinary = constants.slot.symbolWeights
            local joker = symbols.Joker
            for key in pairs(ordinary) do
                ordinary[key] = symbols[key] / (1 - joker)
            end

            local cores = require("src.game.cores")
            local getJokerChance = cores.getJokerChance
            local prepareSpin = cores.prepareSpin
            local function withBaseChance(bonus)
                return math.min(0.05, joker + (bonus or 0))
            end
            function cores.getJokerChance(...)
                return withBaseChance(getJokerChance(...))
            end
            function cores.prepareSpin(...)
                local spin = prepareSpin(...)
                if spin then
                    spin.jokerChance = withBaseChance(spin.jokerChance)
                end
                return spin
            end
        end

        local upgrade = loadUpgrade(...)
        local grades = constants.unitGrades
        local original = grades.probabilities
        local adjusted = {}
        local applyOriginal = upgrade.applyUpgradeEffects

        local function refreshOdds()
            if weights then
                for grade, probability in pairs(weights) do
                    adjusted[grade] = probability
                end
                return
            end
            adjusted.advanced = 0.25 + original.advanced * 0.20
            adjusted.rare = 0.14 + original.rare * 0.50
            adjusted.legendary = 0.06 + original.legendary * 2.50
            adjusted.prism = 0.05 + original.prism * 2.50
            adjusted.normal = 1 - adjusted.advanced - adjusted.rare - adjusted.legendary - adjusted.prism
        end

        refreshOdds()
        assert(getmetatable(grades) == nil)
        grades.probabilities = nil
        setmetatable(grades, {
            __index = function(_, key)
                if key == "probabilities" then
                    return adjusted
                end
            end,
        })

        function upgrade.applyUpgradeEffects(...)
            rawset(grades, "probabilities", original)
            local ok, failure = pcall(applyOriginal, ...)
            rawset(grades, "probabilities", nil)
            if not ok then error(failure, 0) end
            refreshOdds()
        end

        function upgrade.isPrismOpen()
            return adjusted.prism > 0
        end

        -- Modified Endless runs may still record their results locally.
        local leaderboard = require("src.leaderboard")
        function leaderboard.submit()
            return false
        end
        return upgrade
    end
end
