// Run the actual sketch against a 4-us clock and capture GPIO transitions.
#include <cstdint>
#include <cstdlib>
#include <iostream>
#include <stdexcept>
#include <string>
#include <vector>

struct Edge { int pin; uint64_t time; bool high; };
std::vector<Edge> edges;
uint64_t clock_us = 0;

class Port {
 public:
  explicit Port(int offset) : offset_(offset), value_(0) {}
  Port& operator|=(int mask) { set(value_ | mask); return *this; }
  Port& operator&=(int mask) { set(value_ & mask); return *this; }
 private:
  int offset_;
  uint8_t value_;
  void set(uint8_t value) {
    for (int bit = 0; bit < 8; ++bit) {
      if ((value ^ value_) & (1 << bit)) {
        edges.push_back({offset_ + bit, clock_us, bool(value & (1 << bit))});
      }
    }
    value_ = value;
  }
};

Port PORTD(0), PORTB(8);
int PIND = 0, PINB = 0;
#define _BV(bit) (1 << (bit))
#define INPUT 0
#define INPUT_PULLUP 2
#define OUTPUT 1
void pinMode(int, int) {}
int digitalRead(int) { return 0; }
int analogRead(int) { return 0; }
void analogWrite(int, int) {}
uint32_t micros() { uint32_t now = clock_us; clock_us += 4; return now; }

struct EndOfInput {};
struct SerialStub {
  std::vector<int> data;
  size_t position = 0;
  void begin(int) {}
  void println(int) {}
  void write(int) {}
  int read() {
    if (position == data.size()) throw EndOfInput();
    return data[position++];
  }
} Serial;

#include "../ino/ino.ino"

void check_plans() {
  size_t checked = 0;
  for (uint16_t frequency = 1; frequency <= 255; ++frequency) {
    for (uint32_t duration_us : {1000U, 49000U, 1733000U, 2000000U, 2150000U, 65535000U}) {
      for (uint32_t budget : {1U, uint32_t(duration_us * 0.01 + 0.5),
             uint32_t(duration_us * 0.28 + 0.5), uint32_t(duration_us * 0.5 + 0.5),
             uint32_t(duration_us * 0.95 + 0.5), uint32_t(duration_us * 0.9999 + 0.5),
             duration_us - 1}) {
        if (budget == 0 || budget >= duration_us) continue;
        EqualOnPulseTrain train(frequency, duration_us, budget);
        uint64_t on_time = 0;
        uint32_t previous = 0;
        size_t transitions = 0;
        while (!train.finished) {
          if (train.next_edge_us < previous || train.next_edge_us > duration_us) {
            throw std::runtime_error("Non-monotonic or out-of-window pulse edge");
          }
          if (train.high) on_time += train.next_edge_us - previous;
          previous = train.next_edge_us;
          train.advance();
          if (++transitions > 4000) throw std::runtime_error("Pulse train did not finish");
        }
        if (on_time != budget || train.high) throw std::runtime_error("Incorrect total ON time");
        ++checked;
      }
    }
  }
  std::cout << checked << " exact ON-budget plans passed\n";
}

int main(int argc, char** argv) {
  if (argc < 2) return 2;
  if (std::string(argv[1]) == "--check-plans") {
    check_plans();
    return 0;
  }
  if (argc > 2) clock_us = std::strtoull(argv[2], nullptr, 10);
  std::string hex(argv[1]);
  for (size_t i = 0; i < hex.size(); i += 2) {
    Serial.data.push_back(std::stoi(hex.substr(i, 2), nullptr, 16));
  }
  try {
    setup();
    loop();
  } catch (const EndOfInput&) {}
  for (const Edge& edge : edges) {
    std::cout << edge.pin << ' ' << edge.time << ' ' << edge.high << '\n';
  }
}
