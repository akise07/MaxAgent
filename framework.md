# MaxAgent 架构文档

> 桌面 AI 聊天助手：LangChain + LangGraph Agent，封装为 FastAPI 后端 + pywebview 原生窗口。

## 1. 分层架构

依赖**单向向下**，无环。上层可引用下层，下层不得反向引用上层。

```
入口层        app.py（GUI） / main.py（CLI）
                  │
                  ▼
API 路由层     app/api/          仅路由分发 + HTTP 异常 + 依赖注入
                  │
                  ▼
业务层         app/services/     LangGraph 构造 + 聊天编排
                  │
          ┌───────┴───────┐
          ▼               ▼
持久化层   app/storage/    DTO 层   app/schemas/
JSON 读写 + 线程锁          请求体 Pydantic 模型
                  │
                  ▼
配置层         app/config/       环境配置 + 模型参数常量
```

## 2. 目录结构

```
MaxAgent/
├── app.py                         # GUI 入口（uvicorn + pywebview）
├── main.py                        # CLI 入口（终端对话样例）
├── app/
│   ├── api/                       # 路由层
│   │   ├── chat.py                #   /api/chat、/api/config、/api/open-home
│   │   ├── conversations.py       #   /api/conversations*
│   │   ├── models.py              #   /api/models*
│   │   ├── skills.py              #   /api/skills*（技能列表 + 执行）
│   │   └── debug.py               #   热更新模块（后端 reload + 前端文件监听）
│   ├── skills/                    # 技能层（文件夹 + skill.md，不含 .py）
│   │   ├── __init__.py            #   SkillSpec 元数据 dataclass
│   │   ├── web_search/            #   示例：联网搜索
│   │   │   └── skill.md           #   YAML front matter + Markdown（含 #何时调用）
│   │   ├── code_review/           #   示例：代码审查
│   │   │   └── skill.md
│   │   └── bash/                  #   Bash 命令执行
│   │       ├── skill.md           #   技能文档
│   │       └── executor.py        #   execute() 执行器
│   ├── services/                  # 业务层
│   │   ├── agent.py               #   LangGraph StateGraph 构造
│   │   └── chat_service.py        #   聊天编排（显式参数，去全局，含 /skill 调用）
│   ├── context/                   # 上下文层
│   │   ├── context.py             #   对话上下文构建（历史消息组装 + 截断）
│   │   └── skill_loader.py        #   技能加载器（扫描文件夹 + 解析 skill.md）
│   ├── storage/                   # 持久化层
│   │   ├── session_store.py       #   SessionManager（会话 JSON）
│   │   ├── models.py              #   ModelConfigStore（模型配置 JSON）
│   │   ├── sessions/              #   运行时会话数据（gitignored）
│   │   └── logs/                  #   运行时日志
│   ├── schemas/                   # DTO 层
│   │   └── requests.py            #   5 个请求体模型
│   ├── config/                    # 配置层
│   │   ├── settings.py            #   Config（从 .env 读取）
│   │   ├── model.py               #   AdvancedConfig + 思考强度常量
│   │   └── prompts.py             #   系统提示词模板
│   └── static/                    # 前端资源（html/js/css，不在本次分层范围）
├── home/                          # 用户数据区（config/memory/skills）
├── weights/                       # 视觉模型资产（YOLO/OCR，未接入主流程）
├── tests/                         # 演示脚本
└── scripts/                       # 工具脚本
```

## 3. 各包职责与边界

| 包 | 职责 | 禁止 |
|----|------|------|
| `app/api/` | FastAPI 路由声明、请求分发、HTTPException、`init_dependencies` 注入入口 | 业务编排、持久化、LangGraph 构造 |
| `app/services/` | 业务编排（chat 调用流程、LLM 参数解析、Agent 图构造） | 路由、HTTP 状态码 |
| `app/storage/` | JSON 持久化读写、线程锁、文件原子替换 | 路由、Pydantic 请求校验 |
| `app/schemas/` | API 请求体 Pydantic 模型（DTO） | 业务逻辑、默认值工厂 |
| `app/config/` | 环境配置（`Config`）、模型参数常量、`AdvancedConfig` schema、`default_advanced()` 工厂 | 持久化、路由 |

## 4. 入口点

### `app.py`（GUI 主入口，生产入口）

启动入口：`main(debug=False)`，`debug=True` 时启用热更新。

启动流程：
1. `main(debug=True)` → `enable_hot_reload(app)` 注册热更新路由 + 启动前端文件监听
2. 后台线程启动 `uvicorn` 监听 `127.0.0.1:8000`（`debug=True` 时 `reload=True`，排除 `app/static/`）
3. `wait_for_server` 轮询等待就绪
4. `webview.create_window` 创建原生窗口加载 `http://127.0.0.1:8000`
5. `webview.start(debug=True)` 进入 GUI 事件循环（F12 打开开发者工具）
6. 窗口关闭后 `disable_hot_reload()` + `stop_server()`

