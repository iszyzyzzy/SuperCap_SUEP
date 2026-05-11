#pragma once
#include "main.h"
//#include "PowerManager.hpp"
//#include "Config.hpp"

#define HARDWARE_ID 103

#ifndef HARDWARE_ID
#error "please specify hardware id"
#endif


//#define WPT_HARDWARE
//#define CALIBRATION_MODE
//#define IGNORE_CAPACITOR_ERROR

#ifdef CALIBRATION_MODE

#define HARDWARE_UID_W0 0x00000000
#define HARDWARE_UID_W1 0x00000000
#define HARDWARE_UID_W2 0x00000000

#define ADC_VA_K        0.00284025493302185f
#define ADC_VA_B        0.096382087f
#define ADC_VB_K        0.00283064245539459f
#define ADC_VB_B        0.096382087f

#define ADC_IA_K        -0.00426032707865977f
#define ADC_IA_B        34.6220566648572f
#define ADC_IB_K        0.00436961348441836f
#define ADC_IB_B        -35.442372697575f

#define ADC_IREF_K      0.00438520650402692f
#define ADC_IREF_B      -35.6851326479174f

#define WPT_HARDWARE
#define ADC_VWPT_K      0.00282862236057022f
#define ADC_VWPT_B      0.126888445762173f
#define ADC_IWPT_K      0.00421074805006724f
#define ADC_IWPT_B      -34.2917170449864f


#elif (HARDWARE_ID == 101) // TEST

#define HARDWARE_UID_W0     0x001E002F
#define HARDWARE_UID_W1     0x534B5009
#define HARDWARE_UID_W2     0x20343732

#define ADC_VA_K        0.002850088173729f
#define ADC_VA_B        -0.067354875f
#define ADC_VB_K        0.002851284425586f
#define ADC_VB_B        -0.035420308f
#define ADC_IA_K        -0.004507756508638f
#define ADC_IA_B        36.513712163f
#define ADC_IB_K        0.004293845269546f
#define ADC_IB_B        -34.784356092f
#define ADC_IREF_K      0.004236687275736f
#define ADC_IREF_B      -34.496932090f

// TODO WPT

#elif (HARDWARE_ID == 102) // 01

#define HARDWARE_UID_W0     5439523
#define HARDWARE_UID_W1     1095651349
#define HARDWARE_UID_W2     540227125

#define ADC_VA_K        0.002876844091531f
#define ADC_VA_B        0.089569945f
#define ADC_VB_K        0.002874192926089f
#define ADC_VB_B        0.022003271f
#define ADC_IA_K        -0.004686151139523f
#define ADC_IA_B        37.900212620f
#define ADC_IB_K        0.004247970196219f
#define ADC_IB_B        -34.420117905f
#define ADC_IREF_K      0.004296879429689f
#define ADC_IREF_B      -34.945227154f

#elif (HARDWARE_ID == 103) // 02

#define HARDWARE_UID_W0     4325407
#define HARDWARE_UID_W1     1095651347
#define HARDWARE_UID_W2     540227125

#define ADC_VA_K        0.002823099050220f
#define ADC_VA_B        0.079438619f
#define ADC_VB_K        0.002808464881297f
#define ADC_VB_B        0.060015680f
#define ADC_IA_K        -0.004564355115652f
#define ADC_IA_B        36.948333303f
#define ADC_IB_K        0.004277271513668f
#define ADC_IB_B        -34.665408906f
#define ADC_IREF_K      0.004268022280234f
#define ADC_IREF_B      -34.689022901f

#endif