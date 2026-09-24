library(tidyverse)
library(glmnet)
library(arrow)
library(tools)
library(viridis)
library(utexr)
library(data.table)
source("src/flkl/analysis/behavior_io.R")

parse_args <- function() {
  args <- commandArgs(trailingOnly = TRUE)

  parsed <- list(
    data_dir = NULL,
    iter = 100
  )

  usage <- paste0(
    "Usage: Rscript decode_neuro.R ",
    "--data-dir <path> [--iter <integer>]\n",
    "Example: Rscript decode_neuro.R ",
    "--data-dir data/2p/G13M3-20260604"
  )

  if (length(args) == 0) {
    stop("--data-dir is required.\n", usage, call. = FALSE)
  }

  i <- 1
  while (i <= length(args)) {
    arg <- args[i]

    if (arg == "--data-dir") {
      if (i + 1 > length(args)) {
        stop("--data-dir requires a value.", call. = FALSE)
      }

      if (startsWith(args[i + 1], "--")) {
        stop("--data-dir requires a value.", call. = FALSE)
      }

      parsed$data_dir <- args[i + 1]
      i <- i + 2

    } else if (startsWith(arg, "--data-dir=")) {
      parsed$data_dir <- sub("^--data-dir=", "", arg)
      i <- i + 1

    } else if (arg == "--iter") {
      if (i + 1 > length(args)) {
        stop("--iter requires a value.", call. = FALSE)
      }

      if (startsWith(args[i + 1], "--")) {
        stop("--iter requires a value.", call. = FALSE)
      }

      parsed$iter <- as.integer(args[i + 1])
      i <- i + 2

    } else if (startsWith(arg, "--iter=")) {
      parsed$iter <- as.integer(sub("^--iter=", "", arg))
      i <- i + 1

    } else {
      stop("Unknown argument: ", arg, "\n", usage, call. = FALSE)
    }
  }

  if (is.null(parsed$data_dir) || parsed$data_dir == "") {
    stop("--data-dir is required.\n", usage, call. = FALSE)
  }

  if (!dir.exists(parsed$data_dir)) {
    stop("data-dir does not exist: ", parsed$data_dir, call. = FALSE)
  }

  if (is.na(parsed$iter) || parsed$iter < 1) {
    stop("--iter must be a positive integer.", call. = FALSE)
  }

  parsed
}

align_with_reward <- function(data) {
  if("IR-on" %in% unique(data$event)) {
    reward_on_times <- data$time[data$event == "Reward-on"]
    reward_off_times <- data$time[data$event == "Reward-off"]
    reward_duration <- median(reward_off_times - reward_on_times)
    aligned_data <- align_with(data, "event", "IR-on", "time", -4 - reward_duration, -reward_duration) %>%
    filter(!(serial == min(serial) | serial == max(serial))) %>%
    mutate(serial = dense_rank(serial), time = time + reward_duration)
  } else {
    aligned_data <- align_with(data, "event", "Reward-on", "time", -4, 2)
  }

  aligned_data <- aligned_data[, {
    .SD %>%
      mutate(
        visual_freq = sum(event == "LED-on", na.rm = TRUE) / 2,
        audio_freq  = sum(event == "Sound-on", na.rm = TRUE) / 2,
      )
    },
    by = serial]

  return(aligned_data)
}

run_decoder <- function(d, target_col) {
  d <- d %>%
    group_by(visual_freq, audio_freq) %>%
    mutate(
      split = fifelse(
        row_number() %in% sample(row_number(), size = floor(0.8 * n())),
        "train",
        "test"
      )
    ) %>%
    ungroup()

  x <- d %>%
    select(matches("^cell_")) %>%
    as.matrix()

  y <- d[[target_col]]

  train_idx <- d$split == "train"
  test_idx  <- d$split == "test"

  if (sum(train_idx) < 2 || sum(test_idx) < 1) {
    return(tibble(target = target_col, true = numeric(), pred = numeric()))
  }

  if (length(unique(y[train_idx][!is.na(y[train_idx])])) < 2) {
    return(tibble(target = target_col, true = numeric(), pred = numeric()))
  }

  fit <- cv.glmnet(
    x[train_idx, ],
    y[train_idx],
    alpha = 0
  )

  pred <- predict(
    fit,
    newx = x[test_idx, ],
    s = "lambda.min"
  )[, 1]

  tibble(
    target = target_col,
    true = y[test_idx],
    pred = pred
  )
}


args <- parse_args()

data_dir <- args$data_dir
iter <- args$iter

FPS <- 7.3
STIM_DURATION <- 2.
TIME_BIN <- 0.5