热更新机制（`app/api/debug.py`）：
- **后端**：uvicorn `reload=True` 监听 `app/` 下 `.py` 文件变更，自动重启
- **前端**：`_watch_frontend` 线程每 0.5s 检测 `app/static/` 文件 MD5 变化 → 调用 `/api/reload-frontend` 设标志 → 前端每 1s 轮询 `/api/poll-reload` → `location.reload()`

依赖注入顺序：
```python
session_manager = SessionManager()
agent = build_agent()
config = Config()
model_store = ModelConfigStore()
chat_api.init_dependencies(session_manager, agent, config, model_store)
conversations.init_dependencies(session_manager)
models_api.init_store(model_store)
```

### `main.py`（CLI 入口，样例运行）

瘦入口，仅 `from app.services.agent import build_agent` + `main()` 样例对话。

## 5. 配置加载时序

`app/config/settings.py` 顶部执行 `load_dotenv()`，凡 import settings 即触发 .env 加载。

```
app.py / main.py
    └─ import app.services.agent
        └─ import app.config.settings   ← load_dotenv() 在此触发
            └─ os.getenv() 读取环境变量
```

`ModelConfigStore._seed_from_env` 的 `os.getenv` 在 settings 加载之后执行，时序正确。

## 6. 关键设计决策

### 6.1 跨层依赖修复
- **问题**：原 `app/api/fun.py` 反向 import 根目录的 `config.py` 和 `main.py`
- **方案**：`Config` 移入 `app/config/settings.py`，`build_agent` 移入 `app/services/agent.py`，根 `config.py` 删除

### 6.2 `session_store.py` 命名
- **问题**：`app/storage/sessions.py` 与数据目录 `app/storage/sessions/` 存在 Python 命名空间包歧义
- **方案**：代码文件命名为 `session_store.py`，数据目录保持 `sessions/`

### 6.3 路径计算
| 文件 | 项目根推导 | 说明 |
|------|-----------|------|
| `app/api/chat.py` | `Path(__file__).resolve().parents[2]` | `app/api/` → `app/` → 项目根 |
| `app/storage/models.py` | `Path(__file__).resolve().parents[2]` | `app/storage/` → `app/` → 项目根 |
| `app/storage/session_store.py` | `os.path.dirname` × 3 | `app/storage/` → `app/` → 项目根 |

### 6.4 两个 `init_dependencies` 不合并
- `chat.init_dependencies`（4 参）与 `conversations.init_dependencies`（1 参）签名不同、注入对象不同
- 合并会破坏 `app.py` 调用约定，违反"功能不变"原则

### 6.5 `_mask_key` 助手
- `list_models` 与 `get_model` 的密钥脱敏逻辑抽为纯函数 `_mask_key(key) -> str`
- **不改任何输出字段形状**：`list_models` 返回 `api_key_masked` + `has_api_key`，`get_model` 返回 `has_api_key`

## 7. API 路由清单

| 方法 | 路径 | 路由文件 | 说明 |
|------|------|---------|------|
| POST | `/api/chat` | `chat.py` | 聊天主接口 |
| GET | `/api/config` | `chat.py` | 前端配置信息 |
| POST | `/api/open-home` | `chat.py` | 打开 home 目录 |
| GET | `/api/conversations` | `conversations.py` | 会话列表 |
| POST | `/api/conversations/new` | `conversations.py` | 新建会话 |
| GET | `/api/conversations/{id}` | `conversations.py` | 获取会话 |
| DELETE | `/api/conversations/{id}` | `conversations.py` | 删除会话 |
| PUT | `/api/conversations/rename` | `conversations.py` | 重命名会话 |
| GET | `/api/models` | `models.py` | 模型列表 |
| POST | `/api/models` | `models.py` | 新增模型 |
| GET | `/api/models/{uid}` | `models.py` | 获取模型 |
| PUT | `/api/models/{uid}` | `models.py` | 更新模型 |
| DELETE | `/api/models/{uid}` | `models.py` | 删除模型 |
| POST | `/api/models/{uid}/default` | `models.py` | 设默认模型 |
| GET | `/api/reload-frontend` | `app.py` | 前端热更新通知 |
| GET | `/api/poll-reload` | `app.py` | 前端热更新轮询 |
| GET | `/api/skills` | `skills.py` | 技能列表 |

## 8. 聊天调用流程

```
POST /api/chat
  │
  ▼
app/api/chat.py: chat()
  ├─ 校验依赖注入、会话存在性（HTTPException）
  └─ chat_service.run_chat(req, session_manager, agent, model_store, config)
       │
       ▼
  app/services/chat_service.py: run_chat()
       ├─ 首次消息自动生成标题
       ├─ 写入用户消息（session_manager.add_message）
       ├─ build_context()  ← app/context/context.py 组装 SystemMessage + 历史消息
       ├─ resolve_llm_config()  ← 从 model_store 或 config 解析 LLM 参数
       ├─ build_thinking_kwargs()  ← advanced → reasoning_effort
       ├─ build_openai_tools()  ← skill_loader.py 将技能转为 OpenAI tools 格式
       ├─ ChatOpenAI.bind_tools(tools)  ← 绑定工具到 LLM
       ├─ 第一轮 invoke → LLM 返回 tool_calls（或直接回复）
       │   ├─ 无 tool_calls → 直接使用回复内容
       │   └─ 有 tool_calls → 执行工具 → ToolMessage 追加到消息列表
       │       └─ 第二轮 invoke → LLM 根据工具结果生成最终回复
       ├─ 失败 fallback: agent.invoke()  ← LangGraph 路径
       └─ 写入助手回复（session_manager.add_message）
```

