#ifndef FLKL_EQUAL_ON_H
#define FLKL_EQUAL_ON_H

#include <stdint.h>

// A finite pulse train with an exact integer-microsecond ON budget.
// Edge times are relative to stimulus onset, so loop overhead cannot accumulate.
class EqualOnPulseTrain {
 public:
  bool high;
  bool finished;
  uint32_t next_edge_us;

  EqualOnPulseTrain(uint8_t frequency, uint32_t duration_us, uint32_t total_on_us)
      : high(false), finished(true), next_edge_us(duration_us),
        frequency_(frequency), pulse_index_(0), onset_us_(0),
        period_error_(0), width_error_(0), clipped_tail_us_(0),
        tail_us_(0), distribute_off_(false) {
    if (frequency == 0 || total_on_us == 0 || total_on_us >= duration_us) {
      return;
    }
    period_us_ = 10000000UL / frequency;
    period_remainder_ = 10000000UL % frequency;
    uint16_t full_cycles = (uint64_t(duration_us) * frequency) / 10000000UL;
    uint32_t tail_start_us = (uint64_t(full_cycles) * 10000000UL) / frequency;
    uint32_t tail_us = duration_us - tail_start_us;
    tail_us_ = tail_us;
    pulse_count_ = full_cycles + (tail_us > 0);
    width_count_ = pulse_count_;

    // If the final partial period is too short for an equal-width pulse,
    // fill that tail and distribute the remaining ON budget over full periods.
    if (tail_us > 0 && uint64_t(tail_us) * pulse_count_ < total_on_us) {
      clipped_tail_us_ = tail_us;
      total_on_us -= tail_us;
      width_count_ = full_cycles;
    }
    width_us_ = total_on_us / width_count_;
    width_remainder_ = total_on_us % width_count_;
    // Near 100% ON, adjacent periods can differ by 1 us. Distribute their
    // OFF budget instead, so a rounded ON pulse never overlaps the next one.
    if (width_us_ >= period_us_) {
      uint32_t pool_us = clipped_tail_us_ > 0 ? tail_start_us : duration_us;
      uint32_t off_us = pool_us - total_on_us;
      width_us_ = off_us / width_count_;
      width_remainder_ = off_us % width_count_;
      distribute_off_ = true;
    }
    high = true;
    finished = false;
    next_edge_us = next_width();
  }

  void advance() {
    if (finished) {
      return;
    }
    if (high) {
      high = false;
      ++pulse_index_;
      if (pulse_index_ == pulse_count_) {
        finished = true;
        return;
      }
      onset_us_ += period_us_;
      period_error_ += period_remainder_;
      if (period_error_ >= frequency_) {
        ++onset_us_;
        period_error_ -= frequency_;
      }
      next_edge_us = onset_us_;
    } else {
      high = true;
      next_edge_us = onset_us_ + next_width();
    }
  }

 private:
  uint8_t frequency_;
  uint16_t pulse_index_, pulse_count_, width_count_;
  uint32_t onset_us_, period_us_, period_remainder_, period_error_;
  uint32_t width_us_, width_remainder_, width_error_, clipped_tail_us_;
  uint32_t tail_us_;
  bool distribute_off_;

  uint32_t next_width() {
    if (clipped_tail_us_ > 0 && pulse_index_ == pulse_count_ - 1) {
      return clipped_tail_us_;
    }
    uint32_t width = width_us_;
    width_error_ += width_remainder_;
    if (width_error_ >= width_count_) {
      ++width;
      width_error_ -= width_count_;
    }
    if (distribute_off_) {
      uint32_t window = period_us_ + (period_error_ + period_remainder_ >= frequency_);
      if (tail_us_ > 0 && pulse_index_ == pulse_count_ - 1) window = tail_us_;
      return window - width;
    }
    return width;
  }
};

#endif
