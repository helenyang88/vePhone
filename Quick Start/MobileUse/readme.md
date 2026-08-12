# 火山引擎 Mobile Use Quick Start

本目录提供两类 Mobile Use 示例：

- `openapi_sample/`：最小化 OpenAPI 调用示例，适合快速验证 AK/SK、网络和接口连通性。
- `ui_test_demo/`：完整的本地 Web 测试平台，包含用例管理、测试计划、任务执行、设备池、执行轨迹和结果报告。

## 目录结构

```text
MobileUse/
├── openapi_sample/
│   └── python_openapi_sample.py      # OpenAPI 最小调用示例
├── requirements.txt                  # openapi_sample 依赖
├── readme.md                         # 本说明
└── ui_test_demo/                     # Mobile Use 测试平台
    ├── README.md                     # 英文说明
    ├── README.zh-CN.md               # 中文说明
    ├── .env.example                  # 本地配置模板
    ├── pyproject.toml                # Python 后端依赖
    ├── package.json                  # 前端依赖与脚本
    ├── src/mua_platform/             # FastAPI 后端
    ├── web/                          # React + Vite 前端
    ├── tests/                        # 后端、前端和 E2E 测试
    └── scripts/                      # 部署辅助脚本
```

## 环境要求

- Python 3.12+
- uv
- Node.js 22+
- npm
- 能访问火山引擎 OpenAPI 域名，例如 `open.volcengineapi.com`
- 已开通 Mobile Use / 云手机相关服务权限

## 快速开始

### 运行 OpenAPI 最小示例

```bash
cd "Quick Start/MobileUse"
pip install -r requirements.txt
export VOLC_ACCESSKEY="YOUR_AK"
export VOLC_SECRETKEY="YOUR_SK"
python openapi_sample/python_openapi_sample.py
```

该示例展示如何通过 `volcenginesdkcore.UniversalApi` 完成签名、发起请求和基础错误处理。

### 运行 Mobile Use 测试平台

```bash
cd "Quick Start/MobileUse/ui_test_demo"
uv sync --dev
npm ci
cp .env.example .env
```

编辑 `.env`，至少配置以下真实执行所需字段：

- `MOBILE_USE_ACCESS_KEY_ID`
- `MOBILE_USE_SECRET_ACCESS_KEY`
- `MOBILE_USE_PRODUCT_ID`
- `MOBILE_USE_TOS_BUCKET`
- `MOBILE_USE_TOS_REGION`

启动后端：

```bash
uv run uvicorn mua_platform.main:app --reload --host 127.0.0.1 --port 8000
```

另开终端启动前端：

```bash
npm run dev
```

默认访问地址：

- 后端：`http://127.0.0.1:8000`
- 前端：`http://127.0.0.1:5173`

首次打开页面后，创建管理员账号，在设置页配置 Mobile Use Runner，然后进入设备池、用例库或测试计划页面开始执行。

## 常用命令

在 `ui_test_demo/` 目录下运行：

```bash
uv run pytest
npm test
npm run build
```

## 更多说明

- `ui_test_demo/README.md`：英文使用说明。
- `ui_test_demo/README.zh-CN.md`：中文使用说明。
- `.env` 会包含 AK/SK 等敏感信息，不要提交到仓库。
- 本地运行数据默认写入 `ui_test_demo/data/`，该目录不应提交。

## 参考链接

- 火山引擎文档：https://www.volcengine.com/docs
- SDK 文档：https://www.volcengine.com/docs/sdk/
