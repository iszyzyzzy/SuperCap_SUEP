# 工具食用指南
TODO 有些地方和我的工作流强耦合，需要改一下
## 校准
校准用calibrate.py，这个脚本是为ozone设计的，用其他调试器可能需要修改文件读取部分
首先在Calibration.hpp中启用CALIBRATION_MODE宏定义，然后编译烧录固件
然后使用ozone连接设备，watch adc.Data.tempData, 然后用电源和负载仪给各端口上电压和电流负载，待数值稳定后，右键保存数据到/debug/calibration，命名见下，脚本可以自动识别（xx可以有小数）
- AxxV.csv: 在chassis口供xxV电
- AxxA.csv: 在chassis口供24V电，ref口加xxA恒流负载
- BxxAyyV.csv: 在chassis口供24V电，cap口接xxA恒流负载，此时cap口电压为yyV
没说的口就是空载，CALIBRATION_MODE下的cap口为一个单p控制的buck降压，目标20v但因为是单p所以电压肯定会有跌落，不用管，万用表读出来是啥写上去就行（注意别看负载仪读出，它不准的）
保存好这些文件后，运行calibrate.py，脚本会自动读取这些文件并计算出校准系数，最后把系数打印出来，复制到Calibration.hpp中替换原来的系数即可
！注意往上翻翻Results里的R^2，正常应该至少0.995以上，如果非常低很可能硬件有问题，笔者已经见到了至少板间接触不良，ina损坏/虚焊，容阻焊错导致adc没读数等问题
！不要管有的时候k是负数的问题，如果这里算出来是负数，那就是负数，说明测量方向和预期相反了，不会影响使用

### 交互采样（推荐，不暂停CPU）
如果不想用调试器暂停CPU抓数据，可以使用 `capture_calibration.py` 通过 CAN 自动采样：

```bash
python capture_calibration.py COM3
```

脚本会逐步显示接线/负载要求，你在外部配置好后按回车，它会自动抓取一段稳定数据并保存到 `debug/calibration`。
默认步骤包含 A 侧正负电流点；B 侧默认只给出 `B0A/B1A/B2A`（校准模式下单 P buck 不适合做 B 侧负电流）。
对 `BxxA` 步骤，脚本会在采样后要求你输入万用表实测 CAP 电压，并自动按 `BxxAyyV.csv` 命名保存。

也可以自定义步骤：

```bash
python capture_calibration.py COM3 --steps A24V,A-2A,A-1A,A0A,A1A,B-2A20V,B2A14V
```

文件命名规则：
- `AxxV.csv`：chassis 口供 `xxV`，其他口空载
- `AxxA.csv`：chassis 口供电、ref 口加 `xxA` 恒流负载（支持负数，如 `A-1.5A.csv`）
- `AxxA@yyV.csv`：同上，但额外记录有负载时实测输入电压 `yyV`（推荐）
- `BxxA.csv`：chassis 口供 `24V`，cap 口接 `xxA` 恒流负载；脚本会额外要求输入实测 CAP 电压并最终保存为 `BxxAyyV.csv`
- `BxxAyyV.csv`：也可直接指定（手动模式），`yyV` 为实测 CAP 电压
- `BxxAyyV@zzV.csv`：在上一条基础上额外记录实测输入电压 `zzV`（推荐，可补偿线阻导致的输入压降）

`calibrate.py` 对于带负载文件会优先使用文件名中的实测输入电压；如果没有提供，会对 B 文件的 iA 估算回退使用 24V（并打印警告）。
对于 `BxxA...` 工况，脚本会按功率估算输入电流，并将 `iR` 目标设为与 `iA` 一致，不再默认 `iR=0`。

`calibrate.py` 已兼容 Ozone 导出的 CSV 和 `capture_calibration.py` 的 CSV。
## 上位机
上位机用slcan_monitor.py，使用前请确保已经安装python-can和rich库
默认是用的slcan，运行要把串口号附在后面，比如这样：
```bash
python slcan_monitor.py COM3
```
界面应该很好理解，指令可以打help看帮助