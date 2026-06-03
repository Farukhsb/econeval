#!/usr/bin/env Rscript

suppressWarnings(suppressMessages({
  args <- commandArgs(trailingOnly = TRUE)
}))

if (length(args) == 0) {
  stop(
    "Usage: econeval_bridge.R --config CONFIG [--model MODEL] [--class CLASS] ",
    "--report REPORT [--baseline-report BASELINE] [--format FORMAT]"
  )
}

parse_args <- function(arguments) {
  parsed <- list()
  index <- 1
  while (index <= length(arguments)) {
    flag <- arguments[[index]]
    if (!startsWith(flag, "--")) {
      stop(sprintf("Unexpected argument: %s", flag))
    }
    key <- sub("^--", "", flag)
    value <- TRUE
    if (index < length(arguments) && !startsWith(arguments[[index + 1]], "--")) {
      value <- arguments[[index + 1]]
      index <- index + 1
    }
    parsed[[key]] <- value
    index <- index + 1
  }
  parsed
}

args <- parse_args(args)

required <- c("config", "report")
missing <- required[!(required %in% names(args))]
if (length(missing) > 0) {
  stop(sprintf("Missing required arguments: %s", paste(missing, collapse = ", ")))
}

cmd <- file.path("python")
bridge_args <- c("-m", "econeval", "--config", args[["config"]], "--report", args[["report"]])

if (!is.null(args[["model"]]) && !identical(args[["model"]], TRUE)) {
  bridge_args <- c(bridge_args, "--model", args[["model"]])
}
if (!is.null(args[["class"]]) && !identical(args[["class"]], TRUE)) {
  bridge_args <- c(bridge_args, "--class", args[["class"]])
}
if (!is.null(args[["baseline-report"]]) && !identical(args[["baseline-report"]], TRUE)) {
  bridge_args <- c(bridge_args, "--baseline-report", args[["baseline-report"]])
}
if (!is.null(args[["format"]]) && !identical(args[["format"]], TRUE)) {
  bridge_args <- c(bridge_args, "--format", args[["format"]])
}

status <- system2(cmd, bridge_args)
if (status != 0) {
  quit(status = status)
}
