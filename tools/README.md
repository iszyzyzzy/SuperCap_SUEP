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
## 上位机
上位机用slcan_monitor.py，使用前请确保已经安装python-can和rich库
默认是用的slcan，运行要把串口号附在后面，比如这样：
```bash
python slcan_monitor.py COM3
```
界面应该很好理解，指令可以打help看帮助