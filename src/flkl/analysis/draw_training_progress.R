library(tidyverse)
library(data.table)
library(utexr)


parse_args <- function() {
  args <- commandArgs(trailingOnly = TRUE)

  list(
    subject_ids = args
  )
}

align_with_reward <- function(data) {
  if("IR-on" %in% unique(data$event)) {
    reward_on_times <- data$time[data$event == "Reward-on"]
    reward_off_times <- data$time[data$event == "Reward-off"]
    reward_duration <- median(reward_off_times - reward_on_times)
    aligned_data <- align_with(data, "event", "IR-on", "time", -4 - reward_duration, 2 - reward_duration) %>%
    filter(!(serial == min(serial) | serial == max(serial))) %>%
    mutate(seria = dense_rank(serial))
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

draw_lick_raster <- function(data, only_newest = TRUE) {
  if (only_newest) {
    data <- data[
      ,
      .SD[date == max(date)],
      by = subject
    ]
  }

  data[
    ,
    {
      subject <- .BY$subject
      experiment_date <- .BY$date

      raster_data <- copy(.SD %>% filter(event == "Lick-on"))

      raster_data[
        ,
        serial := data.table::frank(serial, ties.method = "dense"),
        by = .(visual_freq, audio_freq)
      ]

      raster_plot <- ggplot(raster_data) +
        geom_point(
          aes(x = time, y = serial),
          size = 0.25
        ) +
        geom_vline(xintercept = 0, linetype = "dashed") +
        geom_vline(xintercept = -2, linetype = "dashed") +
        facet_wrap(~ visual_freq + audio_freq, scales = "free_y") +
        labs(
          x = "Time from reward onset",
          y = "Trial"
        ) +
        theme_classic() +
        theme(
          aspect.ratio = 0.5,
          strip.text = element_text(size = 6, margin=margin(t=1, r=1, b=1, l=1)),
          strip.background = element_rect(linewidth = 0.2),
          panel.spacing = unit(0.4, "lines"),
          axis.text = element_text(size = 6),
          axis.title = element_text(size = 8)
        )

      ggsave(
        filename = file.path(
          FIGURE_PATH,
          paste0("raster", "-", subject, "-", experiment_date, ".jpg")
        ),
        plot = raster_plot,
        dpi = 300,
        width = 8,
        height = 4
      )

      invisible(NULL)
    },
    by = .(subject, date)
  ]
}

draw_progress <- function(data) {
  data[ ,
    {
      subject <- unique(.BY$subject)
      session <- max(.SD$session)
      experiment_date <- max(.SD$date)

      progress_plot <- ggplot() +
        stat_summary(
          data = .SD %>% filter(stimulus_type != "Asynchronous"),
          fun = "mean", geom = "point",
          aes(
            x = session,
            y = lick,
            color = freqcat,
            group = interaction(freqcat, major_freq)
          ),
          size = 0.5, alpha = 0.25
        ) +
        stat_summary(
          data = .SD %>% filter(freqcat == "Low", stimulus_type %in% c("Visual-only", "Synchronous")),
          fun = "mean", geom = "line",
          aes(
            x = session,
            y = lick * 1.5,
          ),
          size = 0.5, alpha = 0.25
        ) +
        stat_summary(
          data = .SD %>%
            filter(freqcat == "Low", stimulus_type == "Audio-only"),
          fun.data = function(y) {
            m <- mean(y, na.rm = TRUE)
            data.frame(
              y = m,
              ymin = m - 0.5,
              ymax = m + 0.5
            )
          },
          geom = "ribbon",
          aes(
            x = session,
            y = lick,
            group = 1
          ),
          alpha = 0.15
        ) +
        stat_summary(
          data = .SD %>% filter(stimulus_type != "Asynchronous"),
          fun = "mean", geom = "point",
          aes(x = session, y = lick, color = freqcat)
        ) +
        facet_wrap(~stimulus_type) +
        coord_cartesian(ylim = c(0, NA)) +
        scale_x_continuous(
          limits = c(session - 9, session),
          breaks = seq(session - 9, session, by = 1)
        ) +
        theme_classic() +
        theme(
          aspect.ratio = 0.5,
          strip.text = element_text(size = 6, margin=margin(t=1, r=1, b=1, l=1)),
          strip.background = element_rect(linewidth = 0.2),
          panel.spacing = unit(0.4, "lines"),
          axis.text = element_text(size = 6),
          axis.title = element_text(size = 8)
        )

        ggsave(
          filename = file.path(
            FIGURE_PATH,
            paste0("progress", "-", subject, "-", experiment_date, ".jpg")
          ),
          plot = progress_plot,
          dpi = 300,
          width = 9,
          height = 3
        )

        invisible()
    },
    by = subject]
}

draw_psychometric_function <- function(data) {
  data[ ,
    {
      subject <- unique(.BY$subject)
      session <- max(.SD$session)
      experiment_date <- max(.SD$date)

      last_date <- .SD[.SD$date == experiment_date]
      nstim <- unique(last_date$major_freq)

      if (length(nstim) <= 1) {
        return()
      }

      psychometric_function <- ggplot(last_date) +
        geom_point(
          aes(
            x = major_freq, y = lick,
            color = stimulus_type, group = stimulus_type
          ),
          size = 0.5, alpha = 0.25
        ) +
        stat_summary(
          fun.data = "mean_se", geom = "errorbar",
          aes(
            x = major_freq, y = lick,
            color = stimulus_type, group = stimulus_type
          ),
          linewidth = 0.5, width = 0.5
        ) +
        stat_summary(
          fun = "mean", geom = "point",
          aes(
            x = major_freq, y = lick,
            color = stimulus_type, group = stimulus_type
          ),
          size = 2
        ) +
        coord_cartesian(ylim = c(0, NA)) +
        theme_classic() +
        theme(
          aspect.ratio = 0.5,
          strip.text = element_text(size = 6, margin=margin(t=1, r=1, b=1, l=1)),
          strip.background = element_rect(linewidth = 0.2),
          panel.spacing = unit(0.4, "lines"),
          axis.text = element_text(size = 6),
          axis.title = element_text(size = 8)
        )

        ggsave(
          filename = file.path(
            FIGURE_PATH,
            paste0("psychometric", "-", subject, "-", experiment_date, ".jpg")
          ),
          plot = psychometric_function,
          dpi = 300,
          width = 8,
          height = 4
        )

        invisible()
    },
    by = subject]
}

#############################
# Read data and draw figure #
#############################

DATA_PATH <- "data/behavior/merged.csv"
FIGURE_PATH <- "fig/training"

if (!dir.exists(FIGURE_PATH)) {
  dir.create(FIGURE_PATH, recursive = TRUE)
}

args <- parse_args()

merged_data <- fread(DATA_PATH)

if (length(args$subject_ids) > 0) {
  available_subjects <- unique(merged_data$subject)
  missing_subjects <- setdiff(args$subject_ids, available_subjects)

  if (length(missing_subjects) > 0) {
    warning(
      "The following subject(s) were not found in the data: ",
      paste(missing_subjects, collapse = ", ")
    )
  }

  merged_data <- merged_data[
    subject %chin% args$subject_ids
  ]

  if (nrow(merged_data) == 0) {
    stop("No data remained after filtering by subject_id.")
  }
}

message(
  "Drawing figures for subject(s): ",
  paste(sort(unique(merged_data$subject)), collapse = ", ")
)

aligned_data <- merged_data[
  ,
  {
    align_with_reward(.SD) %>%
      mutate(
        time_window = case_when(
          time <= -2 ~ "Pre-CS",
          time <= 0  ~ "CS",
          TRUE       ~ "US"
        )
      )
  },
  by = .(subject, date)
]

lick_data <- aligned_data %>%
  group_by(subject, date, condition, phase, session, visual_freq, audio_freq, serial, time_window) %>%
  summarise(
    lick = sum(event == "Lick-on", na.rm = TRUE) / 2,
    .groups = "drop"
  ) %>%
  complete(
    nesting(subject, date, condition, phase, session, visual_freq, audio_freq, serial),
    time_window = c("Pre-CS", "CS", "US"),
    fill = list(lick = 0)
  ) %>%
  mutate(
    stimulus_type = case_when(
      visual_freq == 0 & audio_freq == 0 ~ "None",
      visual_freq == audio_freq ~ "Synchronous",
      visual_freq > 0 & audio_freq > 0 ~ "Asynchronous",
      visual_freq > 0 ~ "Visual-only",
      audio_freq > 0 ~ "Audio-only"
    )
  ) %>%
  filter(stimulus_type != "None") %>%
  mutate(
    major_freq = case_when(
      stimulus_type == "Synchronous" ~ visual_freq,
      stimulus_type == "Asynchronous" ~ audio_freq,
      stimulus_type == "Visual-only" ~ visual_freq,
      stimulus_type == "Audio-only" ~ audio_freq
    ),
    freqcat = fifelse(major_freq > 9, "High", "Low")
  ) %>%
  data.table()

draw_lick_raster(aligned_data, TRUE)
draw_progress(lick_data)
draw_psychometric_function(lick_data)