### Tool Calling 数据流

```
LLM 返回的 tool_calls 示例：
  response.tool_calls = [
    {
      "name": "web_search",
      "args": {"query": "今天天气"},
      "id": "call_xxx"
    }
  ]

后端执行：
  → _execute_tool("web_search", {"query": "今天天气"})
  → ToolMessage(content="...", tool_call_id="call_xxx")
  → 追加到 messages 列表
  → 第二轮 llm.invoke(messages) 生成最终回复
```

### skill.md → OpenAI Tool JSON Schema

skill.md 中的参数表自动转为 tools 定义：

```json
{
  "type": "function",
  "function": {
    "name": "web_search",
    "description": "搜索互联网获取实时信息",
    "parameters": {
      "type": "object",
      "properties": {
        "query": {"type": "string", "description": "搜索关键词"}
      },
      "required": ["query"]
    }
  }
}
```

`thinking_only` 或 `allow_disable_thinking` 开启时，额外设置 `chat_template_kwargs.enable_thinking=True`（Qwen 风格，常规 API 忽略）。

## 9. 持久化

### `home/config/models.json`
多模型配置列表，由 `ModelConfigStore` 管理：
- 首次启动用 `.env` 播种默认条目
- 写入用 `.tmp` 原子替换
- `threading.Lock` 线程安全
- 密钥脱敏：`_mask_key()` 前 4 + 后 2 截断

### `app/storage/sessions/*.json`
会话数据，由 `SessionManager` 管理：
- 每个会话一个 JSON 文件，文件名 = `conversation_id`
- 内存缓存 + 写时持久化
- `threading.Lock` 线程安全
- 启动时按 `mtime` 倒序加载

## 10. 前端结构与页面分布

```
app/static/
├── index.html          # 单页 HTML，所有页面/面板在同一文件
├── css/
│   └── styles.css      # 全局样式（~1600 行）
└── js/
    ├── app.js          # 主逻辑（~1200 行）
    └── i18n.js         # 国际化（中/英）
```

### 页面 / 视图

| 视图 | DOM 容器 | 说明 |
|------|----------|------|
| 欢迎页 | `#welcome` | 初始展示，含"新建任务"入口 |
| 新建任务页 | `#new-task-page` | 全功能任务创建界面（能力快捷入口 + 输入区 + 工具栏 + 配置条） |
| 对话页 | `#chat-area` | 聊天主界面（消息列表 + 底部输入框） |
| 技能面板 | `#panel-skills` | 侧边面板，展示技能卡片列表（从 `/api/skills` 加载） |
| 自动化面板 | `#panel-automation` | 侧边面板，自动化任务（未上线） |

### 模态弹窗

| 弹窗 | DOM 容器 | 说明 |
|------|----------|------|
| 设置 | `#settings-modal` | 左右两栏布局，含系统设置 / 记忆 / 模型管理 三个 tab |
| Toast | `#toast` | 轻量通知 |

### 左侧边栏功能

| 区域 | 说明 |
|------|------|
| 顶部导航 | 新建任务 / 技能 / 自动化 三个按钮 |
| 任务列表 | 搜索框 + 会话列表（`#conversation-list`） |
| 底部用户栏 | 用户菜单（设置 / 外观 / 语言 / 打开 Home 目录） |

### JS 模块划分（app.js）

| 模块 | 行号 | 职责 |
|------|------|------|
| State | 5-18 | 全局状态变量 |
| DOM refs | 19-64 | DOM 元素引用 |
| API Helpers | 65-79 | fetch 封装 |
| Toast | 80-89 | 通知提示 |
| Theme | 90-107 | 暗色/亮色主题切换 |
| i18n | 108-139 | 国际化渲染 |
| Models | 140-216 | 模型列表 CRUD + 下拉菜单 |
| Conversation | 217-379 | 会话列表加载/切换/CRUD |
| Views | 380-454 | 视图切换（欢迎页/新建任务/对话/面板） |
| Task composer | 455-587 | 新建任务页交互（附件/模型选择/发送） |
| Dropdowns | 588-620 | 下拉菜单通用逻辑 |
| User menu / settings | 621-881 | 用户菜单 + 设置弹窗 + 模型编辑表单 |
| Events | 882-1116 | 事件绑定 |
| Init | 1117- | 初始化入口 |

## 11. 其他资产

- **前端** `app/static/`（index.html / app.js / styles.css / i18n.js）
- **视觉资产** `weights/`（YOLO 图标检测 + PaddleOCR，未接入主流程）
- **演示脚本** `tests/`（手动冒烟脚本，非自动化测试）
- **工具脚本** `scripts/export_yolo_onnx.py`
