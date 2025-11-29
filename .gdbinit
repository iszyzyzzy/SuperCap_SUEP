target remote :3333
monitor reset halt

define reset
    monitor reset 
end

define halt
    monitor halt
end

define calib
    p adcData.tempData
end

define save_calib
    # 设置日志文件名为 calib_data.csv
    set logging file calib_data.csv
    # 确保是追加模式 (默认即为追加，显式设置更安全)
    set logging overwrite off
    # 开启日志
    set logging on
    # 使用 eval 构造命令，避免将字符串作为表达式在目标机上求值(导致malloc错误)
    eval "printf \"", $arg0, ", %.5f, %.5f, %.5f, %.5f, %.5f, %.5f, %.5f\\n\", adcData.tempData[0], adcData.tempData[1], adcData.tempData[2], adcData.tempData[3], adcData.tempData[4], adcData.tempData[5], adcData.tempData[6]"
    # 关闭日志
    set logging off
    echo [Saved to calib_data.csv]\n
end