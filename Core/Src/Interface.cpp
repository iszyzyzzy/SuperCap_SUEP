#include "Interface.hpp"
#include "PowerManager.hpp"
#include "string.h"

// extern uint32_t vTick;

InterfaceStatus interfaceStatus;

typedef struct {
    RGB rgbs[LED_NUM];
    unsigned char updatedFlag;
    unsigned char txFlag;
} RGBStatus;

namespace WS2812 {

static RGBStatus rgbStatus;
static int ws2812_isInit = 0;

void PWM_DMA_TransmitFinshed_Callback(TIM_HandleTypeDef *htim) {
    if (htim == &WS2812_TIM) {
        HAL_TIM_PWM_Stop_DMA(htim, WS2812_TIM_CHANNEL);
        rgbStatus.txFlag = 0;
    }
}

static uint32_t CCRDMABuff[LED_NUM * sizeof(RGB) * 8 + 1];

void init() {
    if (ws2812_isInit) return;
    ws2812_isInit = 1;
    HAL_TIM_RegisterCallback(&WS2812_TIM, HAL_TIM_PWM_PULSE_FINISHED_CB_ID,
                             PWM_DMA_TransmitFinshed_Callback);
    memset(&rgbStatus, 0, sizeof(RGBStatus));
    memset(CCRDMABuff, 0, sizeof(CCRDMABuff));
    // 向CCRDMABuff写入一个全绿做开机提示，但是不写入rgbStatus，这样第一次update就会把它覆盖掉
    unsigned int data;
    for (unsigned int i = 0; i < LED_NUM; i++) {
        data = scale_color(COLOR_GREEN);
        for (unsigned int j = 0; j < 24; j++)
            CCRDMABuff[i * 24 + j] =
                ((data >> (23 - j)) & 1) ? BIT1_WIDTH : BIT0_WIDTH;
    }
    CCRDMABuff[LED_NUM * 24] = 0;
    rgbStatus.txFlag = 1;
    HAL_TIM_PWM_Start_DMA(&WS2812_TIM, WS2812_TIM_CHANNEL, CCRDMABuff,
                          LED_NUM * 24 + 1);
}

void update() {
    if (!rgbStatus.updatedFlag) return;
    if (rgbStatus.txFlag) return;
    rgbStatus.txFlag = 1;
    unsigned int data;

    /*Pack the RGB Value*/
    for (unsigned int i = 0; i < LED_NUM; i++) {
        // GRB Order
        data = (rgbStatus.rgbs[i].green << 16) | 
               (rgbStatus.rgbs[i].red << 8) | 
               rgbStatus.rgbs[i].blue;
        for (unsigned int j = 0; j < 24; j++)
            CCRDMABuff[i * 24 + j] =
                ((data >> (23 - j)) & 1) ? BIT1_WIDTH : BIT0_WIDTH;
    }
    CCRDMABuff[LED_NUM * 24] = 0;

    /*Transmit DMA*/
    HAL_TIM_PWM_Start_DMA(&WS2812_TIM, WS2812_TIM_CHANNEL, CCRDMABuff,
                          LED_NUM * 24 + 1);
}

void blink(uint8_t index, uint8_t r, uint8_t g, uint8_t b) {
    if (index >= LED_NUM) return;
    rgbStatus.updatedFlag = 1;
    rgbStatus.rgbs[index].blue = b;
    rgbStatus.rgbs[index].green = g;
    rgbStatus.rgbs[index].red = r;
}

void blink(uint8_t index, uint32_t colorCode) {
    if (index >= LED_NUM) return;
    rgbStatus.updatedFlag = 1;
    rgbStatus.rgbs[index].red = (colorCode >> 16) & 0xFF;
    rgbStatus.rgbs[index].green = (colorCode >> 8) & 0xFF;
    rgbStatus.rgbs[index].blue = colorCode & 0xFF;
}

} // namespace WS2812

