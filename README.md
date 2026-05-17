# 智能编程导师 (CodeTutorAgent)

一个基于大语言模型的智能编程导师系统，提供自适应编程练习、代码审查和学习路径规划三大核心功能，覆盖"练-评-学"全流程。

## 核心功能

### 自适应编程练习引擎
根据用户设定的目标和当前能力评估，动态生成难度递进、知识点关联的编程题目。支持算法实现、代码重构、调试等多种题型，可对接 LeetCode 题库。

### 智能代码 Review
对用户提交的代码进行语义级分析，指出逻辑错误、边界情况遗漏、代码坏味道、性能隐患和安全风险，生成结构化的 Review 报告。

### 个性化学习路径规划 (Beta)
结合用户的知识图谱掌握度、学习风格和目标岗位技能要求，自动生成分阶段学习路径，推荐学习资源，并随学习进度动态调整。

## 系统架构

```
用户界面 (Web)
        │
导师主控Agent (ReAct)
  ├── 调度 ──→ 练习设计师Agent (ReAct + Tools)
  ├── 调度 ──→ 代码审查Agent (ReAct + Tools)
  ├── 调度 ──→ 学习路径规划Agent (Plan-and-Solve)
  └── 调用工具：长期记忆、LeetCode MCP、笔记系统
```

- **导师主控 Agent**：意图分类（request_exercise / submit_code / learning_path / chat），调度子 Agent
- **练习设计师 Agent**：生成练习题，优先从 LeetCode 题库匹配，匹配失败时 LLM 动态出题
- **代码审查 Agent**：静态分析、安全扫描、语义审查，结合 LeetCode 题解做参考评审
- **学习路径规划师 Agent**：Plan-and-Solve 模式，先生成大纲再逐步细化

## 项目结构

```
codeMentor/
├── backend/
│   ├── api_server.py              # FastAPI 后端入口
│   ├── run_agent_check.py         # 离线冒烟测试 / 在线测试
│   ├── run_cli_session.py         # 命令行交互式会话
│   └── src/
│       ├── agent.py               # CodeTutorAgent 主控 Agent
│       ├── config.py              # TutorConfig 全局配置
│       ├── models.py              # 数据模型定义
│       ├── prompts.py             # 四个 Agent 的 System Prompt
│       ├── prompt_utils.py        # Prompt 安全格式化工具
│       └── services/
│           ├── exercise_service.py    # 练习生成服务
│           ├── review_service.py      # 代码审查服务
│           ├── path_service.py        # 学习路径规划服务
│           ├── memory_service.py      # 长期记忆管理服务
│           ├── leetcode_service.py    # LeetCode GraphQL API 服务
│           ├── leetcode_mcp_client.py # LeetCode MCP stdio 客户端
│           └── leetcode_mcp_tools.py  # LeetCode MCP 工具封装
├── frontend/
│   ├── index.html                 # SPA 主页面
│   ├── app.js                     # 前端逻辑（Mock / 真实 API 双模式）
│   └── style.css                  # 样式
├── run_agent_check.sh             # 冒烟测试脚本
├── run_backend_api.sh             # 启动 FastAPI 服务脚本
├── run_backend_cli.sh             # 启动 CLI 会话脚本
├── .env.example                   # 环境变量模板
└── requirements.txt               # Python 依赖
```

## 环境配置

### 1. Python 环境

项目依赖 `hello_agents` 框架。推荐使用独立虚拟环境：

```bash
# 创建虚拟环境
python -m venv venv

# 激活（Windows Git Bash）
source venv/Scripts/activate

# 激活（Linux / macOS）
source venv/bin/activate

# 安装依赖
pip install hello-agents fastapi uvicorn pydantic
```

**注意**：项目启动脚本（`run_*.sh`）默认使用硬编码路径 `helloAgents/agent_py313/python.exe`，如果使用自己的虚拟环境，可修改脚本或直接用 `python` 命令运行。

### 2. 环境变量

复制模板文件并根据实际情况修改：

```bash
cp .env.example backend/.env
```

主要配置项：

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `DEEPSEEK_API_KEY` / `LLM_API_KEY` | LLM API 密钥（必填） | - |
| `LLM_PROVIDER` | LLM 提供商：deepseek / openai / ollama / lmstudio | `deepseek` |
| `LLM_MODEL_ID` | 模型 ID | `deepseek-chat` |
| `LLM_BASE_URL` | 自定义 API 地址（可选） | 各 provider 默认值 |
| `LLM_TEMPERATURE` | 生成温度 | `0.2` |
| `MAX_HISTORY_TURNS` | 最大对话轮数 | `10` |
| `ENABLE_NOTES` | 启用笔记功能 | `true` |
| `ENABLE_MEMORY` | 启用长期记忆 | `true` |
| `ENABLE_LEETCODE` | 启用 LeetCode 题库 | `true` |
| `ENABLE_LEETCODE_MCP` | 启用 LeetCode MCP（获取完整题面） | `false` |
| `LEETCODE_SITE` | LeetCode 站点：cn / global | `cn` |

