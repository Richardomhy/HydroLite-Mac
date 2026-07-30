# LSTM 洪水预测 MVP

真实 LSTM 门禁建议至少 8 个合格真实事件、1000 个有效时步和 2 个独立测试事件；本阶段不要求安装 PyTorch，也不训练大型网络。少量事件不得声称 operational。

PyTorch 是可选依赖，设备优先 Apple MPS，无法使用时回退 CPU。真实项目状态为 `insufficient_data`，不训练真实 LSTM。

synthetic smoke test 使用固定随机种子、小隐藏层、最多 2 层、最多 20 epochs、最长 6 小时 horizon 和 120 秒上限。当前环境缺少 PyTorch 时状态为 `skipped_optional_dependency`，不影响物理集合、报告和 Streamlit。

任何生成的 `.pt`、`.pth`、`.ckpt`、`.onnx`、scaler 或 joblib 模型均位于忽略的输出目录，且不进入预测 bundle。
