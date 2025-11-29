# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is embedded firmware for an STM32G474 microcontroller controlling a supercapacitor power management system (RM2025 PowerControlBoard). The system manages power distribution for a robotics application, featuring peak current mode buck-boost DC-DC conversion with FDCAN (CAN FD) communication to the main control board.

**Key Target**: STM32G474RB, Cortex-M4F @ 170MHz
**Build System**: Makefile-based (STM32CubeMX generated)
**Languages**: C and C++

## Architecture

### High-Level System Flow

1. **Hardware Initialization** (main.c): Initializes HAL, peripherals (ADC, HRTIM, FDCAN, GPIO, DAC, OPAMP, COMP)
2. **Application Tasks** (UserTask.cpp): Calls `systemStart()` which initializes custom C++ classes
3. **Low-Frequency (LF) Loop** (4kHz via TIM6): Multiplexed 1kHz tasks executed via state machine in `tickCallback()`
   - Task 0: System tick, buzzer, error handling
   - Task 1: CAN communication, button interface
   - Task 2: Capacitor estimation, ADC updates
   - Task 3: Battery monitoring, buzzer sequence, WPT (wireless power transfer) management
4. **High-Frequency (HF) Control**: HRTIM at 250kHz handles peak current mode PWM control

### Module Organization

**C++ Classes** (Core/Inc/\*.hpp, Core/Src/\*.cpp):
- **PowerManager**: DCDC control logic, peak current mode, voltage/current management
- **Communication**: CAN message parsing/sending, data structures (RxData, TxData formats)
- **Calibration**: ADC/hardware calibration
- **Interface**: Button input, buzzer control
- **Utility**: General-purpose functions
- **Config.hpp**: Hardware parameters, protection thresholds, ADC resolution constants

**C Drivers** (Core/Src/\*.c): HAL peripheral initialization and interrupt handlers
- adc.c, hrtim.c, fdcan.c, tim.c, dac.c, opamp.c, comp.c, gpio.c

### Key Global Data Structures (Config.hpp)

- `SystemData sysData`: System state (tick counter, initialization flag, button state)
- `PowerStageData psData`: Power stage state (duty cycles, output enable flags)
- `ADCData adcData`: Filtered ADC readings (voltages, currents)
- `RxData/TxData`: CAN message structures
- `ASKData askData`: Wireless power transfer communication data (if WPT_HARDWARE enabled)

## Communication Protocol

### FDCAN (CAN FD) - Main Control Interface
**Message ID 0x051 (old) / 0x052 (new)**

**Rx from Main Board (RxData)**:
- enableDCDC: Enable/disable buck-boost converter
- refereePowerLimit: Power limit in watts
- refereeEnergyBuffer: Energy buffer target in joules
- activeChargingLimitRatio: Charge target percentage
- useNewFeedbackMessage: Format selector bit
- Other flags: systemRestart, clearError, enableActiveChargingLimit

**Tx to Main Board (TxData / TxDataNew)**:
- statusCode: Error and mode bits
- chassisPower/refereePower: Feedback power values (new format splits float into two uint16_t)
- chassisPowerLimit: Maximum available power
- capEnergy: Capacitor energy level (0-250)

### ASK Communication (WPT Hardware Only)
- 2000 baud rate, 20 period
- 12-bit packets: 1 start, 1 stop, 1 parity, 9 data bits
- Data: 5W/80W requirement (1 bit) + 8-bit power feedback

## Build Commands

```bash
# Build firmware
make all

# Build with verbose output
make VERBOSE=1 all

# Clean build artifacts
make clean

# Full rebuild
make rebuild

# Show binary size information
make size

# Set compiler path (if arm-none-eabi-gcc not in PATH)
make GCC_PATH=/path/to/toolchain all
```

**Build Output**: Creates `build/RM2025-PowerControlBoard.{elf,hex,bin}`

**Compiler Options** (SuperCap.mk):
- Optimization: `-Ofast` (can change to `-O0`, `-O2`, `-Os`, `-Og`)
- Debug Info: `-g3` (maximal; change to `-g0`/`-g1` to reduce size)
- C Standard: C11 (`gnu11`)
- C++ Standard: C++14 (`gnu++14`)
- Warnings: Strict (`-Wall -Wextra -Wpedantic -Wshadow`)

## Code Architecture Patterns

