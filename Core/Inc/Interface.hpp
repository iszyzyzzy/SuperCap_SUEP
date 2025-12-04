#pragma once

#include "Config.hpp"
#include "PowerManager.hpp"
#include "dma.h"
#include "main.h"
#include "math.h"
#include "stdint.h"
#include "tim.h"

#define LED_NUM 3
#define BIT1_WIDTH 137
#define BIT0_WIDTH 69
#define DMA_TX_BUFFER_LENGTH 500

#define WS2812_TIM htim2
#define WS2812_TIM_CHANNEL TIM_CHANNEL_3

#define BUZZER_TIM htim1
#define BUZZER_TIM_CHANNEL TIM_CHANNEL_2

#define COLOR_YELLOW 0xFFFF00
#define COLOR_GREEN 0x00FF00
#define COLOR_BLUE 0x0000FF
#define COLOR_RED 0xFF0000
#define COLOR_WHITE 0xFFFFFF
#define COLOR_BLANK 0x000000
#define COLOR_ORANGE 0xFF4500
#define COLOR_CYAN 0x00FFFF

#define NOTE_WARNING_HIGH_FREQ 1600
#define NOTE_WARNING_LOW_FREQ 400
#define NOTE_WARNING_HIGH_DURATION 100
#define NOTE_WARNING_LOW_DURATION 250
#define WARNING_PERIOD 5000

struct BuzzerNote {
    uint16_t startTime;
    uint16_t freq;
    uint16_t duration;
};

const BuzzerNote buzzerWS_Unrecoverable[10] = {
    {0, NOTE_WARNING_HIGH_FREQ, NOTE_WARNING_HIGH_DURATION},
    {200, NOTE_WARNING_HIGH_FREQ, NOTE_WARNING_HIGH_DURATION},
    {400, NOTE_WARNING_HIGH_FREQ, NOTE_WARNING_HIGH_DURATION},
    {600, NOTE_WARNING_HIGH_FREQ, NOTE_WARNING_HIGH_DURATION},
    {800, NOTE_WARNING_HIGH_FREQ, NOTE_WARNING_HIGH_DURATION},
    {1300, NOTE_WARNING_LOW_FREQ, NOTE_WARNING_LOW_DURATION},
    {WARNING_PERIOD, 0U, 0U}};
const BuzzerNote buzzerWS_SCPA[10] = {
    {0, NOTE_WARNING_HIGH_FREQ, NOTE_WARNING_HIGH_DURATION},
    {200, NOTE_WARNING_HIGH_FREQ, NOTE_WARNING_HIGH_DURATION},
    {400, NOTE_WARNING_HIGH_FREQ, NOTE_WARNING_HIGH_DURATION},
    {600, NOTE_WARNING_HIGH_FREQ, NOTE_WARNING_HIGH_DURATION},
    {1100, NOTE_WARNING_LOW_FREQ, NOTE_WARNING_LOW_DURATION},
    {WARNING_PERIOD, 0U, 0U}};

const BuzzerNote buzzerWS_SCPB[10] = {
    {0, NOTE_WARNING_HIGH_FREQ, NOTE_WARNING_HIGH_DURATION},
    {200, NOTE_WARNING_HIGH_FREQ, NOTE_WARNING_HIGH_DURATION},
    {400, NOTE_WARNING_HIGH_FREQ, NOTE_WARNING_HIGH_DURATION},
    {600, NOTE_WARNING_HIGH_FREQ, NOTE_WARNING_HIGH_DURATION},
    {1100, NOTE_WARNING_LOW_FREQ, NOTE_WARNING_LOW_DURATION},
    {1600, NOTE_WARNING_LOW_FREQ, NOTE_WARNING_LOW_DURATION},
    {WARNING_PERIOD, 0U, 0U}};