(function() {
  subject_date <- basename(normalizePath(data_dir, mustWork = FALSE)) %>%
    str_split("-", simplify = TRUE) %>%
    as.vector()

  target_subject <<- subject_date[1]
  target_date <<- subject_date[2]
})()

dff_path <- list.files(data_dir, pattern = "dff", full.names = T)
FIGURE_PATH <- file.path("fig/neuro/decode_stimulus_from_dff")


decodable_data <- (function() {
  target_data <- read_behavior_data(target_subject, target_date)
  target_data[, frame := cumsum(event == "FrameSignal-on")]

  aligned_data <- align_with_reward(target_data)
  aligned_data <- aligned_data[aligned_data$event == "FrameSignal-on", ]
  neuro_activity <- read_parquet(dff_path) %>%
    select(-frame_idx) %>%
    as.matrix

  ncell <- ncol(neuro_activity)
  nbin <- STIM_DURATION / TIME_BIN

  feature_name <- paste0(
    "cell_", rep(seq_len(ncell), each = nbin),
    "_time_", rep(seq_len(nbin), times = ncell)
  )

  aligned_data[ ,
    {
      before_stimulus_frames <- .SD$frame[.SD$time <= -STIM_DURATION]

      after_stimulus_frames <- .SD$frame[.SD$time >  -STIM_DURATION]
      after_stimulus_times <- .SD$time[.SD$time >  -STIM_DURATION]

      time_bin <- bining(after_stimulus_times, 0.5)
      bins <- unique(time_bin)
      grp <- match(time_bin, bins)

      baseline_activity <- neuro_activity[before_stimulus_frames, , drop = FALSE]
      stim_activity <- neuro_activity[after_stimulus_frames, , drop = FALSE]

      baseline <- colMeans(baseline_activity)
      scaled_stim_activity <- sweep(stim_activity, 2, baseline, "-")
      mean_activity <- rowsum(scaled_stim_activity, grp, reorder = FALSE) / tabulate(grp)
      setNames(data.table(t(as.vector(mean_activity))), feature_name)
    },
    by = .(serial, visual_freq, audio_freq)
  ] %>%
    mutate(
    stimulus_type = fcase(
      visual_freq > 0 & audio_freq > 0 & visual_freq == audio_freq, "Synchronous",
      visual_freq > 0 & audio_freq > 0, "Asynchronous",
      visual_freq > 0, "Visual-only",
      audio_freq > 0, "Audio-only",
      default = "None"
    )
  )})()


decode_result <- seq_len(iter) %>%
  lapply(function(i) {
    message("Running decoder iteration: ", i, " / ", iter)

    decodable_data %>%
      group_by(stimulus_type) %>%
      group_modify(~ bind_rows(
        run_decoder(.x, "visual_freq"),
        run_decoder(.x, "audio_freq")
      )) %>%
      ungroup() %>%
      group_by(stimulus_type, target, true) %>%
      summarise(pred = mean(pred),
                rmse = mean(sqrt((true - pred)^2)),
                .groups = "drop") %>%
      ungroup
  }) %>%
  bind_rows()


decode_plot <- ggplot(decode_result %>% filter(!(stimulus_type == "Synchronous" & target == "audio_freq")),
  aes(x = true, y = pred)) +
  geom_abline(intercept = 0, slope = 1, linetype = "dashed") +
  geom_point(alpha = 0.25, size = 0.5) +
  stat_summary(fun = "mean", geom = "point", size = 2) +
  stat_summary(fun.data = "mean_se", geom = "errorbar", linewidth = 1) +
  geom_smooth(method = "lm", se = TRUE) +
  facet_wrap(~stimulus_type) +
  labs(
    x = "True frequency",
    y = "Decoded frequency"
  ) +
  theme_classic() +
  theme(
    aspect.ratio = 1.,
    legend.title = element_text(size = 12),
    legend.text = element_text(size = 10),
    axis.title.x = element_text(size = 14),
    axis.title.y = element_text(size = 14),
    plot.title = element_text(size = 16, hjust = 0.5),
    legend.background = element_rect(fill = scales::alpha("white", 0.5), color = "black")
  )

# FIGURE_PATHのディレクトリがなかったら作成する
if (!dir.exists(FIGURE_PATH)) {
  dir.create(FIGURE_PATH, recursive = TRUE)
}

output_name <- basename(normalizePath(data_dir, mustWork = FALSE))

ggsave(
  file.path(FIGURE_PATH, paste0(output_name, ".jpg")),
  decode_plot,
  dpi = 300
)

write_csv(decode_result, file.path(data_dir, "decode.csv"))
