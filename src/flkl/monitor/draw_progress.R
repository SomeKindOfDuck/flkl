# 訓練経過の図を作成する
#
# data/monitor/の recent.csv と summary.csv (flkl.monitor.mergeで作成) を読み、
# 各個体の最新セッションについて以下の図を fig/monitor/{date}/ に保存する。
#
# - raster-{subject}.jpg       : 最新セッションのlick raster
# - progress-{subject}.jpg     : 直近10セッションのlick rateの推移
# - psychometric-{subject}.jpg : 最新セッションの周波数ごとのlick rate
# - progress-all.jpg           : 最新の実験日にデータがある個体のprogressをまとめたもの
#
# Usage: Rscript src/flkl/monitor/draw_progress.R [subject ...] [--force]

library(tidyverse)
library(data.table)
library(ggh4x)

STIM_DURATION <- 2
MIN_ITI <- 5
PRE_CS <- STIM_DURATION
POST_CS <- 2 * STIM_DURATION
N_PROGRESS_SESSIONS <- 10

# 訓練の達成基準(CS中のlick rate)
# - Visual-only, Synchronous: 使用周波数がCRITERION_FREQSと一致するセッションで、
#                             Highの平均がLowの平均のDISCRIMINATION_RATIO倍を超える
# - Audio-only              : Highの平均がLowの平均 + AUDIO_MARGIN以内
DISCRIMINATION_RATIO <- 1.5
AUDIO_MARGIN <- 0.5
CRITERION_FREQS <- c(4, 6, 8, 10, 12, 14)

STIMULUS_TYPE_LEVELS <- c("Visual-only", "Audio-only", "Synchronous", "Asynchronous")

DATA_DIR <- "data/monitor"
FIGURE_DIR <- "fig/monitor"

parse_args <- function() {
  args <- commandArgs(trailingOnly = TRUE)

  list(
    subject_ids = setdiff(args, "--force"),
    force = "--force" %in% args
  )
}

theme_monitor <- function() {
  theme_classic() +
    theme(
      aspect.ratio = 0.5,
      strip.text = element_text(size = 6, margin = margin(t = 1, r = 1, b = 1, l = 1)),
      strip.background = element_rect(linewidth = 0.2),
      panel.spacing = unit(0.4, "lines"),
      axis.text = element_text(size = 6),
      axis.title = element_text(size = 8)
    )
}

figure_path <- function(kind, subject, experiment_date) {
  dir <- file.path(FIGURE_DIR, experiment_date)
  dir.create(dir, recursive = TRUE, showWarnings = FALSE)
  file.path(dir, paste0(kind, "-", subject, ".jpg"))
}

should_draw <- function(path, force) {
  if (file.exists(path) && !force) {
    message("Skip existing figure: ", path)
    return(FALSE)
  }
  TRUE
}

# 刺激条件ごとの平均・SD・試行数から、それらをまとめた全試行の平均とSEを計算する
pool_mean_se <- function(n, m, s) {
  total <- sum(n)
  pooled_mean <- sum(n * m) / total

  s[is.na(s)] <- 0
  sum_sq <- sum((n - 1) * s^2 + n * (m - pooled_mean)^2)
  se <- if (total > 1) sqrt(sum_sq / (total - 1)) / sqrt(total) else NA_real_

  list(lick = pooled_mean, se = se)
}

##########
# Raster #
##########

# 視覚・聴覚刺激のonset間隔がMIN_ITI秒以上空いた箇所を試行の境界とみなし、
# 各試行の最初のonset時刻(=CS onset)を返す
detect_trial_onsets <- function(events) {
  onsets <- sort(events[event %in% c("LED-on", "Sound-on"), time])

  if (length(onsets) == 0) {
    return(numeric(0))
  }

  gap <- c(Inf, diff(onsets))
  onsets[gap >= MIN_ITI]
}

# 1セッション分のイベントを、CS onsetを0とした試行ごとの時刻に変換する
align_with_cs <- function(events) {
  cs_on <- detect_trial_onsets(events)

  # 記録の端で窓が欠ける試行は除外する
  t_range <- range(events$time)
  cs_on <- cs_on[cs_on - PRE_CS >= t_range[1] & cs_on + POST_CS <= t_range[2]]

  if (length(cs_on) == 0) {
    return(data.table())
  }

  trials <- data.table(trial = seq_along(cs_on), cs_on = cs_on)

  aligned <- trials[
    ,
    events[time >= cs_on - PRE_CS & time < cs_on + POST_CS, .(event, time = time - cs_on)],
    by = trial
  ]

  freqs <- aligned[
    ,
    .(
      visual_freq = sum(event == "LED-on") / STIM_DURATION,
      audio_freq = sum(event == "Sound-on") / STIM_DURATION
    ),
    by = trial
  ]

  freqs[aligned, on = "trial"]
}