const BuzzerNote buzzerWS_OCPA[10] = {
    {0, NOTE_WARNING_HIGH_FREQ, NOTE_WARNING_HIGH_DURATION},
    {200, NOTE_WARNING_HIGH_FREQ, NOTE_WARNING_HIGH_DURATION},
    {400, NOTE_WARNING_HIGH_FREQ, NOTE_WARNING_HIGH_DURATION},
    {900, NOTE_WARNING_LOW_FREQ, NOTE_WARNING_HIGH_DURATION},
    {WARNING_PERIOD, 0U, 0U}};

const BuzzerNote buzzerWS_OCPB[10] = {
    {0, NOTE_WARNING_HIGH_FREQ, NOTE_WARNING_HIGH_DURATION},
    {200, NOTE_WARNING_HIGH_FREQ, NOTE_WARNING_HIGH_DURATION},
    {400, NOTE_WARNING_HIGH_FREQ, NOTE_WARNING_HIGH_DURATION},
    {900, NOTE_WARNING_LOW_FREQ, NOTE_WARNING_HIGH_DURATION},
    {1100, NOTE_WARNING_LOW_FREQ, NOTE_WARNING_HIGH_DURATION},
    {WARNING_PERIOD, 0U, 0U}};

const BuzzerNote buzzerWS_OCPR[10] = {
    {0, NOTE_WARNING_HIGH_FREQ, NOTE_WARNING_HIGH_DURATION},
    {200, NOTE_WARNING_HIGH_FREQ, NOTE_WARNING_HIGH_DURATION},
    {400, NOTE_WARNING_HIGH_FREQ, NOTE_WARNING_HIGH_DURATION},
    {900, NOTE_WARNING_LOW_FREQ, NOTE_WARNING_HIGH_DURATION},
    {1100, NOTE_WARNING_LOW_FREQ, NOTE_WARNING_HIGH_DURATION},
    {1300, NOTE_WARNING_LOW_FREQ, NOTE_WARNING_HIGH_DURATION},
    {WARNING_PERIOD, 0U, 0U}};

const BuzzerNote buzzerWS_OVPA[10] = {
    {0, NOTE_WARNING_HIGH_FREQ, NOTE_WARNING_HIGH_DURATION},
    {200, NOTE_WARNING_HIGH_FREQ, NOTE_WARNING_HIGH_DURATION},
    {400, NOTE_WARNING_HIGH_FREQ, NOTE_WARNING_HIGH_DURATION},
    {900, NOTE_WARNING_LOW_FREQ, NOTE_WARNING_LOW_DURATION},
    {WARNING_PERIOD, 0U, 0U}};

const BuzzerNote buzzerWS_OVPB[10] = {
    {0, NOTE_WARNING_HIGH_FREQ, NOTE_WARNING_HIGH_DURATION},
    {200, NOTE_WARNING_HIGH_FREQ, NOTE_WARNING_HIGH_DURATION},
    {400, NOTE_WARNING_HIGH_FREQ, NOTE_WARNING_HIGH_DURATION},
    {900, NOTE_WARNING_LOW_FREQ, NOTE_WARNING_LOW_DURATION},
    {1400, NOTE_WARNING_LOW_FREQ, NOTE_WARNING_LOW_DURATION},
    {WARNING_PERIOD, 0U, 0U}};

const BuzzerNote buzzerWS_LowBattery[10] = {{0, 1600, 40},
                                            {40, 800, 40},
                                            {80, 1600, 40},
                                            {120, 800, 40},
                                            {WARNING_PERIOD, 0U, 0U}};

struct InterfaceStatus {
    uint8_t isWarning = 0U;
    uint8_t isWarningLast = 0U;
    uint16_t buzzerSequenceCnt = 0U;

    BuzzerNote buzzerNote[10];
    uint8_t buzzerNoteLength = 0U;
    uint8_t noteIndex = 0U;
};

extern InterfaceStatus interfaceStatus;

namespace Buzzer {
void init();
void play(uint16_t freq, uint16_t duration);
void update();
} // namespace Buzzer

