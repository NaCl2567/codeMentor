# Frontend (Code Tutor Studio)

这个前端按 `CodeTutorAgent` 工作流设计：

- 主控对话区：模拟 `orchestrator_agent` 收消息并分流
- 意图看板：展示 `request_exercise / submit_code / learning_path / chat`
- 三个结果区：练习题、代码审查报告、学习路径

## 启动

在项目根目录执行任一方式：

1. Python 静态服务
```bash
python -m http.server 5500
```
然后访问 `http://127.0.0.1:5500/frontend/`

2. VSCode Live Server 直接打开 `frontend/index.html`

## 模式

- `Mock Mode`（默认开启）：纯前端模拟整个工作流
- 关闭 `Mock Mode`：调用 `POST http://127.0.0.1:8000/api/chat`

请求体约定：
```json
{
  "user_id": "demo_user",
  "message": "给我一题 Python 基础练习"
}
```

响应体建议：
```json
{
  "response": "...",
  "intent": "request_exercise",
  "params": {"language": "Python"},
  "exercise_markdown": "...",
  "review_markdown": "...",
  "path_markdown": "..."
}
```

如果你希望，我下一步可以把 `backend` 的 FastAPI 接口也一起补上，直接和这个前端联调。
