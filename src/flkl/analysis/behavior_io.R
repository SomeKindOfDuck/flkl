# 行動データ(binary csv)の読み込み
library(data.table)

# data/behavior/にある1セッション分のbinary csvを読み込む
# 旧merged.csvからsubject/dateで絞り込んだものと同じ形式
# (subject, date, condition, phase, session, time, event)で返す
read_behavior_data <- function(
    subject,
    date,
    behavior_dir = "data/behavior",
    group_config = "group.toml"
) {
  subject <- as.character(subject)
  date <- as.character(date)

  # {subject}_{phase}_{session}_{date}-{time}_binary.csv
  pattern <- paste0("^", subject, "_[^_]+_[0-9]+_", date, "-.*_binary\\.csv$")
  paths <- list.files(behavior_dir, pattern = pattern, full.names = TRUE)

  if (length(paths) == 0) {
    stop("No behavior data found for subject=", subject, ", date=", date, " in ", behavior_dir)
  }

  if (length(paths) > 1) {
    stop(
      "Multiple behavior data found for subject=", subject, ", date=", date, ":\n  ",
      paste(basename(paths), collapse = "\n  ")
    )
  }

  identifier <- strsplit(basename(paths), "_", fixed = TRUE)[[1]]

  data <- fread(paths)
  data[, time := time - min(time, na.rm = TRUE)]

  data[
    ,
    `:=`(
      subject = subject,
      date = as.integer(date),
      condition = read_condition(subject, group_config),
      phase = identifier[2],
      session = as.integer(identifier[3])
    )
  ]

  setcolorder(data, c("subject", "date", "condition", "phase", "session", "time", "event"))

  data[]
}

# group.tomlからsubjectの群(Single/Multi)を返す
read_condition <- function(subject, group_config = "group.toml") {
  lines <- readLines(group_config, warn = FALSE)

  subjects_of <- function(group) {
    line <- grep(paste0("^\\s*", group, "\\s*="), lines, value = TRUE)
    if (length(line) == 0) {
      return(character(0))
    }
    gsub('"', "", regmatches(line, gregexpr('"[^"]*"', line))[[1]])
  }

  if (subject %in% subjects_of("single")) {
    return("Single")
  }

  if (subject %in% subjects_of("multi")) {
    return("Multi")
  }

  stop("Subject ", subject, " is not found in ", group_config)
}
