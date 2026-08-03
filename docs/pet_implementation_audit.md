# PET 实现审计

Hargreaves-Samani 使用 `ET0=0.0023*Ra*(Tmean+17.8)*sqrt(Tmax-Tmin)`，其中 `Ra` 为日尺度 MJ/(m2*d)，输出为 mm/d。审计会检查温度摄氏度、纬度只转一次弧度、日序、闰年、Ra 和逐日独立实现差值；不会额外乘 `0.408`。