/*
LED指示如下
LED0: 错误指示灯
    正常工作：绿
    警告状态：黄
    可恢复错误：闪烁红
    不可恢复错误：常亮红
LED1: 主dcdc回路状态 
    Buck充电: 黄绿 #99FF00
    Buck-Boost 充电: 草绿 #66FF00
    Boost 充电: 正绿 #00FF00
    Buck放电: 橙色 #FF6600
    Buck-Boost 放电: 橙红 #FF3300
    Boost 放电: 正红 #FF0000
    空载: 白色微亮 #333333
    异常: 正蓝 #0000FF
    关机: 关闭 #000000
LED2: 通信状态
    断开连接: 红色 #FF0000 / （自主模式） 蓝色 #0000FF
    连接正常: 绿 #00FF00
    CAN通信活动: 白色闪烁 #FFFFFF
 */

constexpr uint8_t SYSTEM_LED = 0;
constexpr uint8_t POWER_LED = 1;
constexpr uint8_t COMM_LED = 2;

// 这led神奇的巨亮，所以给了个很低的上限，不过这样有时会导致分不清状态，总之先这样吧
constexpr int OVERALL_BRIGHTNESS = 32; // 0-255
constexpr uint8_t scale_comp(uint8_t c) {
    return static_cast<uint8_t>(
        (static_cast<uint32_t>(c) * OVERALL_BRIGHTNESS + 127U) / 255U);
}

constexpr uint32_t scale_color(uint32_t color) {
    return (static_cast<uint32_t>(scale_comp((color >> 16) & 0xFF)) << 16) |
           (static_cast<uint32_t>(scale_comp((color >> 8) & 0xFF)) << 8) |
           static_cast<uint32_t>(scale_comp(color & 0xFF));
}

constexpr uint32_t COLOR_STATE_NORMAL = scale_color(COLOR_GREEN);
constexpr uint32_t COLOR_STATE_WARNING = scale_color(COLOR_YELLOW);
constexpr uint32_t COLOR_STATE_ERROR = scale_color(COLOR_RED);

constexpr uint32_t COLOR_POWER_Buck_Charging = scale_color(0x99FF00);
constexpr uint32_t COLOR_POWER_BuckBoost_Charging = scale_color(0x66FF00);
constexpr uint32_t COLOR_POWER_Boost_Charging = scale_color(0x00FF00);
constexpr uint32_t COLOR_POWER_Buck_Discharging = scale_color(0xFF6600);
constexpr uint32_t COLOR_POWER_BuckBoost_Discharging = scale_color(0xFF3300);
constexpr uint32_t COLOR_POWER_Boost_Discharging = scale_color(0xFF0000);
constexpr uint32_t COLOR_POWER_Idle = scale_color(0x333333);
constexpr uint32_t COLOR_POWER_Abnormal = scale_color(COLOR_BLUE);

constexpr uint32_t COLOR_COMM_DISCONNECTED = scale_color(COLOR_RED);
constexpr uint32_t COLOR_COMM_AUTONOMOUS = scale_color(COLOR_BLUE);
constexpr uint32_t COLOR_COMM_CONNECTED = scale_color(COLOR_GREEN);
constexpr uint32_t COLOR_COMM_ACTIVITY = scale_color(COLOR_WHITE);

typedef struct {
    uint8_t blue;
    uint8_t red;
    uint8_t green;
} RGB;

namespace WS2812 {

void init();

void blink(uint8_t index, uint8_t r, uint8_t g, uint8_t b);

void blink(uint8_t index, uint32_t colorCode);

void update();

void blank(int index);

void blankAll();

} // namespace WS2812

namespace Interface {

void alert();
void flashLED(uint8_t index, uint32_t color, uint32_t duration);
void updateButtonState();
void updateBuzzerSequence();
void updateLEDs();

} // namespace Interface