draw_lick_raster <- function(events, subject, experiment_date, force) {
  output_path <- figure_path("raster", subject, experiment_date)

  if (!should_draw(output_path, force)) {
    return(invisible(NULL))
  }

  raster_data <- align_with_cs(events)[event == "Lick-on"]

  if (nrow(raster_data) == 0) {
    message("No licks to draw: ", subject, " ", experiment_date)
    return(invisible(NULL))
  }

  raster_data[
    ,
    trial := frank(trial, ties.method = "dense"),
    by = .(visual_freq, audio_freq)
  ]

  raster_plot <- ggplot(raster_data) +
    geom_point(aes(x = time, y = trial), size = 0.25) +
    geom_vline(xintercept = c(0, STIM_DURATION), linetype = "dashed") +
    facet_wrap(~ visual_freq + audio_freq, scales = "free_y") +
    labs(x = "Time from CS onset (s)", y = "Trial") +
    theme_monitor()

  ggsave(output_path, raster_plot, dpi = 300, width = 8, height = 4)
}

############
# Progress #
############

# 各個体の直近N_PROGRESS_SESSIONSセッションについて、lick rateの推移を描く
# (facetは呼び出し側で追加する)
build_progress_plot <- function(summary) {
  summary <- summary[summary[, .I[session > max(session) - N_PROGRESS_SESSIONS], by = subject]$V1]
  summary[, stimulus_type := factor(stimulus_type, levels = STIMULUS_TYPE_LEVELS)]

  pre_cs <- summary[
    time_window == "Pre-CS",
    pool_mean_se(n_trials, lick_mean, lick_sd),
    by = .(subject, session, stimulus_type)
  ]

  cs <- summary[time_window == "CS" & stimulus_type != "Asynchronous"]

  cs_by_freq <- cs[
    ,
    pool_mean_se(n_trials, lick_mean, lick_sd),
    by = .(subject, session, stimulus_type, freqcat, major_freq)
  ]

  cs_by_freqcat <- cs[
    ,
    pool_mean_se(n_trials, lick_mean, lick_sd),
    by = .(subject, session, stimulus_type, freqcat)
  ]

  low_line <- cs_by_freqcat[
    freqcat == "Low" & stimulus_type %in% c("Visual-only", "Synchronous")
  ]

  audio_low_band <- cs_by_freqcat[
    freqcat == "Low" & stimulus_type == "Audio-only"
  ]

  criteria <- dcast(
    cs_by_freqcat,
    subject + session + stimulus_type ~ freqcat,
    value.var = "lick"
  )
  for (col in setdiff(c("High", "Low"), names(criteria))) {
    criteria[, (col) := NA_real_]
  }

  used_freqs <- cs[
    ,
    .(full_freqs = setequal(unique(major_freq), CRITERION_FREQS)),
    by = .(subject, session, stimulus_type)
  ]
  criteria <- used_freqs[criteria, on = .(subject, session, stimulus_type)]

  criteria[
    ,
    passed := fcase(
      stimulus_type %in% c("Visual-only", "Synchronous"),
        full_freqs & High > DISCRIMINATION_RATIO * Low,
      stimulus_type == "Audio-only", High <= Low + AUDIO_MARGIN,
      default = FALSE
    )
  ]

  # 刺激の種類によらず、各個体の全パネルでx軸の範囲を直近のセッション範囲に揃える
  session_range <- summary[, .(session = range(session)), by = subject]

  ggplot() +
    geom_blank(data = session_range, aes(x = session)) +
    geom_point(data = pre_cs, aes(x = session, y = lick), size = 0.5) +
    geom_errorbar(
      data = pre_cs,
      aes(x = session, ymin = lick - se, ymax = lick + se),
      linewidth = 0.2, width = 0.5
    ) +
    geom_point(
      data = cs_by_freq,
      aes(x = session, y = lick, color = freqcat),
      size = 0.5, alpha = 0.25
    ) +
    geom_line(
      data = low_line,
      aes(x = session, y = lick * DISCRIMINATION_RATIO),
      linewidth = 0.5, alpha = 0.25
    ) +
    geom_ribbon(
      data = audio_low_band,
      aes(x = session, ymin = lick, ymax = lick + AUDIO_MARGIN),
      alpha = 0.15
    ) +
    geom_point(data = cs_by_freqcat, aes(x = session, y = lick, color = freqcat)) +
    # 基準を満たしたセッションにはパネル上端に*を付ける
    geom_text(
      data = criteria[passed == TRUE],
      aes(x = session, y = Inf, label = "*"),
      vjust = 1, size = 4
    ) +
    coord_cartesian(ylim = c(0, NA)) +
    scale_y_continuous(expand = expansion(mult = c(0.05, 0.15))) +
    # 両端のセッションのエラーバーが表示範囲外で消えないよう、左右に0.5ずつ余白を取る
    scale_x_continuous(
      expand = expansion(add = 0.5),
      breaks = function(limits) seq(ceiling(limits[1]), floor(limits[2]), by = 1)
    ) +
    labs(x = "Session", y = "Lick rate (/s)") +
    theme_monitor()
}

