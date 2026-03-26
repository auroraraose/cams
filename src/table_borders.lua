-- table_borders.lua
function Table(el)
    -- MUST match the name in the Word Dialog exactly
    el.classes:insert('List Table 3')

    local num_cols = #el.colspecs
    local widths = {}

    -- Logic for your 4-column Benchmarks table
    if num_cols == 4 then
        -- Benchmarks(25%), Value(20%), Compliance(15%), Justification(40%)
        widths = {0.20, 0.20, 0.20, 0.40}
    elseif num_cols == 6 then
        widths = {0.20, 0.16, 0.16, 0.16, 0.16, 0.16}
    else
        -- Default for the Financial Performance table (e.g., 6 columns)
        for i = 1, num_cols do
            widths[i] = 1.0 / num_cols
        end
    end

    -- Apply the widths to prevent crushing
    for i, w in ipairs(widths) do
        el.colspecs[i] = {pandoc.AlignDefault, w}
    end

    return el
end