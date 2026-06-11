# GEE 认证指南

HydroLite-Mac 不提交、复制或保存任何 Google、GEE、service account、OAuth token 或 Streamlit secrets。认证应在本地或云端环境中单独配置。

## 本地方式

推荐先运行：

```bash
python scripts/gee_auth_local.py
```

如果尚未认证，按提示执行：

```bash
python -c "import ee; ee.Authenticate(); ee.Initialize(project='你的project')"
```

设置项目：

```bash
export GEE_PROJECT="你的project"
```

诊断：

```bash
python scripts/diagnose_gee.py
python -m hydrolite gee diagnose
```

## Google Cloud Project

确保：

- Google Cloud Project 已存在。
- Earth Engine API 已启用。
- 当前账号或 service account 有 Earth Engine 权限。

也可使用：

```bash
export GOOGLE_CLOUD_PROJECT="你的project"
```

## Service Account

如果使用 service account：

```bash
export GOOGLE_APPLICATION_CREDENTIALS="/path/to/service-account.json"
export GEE_PROJECT="你的project"
```

不要把 JSON 文件复制到项目目录，不要提交到 git。

## Streamlit Cloud Secrets

在 Streamlit Cloud 的 Secrets 面板配置：

```toml
[gee]
project = "你的project"
```

如果后续需要 service account secret，请只在 Streamlit Cloud secrets 中配置，不要提交 `.streamlit/secrets.toml`。

## 不要提交

不要提交：

- `.streamlit/secrets.toml`
- `configs/gee.local.yaml`
- `*service-account*.json`
- `*credentials*.json`
- `~/.config/earthengine`
- `~/.config/gcloud`