### Peak Current Mode Buck-Boost Control
- **Inner Loop (HF)**: HRTIM@250kHz with external comparator feedback (peak current sensing)
- **Outer Loop (LF)**: 1kHz PID control for referee power and energy buffer
- **Protection**: Hardware watchdog via ADC comparators + HRTIM fault lines
  - ADC1_AWDG2: Input current (iA) → Fault2
  - ADC2_AWDG2: Capacitor current (iB) → Fault5
  - ADC1_AWDG1: Node A voltage (vA) → Fault1
  - ADC2_AWDG1: Node B voltage (vB) → Fault4
  - ADC1_AWDG3: Return current (iR) → Fault3

### LF Task Scheduling
Tasks in `tickCallback()` (TIM6 interrupt, 4kHz) execute in round-robin:
```cpp
// Index cycles 0→1→2→3→0
// Each index handles 1kHz tasks
// Use sysData.lfLoopIndex to track current task
```

### Error Handling
- **Recoverable**: `ERROR_RECOVER_AUTO` (firmware attempts recovery), `ERROR_RECOVER_MANUAL` (requires clearError command)
- **Unrecoverable**: `ERROR_UNRECOVERABLE` (power stage fault, permanent disable until power cycle)
- `Protection::errorHandlerLF()` manages error state transitions

### ADC Sampling
- **Multi-channel**: ADC1 (vA, iA, iR) and ADC2 (vB, iB)
- **Filtering**: Exponential moving average with alpha values (0.8-0.9)
- **Resolution**: Config.hpp defines ADC_VSENSE_RES, ADC_ISENSE_RES for raw→physical conversion
- **Hardware watchdog triggers**: Automatic PWM shutdown on threshold violation

## Important Configuration Values (Config.hpp)

| Parameter | Value | Purpose |
|-----------|-------|---------|
| HRTIM_PERIOD | 21760 | 250kHz switching frequency counter (170MHz / 21760) |
| OVP_A / OVP_B | 29.0 / 30.5 V | Over-voltage protection thresholds |
| OCP_CAPARR / OCP_CHASSIS | 25.5 / 20.0 A | Current protection limits |
| SCP_VOLTAGE / SCP_CURRENT | 5.0 V / 5.0 A | Short-circuit detection |
| BATTERY_LOW_LIMIT | 20.92 V | Low battery shutdown |
| HW_VSENSE_RATIO | 16.0 | Voltage divider ratio |
| HW_ISENSE_RATIO | 25.0 | Current sense amplifier ratio |

## STM32CubeMX Integration

- **Project File**: `RM2025-PowerControlBoard.ioc`
- **Auto-generated code**: Protected in `/* USER CODE BEGIN/END */` blocks
- **Custom code**: C++ classes and application logic in USER CODE blocks
- **Linker Script**: `stm32g474rbtx_flash.ld`
- **Startup**: `startup_stm32g474xx.s`

Regenerating from `.ioc` file will preserve USER CODE but may update HAL peripheral init functions.

## Conditional Compilation

- `WPT_HARDWARE`: Enables wireless power transfer (ASK communication, WPT power management)
  - Define in project settings or Config.hpp to enable

## Development Notes

1. **Real-time Constraints**: LF loop must complete within 250µs (1kHz deadline). Monitor task execution times.
2. **Interrupt Safety**: HRTIM runs at 250kHz; keep interrupt handlers short. Use volatile for shared variables.
3. **ADC Watchdog Protection**: Hardware-triggered fault output disables PWM immediately on threshold—test thresholds carefully.
4. **Float Math**: Device supports hardware FPU; use `float` freely (not `double`).
5. **CAN Timing**: FDCAN@500kHz (see fdcan.c MX_FDCAN3_Init parameters); ensure main board synchronization.
6. **Capacitor Voltage Calculation**: Energy ratio = `(V_cap / CAPARR_MAX_VOLTAGE)^2 * 250`; clamp at 250 for full-charge indication.

## External Dependencies

- **STM32G4xx HAL** (Drivers/STM32G4xx_HAL_Driver/)
- **CMSIS** (Drivers/CMSIS/)
- Standard C Library (newlib-nano)
- Math library (libm)

## Build Troubleshooting

| Issue | Solution |
|-------|----------|
| "arm-none-eabi-gcc: command not found" | Install ARM toolchain; use `make GCC_PATH=/toolchain/bin` |
| Large binary size | Change OPT to `-Os` in Makefile; disable DEBUG (`-g0`) |
| Link errors for C++ symbols | Ensure `Makefile` includes CPP_SOURCES and uses `g++` for linking |
| ADC watchdog not triggering | Check ADC init in adc.c; verify threshold values in Config.hpp match hardware ranges |