#### 使用 DeepSeek（默认）

```bash
LLM_PROVIDER=deepseek
LLM_MODEL_ID=deepseek-chat
DEEPSEEK_API_KEY=sk-xxxxxxxx
LLM_BASE_URL=https://api.deepseek.com
```

#### 使用 OpenAI

```bash
LLM_PROVIDER=openai
LLM_MODEL_ID=gpt-4o
LLM_API_KEY=sk-xxxxxxxx
```

#### 使用本地模型（Ollama / LM Studio）

```bash
LLM_PROVIDER=ollama
LOCAL_LLM=llama3:8b
OLLAMA_BASE_URL=http://localhost:11434
```

### 3. LeetCode MCP（可选）

如需获取完整题面、约束条件和题解摘要用于更高质量的练习出题与代码审查，可启用 LeetCode MCP：

```bash
ENABLE_LEETCODE_MCP=true
LEETCODE_MCP_COMMAND=npx
LEETCODE_MCP_ARGS="-y @jinzcdev/leetcode-mcp-server --site cn"
```

关闭时系统仍会通过 GraphQL API 获取公开题目列表元数据，只是不包含完整题面。

## 运行方式

### 1. CLI 交互式会话

在终端中与导师进行对话：

```bash
# 使用脚本
bash run_backend_cli.sh

# 或直接调用
python backend/run_cli_session.py

# 指定用户 ID 并显示意图分类
python backend/run_cli_session.py --user-id my_user --show-intent

# 单轮对话
python backend/run_cli_session.py --once "给我一题 Python 基础练习"
```

CLI 中可用命令：
- `/help` - 查看帮助
- `/state` - 查看当前会话状态
- `/history` - 查看最近对话历史
- `/exit` - 退出

### 3. FastAPI 后端

启动 API 服务器供前端调用：

```bash
# 使用脚本
bash run_backend_api.sh

# 或直接调用
python -m uvicorn backend.api_server:app --host 127.0.0.1 --port 8000 --reload
```

API 端点：

- `GET /health` - 健康检查
- `POST /api/chat` - 对话接口

请求示例：

```json
{
  "user_id": "demo_user",
  "message": "给我一题 Python 列表基础练习"
}
```

响应示例：

```json
{
  "response": "## 练习题目：...",
  "intent": "request_exercise",
  "params": {"language": "Python", "difficulty": "基础"},
  "exercise_markdown": "...",
  "review_markdown": "",
  "path_markdown": ""
}
```

### 4. 前端界面

前端为纯静态页面，有两种模式：

**Mock 模式（默认）**：开关开启时，前端不依赖后端，用内置逻辑模拟完整工作流，适合体验界面交互。

**API 模式**：在界面右上角点击关闭 Mock 开关后，前端向 `http://127.0.0.1:8000/api/chat` 发送请求，需要先启动 FastAPI 后端。

启动前端：

```bash
# 方式一：Python 静态服务器
python -m http.server 5500
# 访问 http://127.0.0.1:5500/frontend/

# 方式二：VS Code Live Server 直接打开 frontend/index.html
```

### 完整启动流程

```bash
# 1. 确保后端 .env 已配置
cp .env.example backend/.env
# 编辑 backend/.env，填入 API Key

# 2. 启动后端（终端一）
bash run_backend_api.sh

# 3. 启动前端（终端二）
python -m http.server 5500

# 4. 浏览器访问 http://127.0.0.1:5500/frontend/
# 5. 关闭 Mock 开关，开始对话
```

## 使用示例

### 请求练习
```
给我一题 Python 动态规划入门练习
给我一题 JavaScript 数组中等难度
来一题关于回溯算法的题
```

### 提交代码审查
```
帮我 review 这段代码：
```python
def two_sum(nums, target):
    for i in range(len(nums)):
        for j in range(len(nums)):
            if nums[i] + nums[j] == target:
                return [i, j]
```
```

### 学习路径规划
```
我想成为 Python 后端工程师，给我学习路径
我对前端开发感兴趣，帮我规划一下路线
```

## 依赖

- Python 3.10+
- `hello-agents` - Agent 框架
- `fastapi` + `uvicorn` - Web API
- `pydantic` - 数据校验
- (可选) Node.js + `@jinzcdev/leetcode-mcp-server` - LeetCode MCP
