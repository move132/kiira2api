# Kiira2API

[![Python](https://img.shields.io/badge/Python-3.11+-blue.svg)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.121.2-green.svg)](https://fastapi.tiangolo.com/)
[![License](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

基于 FastAPI 的 API 服务，提供兼容 OpenAI API 格式的聊天完成和模型查询接口。项目采用模块化架构，整合了 Kiira AI 客户端功能。

## ✨ 特性

- 🚀 **OpenAI API 兼容**: 完全兼容 OpenAI API 格式，便于现有客户端集成
- 💬 **聊天完成接口**: 支持 `/v1/chat/completions` 接口，提供流式和非流式响应
- 🤖 **模型查询**: 支持 `/v1/models` 接口，查询可用模型列表
- 🔄 **流式响应**: 支持 Server-Sent Events (SSE) 流式响应
- 📁 **文件上传**: 支持图片、文件上传功能
- ⚙️ **灵活配置**: 支持环境变量和 `.env` 文件配置
- 🏗️ **模块化架构**: 清晰的分层结构，易于维护和扩展

## 📋 目录

- [快速开始](#快速开始)
- [配置说明](#配置说明)
- [API 文档](#api-文档)
- [项目结构](#项目结构)
- [开发指南](#开发指南)
- [许可证](#许可证)

## 🚀 快速开始

### 环境要求

- Python >= 3.11
- [uv](https://github.com/astral-sh/uv) 包管理器（推荐）

### 安装步骤

1. **克隆项目**

```bash
git clone https://github.com/move132/kiira2api.git
cd kiira2api
```

2. **安装依赖**

```bash
# 使用 uv 安装依赖（推荐）
uv sync
```

3. **配置环境变量**

首先复制 `.env.example` 到 `.env`：

```bash
# Linux/macOS
cp .env.example .env

# Windows
copy .env.example .env
```

然后根据需要编辑 `.env` 文件（可选，也可使用环境变量）：
.env 默认配置可以不修改，需要添加额外的agent时添加

```env
# Agent 列表
AGENT_LIST=["Nano Banana Pro🔥","Nano Banana Pro 🔥👉 Try Free","Sora 2: AI Video Remixer", "Veo 3: AI Video Weaver", "Midjourney Art Studio"]
```

4. **运行服务**

```bash
# 方式 1: 使用 uv 运行（推荐）
uv run python main.py

# 方式 2: 使用 uvicorn 直接运行
uvicorn app.main:app --reload --port 8999

# 方式 3: 直接运行模块
uv run python -m app.main
```

服务启动后，访问：
- API 文档: http://localhost:8999/docs
- 健康检查: http://localhost:8999/health

### 使用 Docker 运行

1. **构建镜像**

```bash
docker build -t kiira2api:latest .
```

2. **运行容器**

```bash
# 基本运行
docker run -d -p 8999:8999  -v $(pwd)/data:/app/data --name kiira2api kiira2api:latest

# 使用环境变量
docker run -d -p 8999:8999 \
  -e API_KEY='sk-123456' \
  -e AGENT_LIST='["Dress up Game", "NanoBanana PlayLab"]' \
  --name kiira2api kiira2api:latest

# 挂载 .env 文件
docker run -d -p 8999:8999 \
  --env-file .env \
  --name kiira2api kiira2api:latest
```

3. **查看日志**

```bash
docker logs -f kiira2api
```

4. **停止和删除容器**

```bash
docker stop kiira2api
docker rm kiira2api
```

### 使用 Docker Compose 运行（推荐）

1. **启动服务**

```bash
# 构建并启动服务
docker-compose up -d

# 或者使用 docker compose（新版本）
docker compose up -d
```

2. **查看日志**

```bash
# 查看日志
docker-compose logs -f

# 或者
docker compose logs -f
```

3. **停止服务**

```bash
# 停止服务
docker-compose down

# 停止并删除数据卷
docker-compose down -v
```

4. **重启服务**

```bash
# 重启服务
docker-compose restart

# 重新构建并启动
docker-compose up -d --build
```

**Docker Compose 优势**:
- 自动挂载 `./data` 目录到容器
- 自动加载 `.env` 文件配置
- 自动配置网络和健康检查
- 支持服务重启策略
- 更简单的管理命令

### 使用 GitHub Container 镜像

1. **拉取镜像**

```bash
# 拉取最新版本
docker pull ghcr.io/move132/kiira2api:latest

# 拉取特定版本
docker pull ghcr.io/move132/kiira2api:v1.0.0
```

2. **运行容器**

```bash
# 使用 GHCR 镜像运行
docker run -d -p 8999:8999 \
  -v $(pwd)/data:/app/data \
  --name kiira2api \
  ghcr.io/move132/kiira2api:latest
```
## ⚙️ 配置说明

### 环境变量

所有配置项都支持通过环境变量或 `.env` 文件设置，优先级：**环境变量 > .env 文件 > 默认值**

| 变量名 | 说明 | 默认值 |
|--------|------|--------|
| `API_KEY` | API 密钥（用于接口鉴权） | `sk-123456` |
| `DEFAULT_AGENT_NAME` | 默认代理名称 | `Nano Banana Pro🔥` |
| `AGENT_LIST` | Agent 列表（JSON 或逗号分隔） | `[]` |

**注意**: 如果 `API_KEY` 使用默认值 `sk-123456`，系统将跳过鉴权验证。生产环境请务必修改为安全的密钥。

## 📚 API 文档

### 鉴权说明

所有 `/v1/*` 接口都需要进行 API Key 鉴权（除非使用默认值 `sk-123456`）。

**鉴权方式**（两种方式任选其一）：

1. **Authorization Header**（推荐，兼容 OpenAI API 格式）:
```bash
Authorization: Bearer sk-your-api-key-here
```

2. **X-API-Key Header**:
```bash
X-API-Key: sk-your-api-key-here
```

**示例请求**:

```bash
curl -X POST "http://localhost:8999/v1/chat/completions" \
  -H "Authorization: Bearer sk-your-api-key-here" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "Nano Banana Pro🔥",
    "messages": [{"role": "user", "content": "你好"}]
  }'
```

如果 API Key 无效或缺失，将返回 `401 Unauthorized` 错误。

### POST /v1/chat/completions

聊天完成接口，兼容 OpenAI API 格式。

**请求示例**:

```bash
curl -X POST "http://localhost:8999/v1/chat/completions" \
  -H "Authorization: Bearer sk-your-api-key-here" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "Nano Banana Pro🔥",
    "messages": [
      {"role": "user", "content": "你好"}
    ],
    "stream": false
  }'
```

**流式响应示例**:

```bash
curl -X POST "http://localhost:8999/v1/chat/completions" \
  -H "Authorization: Bearer sk-your-api-key-here" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "Nano Banana Pro🔥",
    "messages": [
      {"role": "user", "content": "你好"}
    ],
    "stream": true
  }'
```

**响应格式**:

```json
{
  "id": "chatcmpl-xxx",
  "object": "chat.completion",
  "created": 1677652288,
  "choices": [
    {
      "index": 0,
      "message": {
        "role": "assistant",
        "content": "你好！有什么可以帮助你的吗？"
      },
      "finish_reason": "stop"
    }
  ],
  "usage": {
    "prompt_tokens": 9,
    "completion_tokens": 12,
    "total_tokens": 21
  }
}
```

### GET /v1/models

获取可用模型列表。

**请求示例**:

```bash
curl -X GET "http://localhost:8999/v1/models" \
  -H "Authorization: Bearer sk-your-api-key-here"
```

**响应格式**:

```json
{
  "object": "list",
  "data": [
    {
      "id": "Nano Banana Pro🔥",
      "object": "model",
      "created": 1677610602,
      "owned_by": "move132"
    }
  ]
}
```

### GET /health

健康检查端点。

**响应格式**:

```json
{
  "status": "healthy"
}
```

## 📁 项目结构

```
kiira2api/
├── app/                      # 应用主目录
│   ├── __init__.py
│   ├── main.py              # FastAPI 应用入口
│   ├── config.py            # 配置管理
│   ├── models/              # 数据模型
│   │   ├── __init__.py
│   │   └── schemas.py       # Pydantic 数据模型定义
│   ├── api/                 # API 路由
│   │   ├── __init__.py
│   │   └── v1/              # v1 版本 API
│   │       ├── __init__.py
│   │       ├── chat.py      # 聊天相关路由
│   │       └── models.py    # 模型相关路由
│   ├── services/            # 业务逻辑服务
│   │   ├── __init__.py
│   │   ├── chat_service.py  # 聊天服务
│   │   └── kiira_client.py  # Kiira AI 客户端服务
│   └── utils/               # 工具函数
│       ├── __init__.py
│       ├── http_client.py   # HTTP 请求工具
│       ├── file_utils.py    # 文件处理工具
│       ├── stream_parser.py # 流式响应解析工具
│       └── logger.py        # 日志工具
├── data/                    # 数据目录
│   └── account.json         # 账户配置（示例）
├── main.py                  # 兼容入口
├── pyproject.toml          # 项目配置和依赖管理
├── uv.lock                 # 依赖锁定文件
├── memory_bank.md          # 项目记忆库
└── README.md               # 项目说明文档
```

## 🛠️ 开发指南

### 技术栈

- **Python**: >=3.11
- **FastAPI**: 0.121.2 - 现代、快速的 Web 框架
- **Uvicorn**: 0.38.0 - ASGI 服务器
- **Pydantic**: 2.12.4 - 数据验证和序列化
- **Requests**: 2.32.5 - HTTP 客户端库
- **pydantic-settings**: 2.0.0 - 配置管理

### 代码规范

- 使用类型提示（Type Hints）
- 遵循 PEP 8 代码风格
- 使用 Pydantic BaseModel 定义数据模型
- API 路由使用 APIRouter 组织
- 使用 `{{CHENGQI:...}}` 注释标记代码变更

### 架构设计

- **分层架构**: API 层、服务层、工具层清晰分离
- **模块化设计**: 功能按模块拆分，职责清晰
- **依赖注入**: 使用 FastAPI 的依赖注入系统
- **数据验证**: 使用 Pydantic 进行请求/响应数据验证

### 开发流程

1. **理解需求**: 阅读 `memory_bank.md` 了解项目上下文
2. **设计方案**: 确定技术实现方案
3. **编写代码**: 按照项目规范编写代码
4. **测试验证**: 确保功能正常
5. **更新文档**: 更新相关文档和记忆库

## 📝 更新日志

### v1.0.0 (2025-11-20)

- ✨ 初始版本发布
- 🎉 实现 OpenAI API 兼容接口
- 🔄 支持流式响应
- ⚙️ 支持环境变量配置
- 📦 模块化架构重构

## 🤝 贡献

欢迎提交 Issue 和 Pull Request！

## 📄 许可证

本项目采用 MIT 许可证。详情请参阅 [LICENSE](LICENSE) 文件。

## 👤 作者

**move132**

- GitHub: [@move132](https://github.com/move132)
- 项目地址: https://github.com/move132/kiira2api

## 🙏 致谢

感谢所有为本项目做出贡献的开发者！

---

**注意**: 本项目仅供学习和研究使用。使用本服务时，请遵守相关服务的使用条款。

