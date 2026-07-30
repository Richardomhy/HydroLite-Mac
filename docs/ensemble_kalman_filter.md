# 轻量 EnKF

EnKF 用 NumPy 对路由流量、基流和修正因子建立集合，包含模型/强迫扰动、正观测误差、协方差正则化、膨胀和非负约束。默认 20、最大 30 个成员。prior/posterior spread 与 innovation 仅为诊断；没有真实误差依据时不声称概率区间已严格校准。
