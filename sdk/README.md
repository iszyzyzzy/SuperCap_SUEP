# 超级电容通讯sdk
该sdk用于与超级电容控制板进行通讯，包含打包数据和解包数据的功能。
考虑到目前要用这玩意的性能不会特别差，就只做了解析出实际单位的版本，要raw数据得直接自己解包
另外我们直接了新版包类型，毕竟现在的我们也没啥历史包袱
clone说明: 你可以直接clone sdk分支，这个分支里只有这个sdk的代码，方便集成到你的工程里
```bash
git clone -b sdk <repo-url> --single-branch
```
## 安装
将`sdk/include/supercap_sdk.h`和`sdk/src/supercap_sdk.c`添加到你的工程中，并包含头文件`supercap_sdk.h`即可使用。
## 使用方法
```c
#include "supercap_sdk.h"

uint8_t tx_buffer[8];
uint8_t rx_buffer[8];

// 你可以像hal一样这样初始化控制结构体
SuperCap_Control_t control = {0};
// 如果需要重置为默认值可以再次 control = (SuperCap_Control_t){0};
// 或者语义明确一点的
SuperCap_InitDefaultControl(&control);
// 注意这个是有值的，不是全0的

// 然后设置你想要的控制参数
control.enable_dcdc = true;
control.system_restart = false; // 这个只要发一个包就会重启！不要重复发
control.clear_error = false;
control.enable_active_charging_limit = false;
// ！！！这两个从裁判系统来
// 如果真的裁判系统掉线了什么建议设置为37w/57j,这相当于回落到最低的功率默认值和禁用缓冲能量闭环
control.referee_power_limit = POWER_LIMIT; 
control.referee_energy_buffer = ENERGY_BUFFER; 

control.active_charging_limit_ratio = 0.8f; // 在enable_active_charging_limit为false时无效

// 打包控制数据
// 打包及发送频率10hz即可，你可以从裁判系统拿到数据后立刻发送
SuperCap_PackTxData(&control, tx_buffer);
// 接下来就是你的can发送代码了
// eg.
// FDCAN_TxHeaderTypeDef tx_header = {
    //         SUPERCAP_SEND_CAN_ID,
    //         FDCAN_STANDARD_ID,
    //         FDCAN_DATA_FRAME,
    //         FDCAN_DLC_BYTES_8,
    //         FDCAN_ESI_PASSIVE,
    //         FDCAN_BRS_OFF,
    //         FDCAN_CLASSIC_CAN,
    //         FDCAN_NO_TX_EVENTS,
    //         0
    // };
// HAL_FDCAN_AddMessageToTxFifoQ(&hfdcan1, &tx_header, tx_buffer);

// 然后是解包，具体是在中断里还是搞状态机什么的随你了
SuperCap_Feedback_t feedback;

// eg.
// ... 接收代码将header和data放到rxHeader和rx_buffer里
if (rxHeader.Identifier == SUPERCAP_RECEIVE_CAN_ID) && (rxHeader.DataLength == 0x8) && (rxHeader.IdType == FDCAN_STANDARD_ID) {
    SuperCap_ParseRxData(rx_buffer, &feedback);
}
// 读feedback即可

```
## 数据格式
### 发送给超级电容的控制数据 (Chassis -> Supercap)  CAN ID: 0x061
| Byte | Bit | 字段 | 类型 | 描述 |
|------|-----|------|------|------|
| 0    | 0   | enable_dcdc | bool | 开启dcdc |
|      | 1   | system_restart | bool | 要求系统重启 |
|      | 2-4 | reserved | - | 保留位 |
|      | 5   | clear_error | bool | 清除错误标志 |
|      | 6   | enable_active_charging_limit | bool | 启用主动充电功率限制 |
|      | 7   | use_new_msg | bool | 使用新消息格式（本sdk固定为1） |
| 1-2  | -   | referee_power_limit | uint16_t | 裁判系统功率限制，单位W，小端 |
| 3-4  | -   | referee_energy_buffer | uint16_t | 裁判系统能量缓冲，单位J，小端 |
| 5    | -   | active_charging_limit_ratio | uint8_t | 主动充电功率限制比例，换算见下 |
| 6-7  | -   | reserved | - | 保留位 |

### 接收自超级电容的反馈数据 (Supercap -> Chassis)  CAN ID: 0x052
| Byte | Bit | 字段 | 类型 | 描述 |
|------|-----|------|------|------|
| 0    | 7   | dcdc_enabled | bool | dcdc是否开启 |
|      | 6   | new_msg_flag | bool | 新消息格式标志(本sdk应当为1) |
|      | 5-4 | wpt_status | enum | 无限充电状态，详见下 |
|      | 3-2 | limit_factor | enum | 功率限制因素，详见下 |
|      | 1-0 | error_flags | enum | 错误标志位，详见下 |
| 1-2  | -   | chassis_power | 映射 | 底盘功率，小端，换算见下 |
| 3-4  | -   | referee_power | 映射 | 裁判系统功率，小端，换算见下 |
| 5-6  | -   | chassis_power_limit | uint16_t | 底盘功率限制，小端，单位W |
| 7    | -   | cap_energy | uint8_t | 电容能量百分比（0-250 => 0-100%） |

#### 映射说明
将uint16映射到-256~+768，分辨率0.015625，可以这样计算
```c
float result = ((float)raw - 16384) / 64.0f;
```
#### 能量百分比说明
cap_energy的计算是(VCap/CAPARR_MAX_VOLTAGE)^2 * 250U，CAPARR_MAX_VOLTAGE默认为28.8V，这意味着这里的值和能量就是成正比的，不用额外处理，不过另外要注意这个值是可以超过250的，能量回收什么的优先级更高能让它超过电压环

---
