capture program drop econeval_bridge

program define econeval_bridge
    version 16.0
    syntax, CONFIG(string) REPORT(string) ///
        [MODEL(string) CLASS(string) BASELINEREPORT(string) FORMAT(string)]

    local cmd `"python -m econeval --config `"`config'"' --report `"`report'"'"'

    if ("`model'" != "") {
        local cmd `"`cmd' --model `"`model'"'"'
    }
    if ("`class'" != "") {
        local cmd `"`cmd' --class `"`class'"'"'
    }
    if ("`baselinereport'" != "") {
        local cmd `"`cmd' --baseline-report `"`baselinereport'"'"'
    }
    if ("`format'" != "") {
        local cmd `"`cmd' --format `"`format'"'"'
    }

    shell `cmd'
    if (_rc != 0) {
        exit _rc
    }
end

* Usage:
*   do bridges/stata/econeval_bridge.do
*   econeval_bridge, config("examples/csv_model/econeval.yml") report("econeval-report.json")
