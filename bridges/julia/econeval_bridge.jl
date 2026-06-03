#!/usr/bin/env julia

function parse_args(arguments::Vector{String})
    parsed = Dict{String, String}()
    index = 1
    while index <= length(arguments)
        flag = arguments[index]
        startswith(flag, "--") || error("Unexpected argument: $flag")
        key = replace(flag, r"^--" => "")
        if index < length(arguments) && !startswith(arguments[index + 1], "--")
            parsed[key] = arguments[index + 1]
            index += 2
        else
            parsed[key] = "true"
            index += 1
        end
    end
    return parsed
end

args = parse_args(copy(ARGS))

for required in ("config", "report")
    haskey(args, required) || error("Missing required argument: --$required")
end

cmd = `python -m econeval --config $(args["config"]) --report $(args["report"])`

if haskey(args, "model") && args["model"] != "true"
    cmd = `$cmd --model $(args["model"])`
end
if haskey(args, "class") && args["class"] != "true"
    cmd = `$cmd --class $(args["class"])`
end
if haskey(args, "baseline-report") && args["baseline-report"] != "true"
    cmd = `$cmd --baseline-report $(args["baseline-report"])`
end
if haskey(args, "format") && args["format"] != "true"
    cmd = `$cmd --format $(args["format"])`
end

success(run(cmd)) || exit(1)