draw_progress <- function(summary, subject, experiment_date, force) {
  output_path <- figure_path("progress", subject, experiment_date)

  if (!should_draw(output_path, force)) {
    return(invisible(NULL))
  }

  progress_plot <- build_progress_plot(summary) +
    facet_wrap(~stimulus_type)

  ggsave(output_path, progress_plot, dpi = 300, width = 9, height = 3)
}

# 全個体のprogressを1枚にまとめる(縦: 個体, 横: 刺激の種類)
draw_progress_all <- function(summary, experiment_date, force) {
  output_path <- figure_path("progress", "all", experiment_date)

  if (!should_draw(output_path, force)) {
    return(invisible(NULL))
  }

  n_subjects <- uniqueN(summary$subject)
  n_stimulus_types <- uniqueN(summary$stimulus_type)

  # 個体ごとにsession番号の範囲が異なるので、x軸はパネルごとに独立させる
  progress_plot <- build_progress_plot(summary) +
    facet_grid2(subject ~ stimulus_type, scales = "free_x", independent = "x") +
    theme(aspect.ratio = NULL)

  ggsave(
    output_path,
    progress_plot,
    dpi = 300,
    width = 3 * n_stimulus_types + 1,
    height = 1.5 * n_subjects + 0.5,
    limitsize = FALSE
  )
}

################
# Psychometric #
################

draw_psychometric_function <- function(summary, subject, experiment_date, force) {
  output_path <- figure_path("psychometric", subject, experiment_date)

  if (!should_draw(output_path, force)) {
    return(invisible(NULL))
  }

  last_date <- summary[date == experiment_date & time_window == "CS"]

  if (uniqueN(last_date$major_freq) <= 1) {
    message("Skip psychometric function (single frequency): ", subject, " ", experiment_date)
    return(invisible(NULL))
  }

  psychometric_plot <- ggplot(
    last_date,
    aes(x = major_freq, y = lick_mean, color = stimulus_type, group = stimulus_type)
  ) +
    geom_errorbar(
      aes(ymin = lick_mean - lick_se, ymax = lick_mean + lick_se),
      linewidth = 0.5, width = 0.5
    ) +
    geom_point(size = 2) +
    coord_cartesian(ylim = c(0, NA)) +
    labs(x = "Frequency (Hz)", y = "Lick rate (/s)") +
    theme_monitor()

  ggsave(output_path, psychometric_plot, dpi = 300, width = 8, height = 4)
}

#############################
# Read data and draw figure #
#############################

args <- parse_args()

summary <- fread(file.path(DATA_DIR, "summary.csv"), colClasses = list(character = "date"))
recent <- fread(file.path(DATA_DIR, "recent.csv"), colClasses = list(character = "date"))

if (length(args$subject_ids) > 0) {
  missing_subjects <- setdiff(args$subject_ids, unique(summary$subject))

  if (length(missing_subjects) > 0) {
    warning(
      "The following subject(s) were not found in the data: ",
      paste(missing_subjects, collapse = ", ")
    )
  }

  summary <- summary[subject %chin% args$subject_ids]
  recent <- recent[subject %chin% args$subject_ids]

  if (nrow(summary) == 0) {
    stop("No data remained after filtering by subject_id.")
  }
}

summary[, freqcat := fifelse(major_freq > 9, "High", "Low")]

message(
  "Drawing figures for subject(s): ",
  paste(sort(unique(summary$subject)), collapse = ", ")
)

for (target_subject in sort(unique(summary$subject))) {
  subject_summary <- summary[subject == target_subject]
  experiment_date <- max(subject_summary$date)

  subject_events <- recent[subject == target_subject & date == experiment_date]

  if (nrow(subject_events) > 0) {
    draw_lick_raster(subject_events, target_subject, experiment_date, args$force)
  } else {
    message("No recent events for raster: ", target_subject, " ", experiment_date)
  }

  draw_progress(subject_summary, target_subject, experiment_date, args$force)
  draw_psychometric_function(subject_summary, target_subject, experiment_date, args$force)
}

# 全体図には、最新の実験日にデータが取られた個体(=訓練中の個体)だけを含める
latest_date <- max(summary$date)
active_subjects <- unique(summary[date == latest_date, subject])
draw_progress_all(summary[subject %chin% active_subjects], latest_date, args$force)