namespace Buzzer {

uint32_t stopTime = 0;

void init() {
    __HAL_TIM_SET_AUTORELOAD(&BUZZER_TIM, 10000000U / 2500U - 1);
    __HAL_TIM_SET_COMPARE(&BUZZER_TIM, BUZZER_TIM_CHANNEL, 0U);
    HAL_TIMEx_PWMN_Start(&BUZZER_TIM, BUZZER_TIM_CHANNEL);
}

void stop() {
    __HAL_TIM_SET_COMPARE(&BUZZER_TIM, BUZZER_TIM_CHANNEL, 0U);
}

void play(uint16_t freq, uint16_t duration) {
    __HAL_TIM_SET_AUTORELOAD(&BUZZER_TIM, 10000000U / freq - 1);
    __HAL_TIM_SET_COMPARE(&BUZZER_TIM, BUZZER_TIM_CHANNEL, 5000000U / freq);
    stopTime = sysData.vTick + duration;
}

// 这里有一个回绕问题会导致蜂鸣器异常，所以改成了这么个奇怪的写法
void update() {
    if ((int32_t)(sysData.vTick - stopTime) >= 0) {
        stop();
    }
}

} // namespace Buzzer

namespace Interface {

void updateButtonState() {
    if (HAL_GPIO_ReadPin(BTN_GPIO_Port, BTN_Pin)) {
        if (sysData.buttonPressedLast &&
            (sysData.buttonCnt > 1000 && sysData.buttonCnt < 2000)) {
            if (errorData.errorLevel == ERROR_RECOVER_MANUAL) {
                Protection::manualClearError();
            } else if (errorData.errorLevel == ERROR_RECOVER_AUTO) {
                Protection::autoClearError();
            }
        }
        sysData.buttonPressed = 0;
        sysData.buttonCnt = 0;
    } else {
        sysData.buttonPressed = 1;
        sysData.buttonCnt++;
        if (sysData.buttonCnt > 3000) {
            HRTIM::disableOutputAB();
            __disable_irq();
            while (true) NVIC_SystemReset();
        }
    }
    sysData.buttonPressedLast = sysData.buttonPressed;
}

void updateBuzzerSequence() {
    interfaceStatus.isWarningLast = interfaceStatus.isWarning;
    if (errorData.errorLevel) {
        interfaceStatus.isWarning = 1;
        if (!interfaceStatus.isWarningLast) {
            interfaceStatus.buzzerSequenceCnt = 0;
            switch (errorData.errorLevel) {
                case ERROR_UNRECOVERABLE:
                    if (errorData.errorCode & ERROR_POWERSTAGE)
                        memcpy(interfaceStatus.buzzerNote,
                               buzzerWS_Unrecoverable,
                               sizeof(buzzerWS_Unrecoverable));
                    break;
                case ERROR_RECOVER_MANUAL:
                    if (errorData.errorCode & ERROR_SCP_B)
                        memcpy(interfaceStatus.buzzerNote, buzzerWS_SCPB,
                               sizeof(buzzerWS_SCPB));
                    else
                        memcpy(interfaceStatus.buzzerNote, buzzerWS_SCPA,
                               sizeof(buzzerWS_SCPA));
                    break;
                case ERROR_RECOVER_AUTO:
                    if (errorData.errorCode & ERROR_OCP_A)
                        memcpy(interfaceStatus.buzzerNote, buzzerWS_OCPA,
                               sizeof(buzzerWS_OCPA));
                    else if (errorData.errorCode & ERROR_OCP_B)
                        memcpy(interfaceStatus.buzzerNote, buzzerWS_OCPB,
                               sizeof(buzzerWS_OCPB));
                    else if (errorData.errorCode & ERROR_OCP_R)
                        memcpy(interfaceStatus.buzzerNote, buzzerWS_OCPR,
                               sizeof(buzzerWS_OCPR));
                    else if (errorData.errorCode & ERROR_OVP_A)
                        memcpy(interfaceStatus.buzzerNote, buzzerWS_OVPA,
                               sizeof(buzzerWS_OVPA));
                    else
                        memcpy(interfaceStatus.buzzerNote, buzzerWS_OVPB,
                               sizeof(buzzerWS_OVPB));

                    break;
                case WARNING:
                    if (errorData.errorCode & WARNING_LOWBATTERY)
                        memcpy(interfaceStatus.buzzerNote, buzzerWS_LowBattery,
                               sizeof(buzzerWS_LowBattery));
                    break;
                default:
                    break;
            }
        }
    } else {
        interfaceStatus.isWarning = 0;
        interfaceStatus.buzzerSequenceCnt = 0;
        interfaceStatus.noteIndex = 0;
        return;
    }

    if (interfaceStatus.buzzerSequenceCnt ==
        interfaceStatus.buzzerNote[interfaceStatus.noteIndex].startTime) {
        Buzzer::play(
            interfaceStatus.buzzerNote[interfaceStatus.noteIndex].freq,
            interfaceStatus.buzzerNote[interfaceStatus.noteIndex].duration);
        interfaceStatus.noteIndex++;
    }

    interfaceStatus.buzzerSequenceCnt++;
    if (interfaceStatus.buzzerSequenceCnt >= WARNING_PERIOD) {
        Protection::autoClearError();
        interfaceStatus.buzzerSequenceCnt = 0;
        interfaceStatus.noteIndex = 0;
    }
}


struct FlashState {
    uint32_t startTime;
    uint32_t duration;
    uint32_t color;
    bool active;
};

static FlashState flashStates[LED_NUM];

void flashLED(uint8_t index, uint32_t color, uint32_t duration) {
    if (index >= LED_NUM) return;
    flashStates[index].startTime = sysData.vTick;
    flashStates[index].duration = duration;
    flashStates[index].color = scale_color(color);
    flashStates[index].active = true;
}

void updateLEDs() {
    // LED 0
    switch (errorData.errorLevel) {
        case NO_ERROR:
            WS2812::blink(SYSTEM_LED, COLOR_STATE_NORMAL);
            break;
        case WARNING:
            WS2812::blink(SYSTEM_LED, COLOR_STATE_WARNING);
            break;
        case ERROR_RECOVER_AUTO:
        case ERROR_RECOVER_MANUAL:
            if (sysData.vTick % 500 < 250) {
                WS2812::blink(SYSTEM_LED, COLOR_STATE_ERROR);
            } else {
                WS2812::blink(SYSTEM_LED, COLOR_BLANK);
            }
            break;
        case ERROR_UNRECOVERABLE:
            WS2812::blink(SYSTEM_LED, COLOR_STATE_ERROR);
            break;
    }

    // LED 1
    if (!psData.outputABEnabled) {
        WS2812::blink(POWER_LED, COLOR_BLANK);
    } else {
        switch (psData.dcdcMode) {
            case BUCK:
                if (psData.iLTarget > 0.5f) {
                    WS2812::blink(POWER_LED, COLOR_POWER_Buck_Charging);
                } else if (psData.iLTarget < -0.5f) {
                    WS2812::blink(POWER_LED, COLOR_POWER_Buck_Discharging);
                } else {
                    WS2812::blink(POWER_LED, COLOR_POWER_Idle);
                }
                break;
            case BOOST:
                if (psData.iLTarget > 0.5f) {
                    WS2812::blink(POWER_LED, COLOR_POWER_Boost_Charging);
                } else if (psData.iLTarget < -0.5f) {
                    WS2812::blink(POWER_LED, COLOR_POWER_Boost_Discharging);
                } else {
                    WS2812::blink(POWER_LED, COLOR_POWER_Idle);
                }
                break;
            case BUCKBOOST:
            case BOOSTBUCK:
                if (psData.iLTarget > 0.5f) {
                    WS2812::blink(POWER_LED, COLOR_POWER_BuckBoost_Charging);
                } else if (psData.iLTarget < -0.5f) {
                    WS2812::blink(POWER_LED, COLOR_POWER_BuckBoost_Discharging);
                } else {
                    WS2812::blink(POWER_LED, COLOR_POWER_Idle);
                }
                break;
            default:
                WS2812::blink(POWER_LED, COLOR_POWER_Abnormal);
                break;
        }
    }

    // LED 2
#ifdef WITHOUT_UPPER
        if (!ctrlData.refLoop.isConnected) {
            WS2812::blink(COMM_LED, COLOR_COMM_AUTONOMOUS);
        } else {
            WS2812::blink(COMM_LED, COLOR_COMM_CONNECTED);
        }
#else
        if (!ctrlData.refLoop.isConnected) {
            WS2812::blink(COMM_LED, COLOR_COMM_DISCONNECTED);
        } else {
            WS2812::blink(COMM_LED, COLOR_COMM_CONNECTED);
        }
#endif

    // Flash Override
    for (int i = 0; i < LED_NUM; i++) {
        if (flashStates[i].active) {
            if ((sysData.vTick - flashStates[i].startTime) < flashStates[i].duration) {
                WS2812::blink(i, flashStates[i].color);
            } else {
                flashStates[i].active = false;
            }
        }
    }
}

} // namespace Interface