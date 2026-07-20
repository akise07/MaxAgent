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
│   │   └── bash/                  #   Bash 命令执行（已废弃，由 tools/system.py 接管）
│   │       ├── skill.md           #   技能文档（仅用于技能列表展示）
│   │       └── executor.py        #   执行器（已废弃，保留兼容）
│   ├── tools/                     # 系统内置工具层（@tool 装饰器）
│   │   ├── system.py              #   bash 工具（PowerShell 命令执行）
│   │   └── file.py                #   文件操作工具（预留）
│   ├── services/                  # 业务层
│   │   ├── agent.py               #   LangGraph StateGraph 构造
│   │   └── chat_service.py        #   聊天编排（显式参数，去全局，含 /skill 调用）
│   ├── context/                   # 上下文层
│   │   ├── context.py             #   对话上下文构建（历史消息组装 + 截断 + token 计数）
│   │   ├── skill_loader.py        #   技能加载器（扫描文件夹 + 解析 skill.md）
│   │   └── tool_loader.py         #   工具加载器（扫描 tools/ + 生成描述文本）
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
| POST | `/api/chat` | `chat.py` | 聊天主接口（非流式） |
| POST | `/api/chat/stream` | `chat.py` | 聊天流式接口（SSE） |
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
| GET | `/api/chat/context-usage` | `chat.py` | 上下文 token 使用量 |

## 8. 聊天调用流程

```
POST /api/chat
  │
  ▼
app/api/chat.py: chat()
  ├─ 校验依赖注入、会话存在性（HTTPException）
  └─ chat_service.run_chat(req, session_manager, model_store, config)
       │
       ▼
  app/services/chat_service.py: run_chat()
       ├─ 首次消息自动生成标题
       ├─ 写入用户消息（session_manager.add_message）
       ├─ _build_llm()  ← 构建 LLM 实例
       │   ├─ resolve_llm_config()  ← 从 model_store 或 config 解析 LLM 参数
       │   ├─ build_thinking_kwargs()  ← advanced → reasoning_effort + extra_body
       │   ├─ build_openai_tools()  ← skill_loader.py 将技能转为 OpenAI tools 格式（排除 bash）
       │   ├─ load_all_tools()  ← tool_loader.py 扫描 tools/ 加载 @tool 装饰器工具
       │   ├─ ChatOpenAI.bind_tools(skill_tools)  ← 绑定技能工具
       │   └─ ChatOpenAI.bind_tools(system_tools)  ← 绑定系统工具
       ├─ build_context(tools=system_tools, include_skills=True)  ← 组装 SystemMessage
       │   ├─ 基础 system prompt
       │   ├─ + get_tool_descriptions(system_tools)  ← 系统工具描述
       │   └─ + get_skill_descriptions()  ← 技能描述（排除 bash）
       ├─ build_agent(llm, _execute_tool)  ← 构建 LangGraph Agent Loop
       │   │
       │   ▼
       │   ┌─────────────────────────────────────────────────┐
       │   │         LangGraph Agent Loop                     │
       │   │                                                 │
       │   │   START → agent（LLM 调用）                      │
       │   │              │                                  │
       │   │              ├─ 无 tool_calls → END              │
       │   │              └─ 有 tool_calls → tools（执行工具） │
       │   │                    │                            │
       │   │                    └─ agent（继续思考）           │
       │   │                         ↑_____________|         │
       │   │                                                 │
       │   │   最大迭代 10 次，防止无限循环                    │
       │   └─────────────────────────────────────────────────┘
       │
       └─ 写入助手回复（session_manager.add_message，含 thinking 字段）
```

### LangGraph Agent Loop 架构

```
app/services/agent.py: build_agent(llm, tool_executor)
  │
  ├─ AgentState: { messages, iteration_count }
  │
  ├─ 节点：
  │   ├─ agent  ← _call_model(state, llm)：调用 LLM，返回 AIMessage
  │   └─ tools  ← _execute_tools(state, tool_executor)：执行 tool_calls，返回 ToolMessage[]
  │
  └─ 边：
      ├─ START → agent
      ├─ agent → 条件边 _should_continue()
      │   ├─ 有 tool_calls 且未超限 → tools
      │   └─ 无 tool_calls 或超限 → END
      └─ tools → agent（循环）
```

### 思维链（reasoning_content）数据流

```
OpenAI 兼容 API 返回 delta.reasoning_content
  → monkey-patch _convert_delta_to_message_chunk 存入 additional_kwargs
  → 流式输出时提取为 thinking 事件（SSE type: "thinking"）
  → 前端渲染为可折叠"深度思考"行（默认展开）
  → 持久化到会话 JSON 的 thinking 字段
  → 后续对话通过 build_context 的 additional_kwargs 传入 LLM
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

工具执行优先级：
  1. 系统内置工具（app/tools/ 下的 @tool 装饰器工具）
     → 通过 load_all_tools() 查找匹配的 BaseTool.invoke()
  2. 技能目录下的 executor.py
     → 通过 skill.dir_path 定位，用 importlib.util.spec_from_file_location
       从绝对路径加载 executor.py（不依赖 app.skills 包名）
  3. 回退到读取 skill.md 返回文档内容

多轮工具调用：
  - LangGraph agent loop 自动处理多轮 tool calling
  - 每轮：agent 思考 → 调用工具 → tools 执行 → agent 继续思考
  - 直到 LLM 不再请求工具或达到最大迭代次数（10 次）

两段式思考：
  - 第一轮 thinking：决定调用工具前的推理过程
  - 第二轮 thinking：分析工具执行结果后的推理过程
  - 前端分别渲染为独立的可折叠 thinking 行
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
| DOM refs | 19-67 | DOM 元素引用 |
| API Helpers | 68-82 | fetch 封装 |
| Toast | 83-92 | 通知提示 |
| Theme | 93-110 | 暗色/亮色主题切换 |
| i18n | 111-142 | 国际化渲染 |
| Models | 143-259 | 模型列表 CRUD + 下拉菜单（含上下文进度圈） |
| Conversation | 260-665 | 会话列表加载/切换/CRUD + 消息渲染（含 thinking 行） |
| Skills | 666-698 | 技能列表加载 |
| Views | 699-773 | 视图切换（欢迎页/新建任务/对话/面板） |
| Task composer | 774-985 | 新建任务页交互（附件/模型选择/发送） |
| Dropdowns | 986-1018 | 下拉菜单通用逻辑 |
| User menu / settings | 1019-1275 | 用户菜单 + 设置弹窗 + 模型编辑表单 |
| Events | 1276-1526 | 事件绑定（含上下文指示器悬浮事件） |
| Init | 1527-1543 | 初始化入口 |
| Hot Reload | 1544- | 前端热更新轮询 |

## 11. 方法清单

### `app.py`

```
_access_log()
  └─ FastAPI 中间件：自定义访问日志，过滤热更新心跳请求
index()
  └─ 返回 index.html 首页
start_server()
  └─ 后台线程启动 uvicorn 服务器（127.0.0.1:8000）
stop_server()
  └─ 停止 uvicorn 服务器
wait_for_server()
  └─ 轮询等待服务器就绪（超时 15s）
create_window()
  └─ 创建 pywebview 原生窗口（1200×800，最小 900×600）
main()
  └─ 应用主入口：初始化依赖 → 启动服务器 → 创建窗口 → 进入 GUI 事件循环
```

### `app/api/chat.py`

```
init_dependencies()
  └─ 注入全局依赖（SessionManager / Config / ModelConfigStore）
_open_in_file_manager()
  └─ 用系统文件管理器打开指定目录（跨平台）
get_config()
  └─ GET /api/config：返回前端配置（API 端点、模型名、默认模型 ID、home 目录）
open_home()
  └─ POST /api/open-home：在文件管理器中打开 home 目录
chat()
  └─ POST /api/chat：非流式聊天接口，校验依赖后调用 chat_service.run_chat()
get_context_usage()
  └─ GET /api/chat/context-usage：返回会话的上下文 token 使用量
chat_stream()
  └─ POST /api/chat/stream：流式聊天接口（SSE），返回 StreamingResponse
```

### `app/api/conversations.py`

```
init_dependencies()
  └─ 注入 SessionManager 依赖
list_conversations()
  └─ GET /api/conversations：返回所有会话列表
new_conversation()
  └─ POST /api/conversations/new：创建新会话
get_conversation()
  └─ GET /api/conversations/{id}：获取指定会话详情
delete_conversation()
  └─ DELETE /api/conversations/{id}：删除会话
rename_conversation()
  └─ PUT /api/conversations/rename：重命名会话
```

### `app/api/models.py`

```
init_store()
  └─ 注入 ModelConfigStore 依赖
get_store()
  └─ 获取 ModelConfigStore 实例（未初始化则抛 500）
list_models()
  └─ GET /api/models：返回模型列表 + 默认模型 ID
get_model()
  └─ GET /api/models/{uid}：获取单个模型详情（含密钥占位符）
create_model()
  └─ POST /api/models：新增模型配置
update_model()
  └─ PUT /api/models/{uid}：更新模型配置
delete_model()
  └─ DELETE /api/models/{uid}：删除模型
set_default_model()
  └─ POST /api/models/{uid}/default：设为默认模型
```

### `app/api/skills.py`

```
api_list_skills()
  └─ GET /api/skills：返回所有可用技能列表
```

### `app/api/debug.py`

```
enable_hot_reload()
  └─ 启用热更新：注册路由 + 启动前端文件监听线程
disable_hot_reload()
  └─ 停止热更新（窗口关闭时调用）
_register_routes()
  └─ 注册 /api/reload-frontend 和 /api/poll-reload 路由
reload_frontend()
  └─ GET /api/reload-frontend：前端文件变更后通知浏览器刷新
poll_reload()
  └─ GET /api/poll-reload：前端轮询检测是否需要刷新
_start_frontend_watcher()
  └─ 启动前端文件监听线程
_watch_frontend()
  └─ 每 0.5s 检测 static/ 文件 MD5 变化 → 触发 reload-frontend
_hash_file()
  └─ 计算文件 MD5 哈希（嵌套在 _watch_frontend 内）
```

### `app/config/model.py`

```
default_advanced()
  └─ 返回 advanced 字段的默认值 dict（供存储层持久化使用）
```

### `app/config/prompts.py`

```
get_system_prompt()
  └─ 获取系统提示词模板字符串
```

### `app/context/context.py`

```
_get_encoding()
  └─ 根据模型名返回 tiktoken 编码名称（默认 cl100k_base）
count_context_tokens()
  └─ 精确计算构建上下文后的总 token 数（system prompt + 历史消息 + thinking）
build_context()
  └─ 构建完整对话上下文消息列表（SystemMessage + 历史 + 工具/技能描述注入）
_dump_context()
  └─ 将上下文消息列表输出到 app/context/context.json（调试用）
```

### `app/context/skill_loader.py`

```
_parse_skill_md()
  └─ 解析 skill.md 文件（YAML front matter + Markdown body），返回 SkillSpec
_parse_parameters()
  └─ 解析参数定义（优先 YAML JSON Schema，回退 Markdown 参数表）
_parse_parameters_table()
  └─ 从 Markdown 参数表解析为 OpenAI Tool JSON Schema
_extract_field()
  └─ 从 YAML front matter 中提取单行字段值
_extract_multiline_field()
  └─ 从 YAML front matter 中提取多行字段值（缩进块）
_discover_skills()
  └─ 扫描 app/skills/ 下所有子文件夹，读取 skill.md
get_skills()
  └─ 获取所有已加载的技能（按名称索引，懒加载 + 缓存）
get_skill()
  └─ 按名称获取单个技能元数据
list_skills()
  └─ 返回技能列表（用于 API 输出，仅含 name/description/icon/category）
build_openai_tools()
  └─ 构建 OpenAI Tool Calling 格式的 tools 列表（排除 bash）
```

### `app/context/tool_loader.py`

```
load_all_tools()
  └─ 扫描 app/tools/ 下所有模块，调用 get_tools() 合并返回所有工具
get_tool_descriptions()
  └─ 将 BaseTool 列表格式化为 system prompt 可用的描述文本
get_skill_descriptions()
  └─ 将 skills 目录下的技能描述格式化为 system prompt 可用的文本（排除 bash）
```

### `app/services/agent.py`

```
_call_model()
  └─ Agent 节点：调用 LLM 生成回复或工具调用请求（含迭代计数）
_execute_tools()
  └─ Tools 节点：执行 LLM 请求的工具调用，返回 ToolMessage 列表
_should_continue()
  └─ 条件边：有 tool_calls 且未超限 → tools，否则 → END
build_agent()
  └─ 构建 LangGraph Agent Loop（agent 节点 + tools 节点 + 条件边循环，最大 10 次迭代）
```

### `app/services/chat_service.py`

```
_patched_convert_delta_to_message_chunk()
  └─ Monkey-patch：让 langchain_openai 保留 reasoning_content 到 additional_kwargs
build_thinking_kwargs()
  └─ 根据 advanced 配置构造 reasoning_effort / model_kwargs / extra_body
resolve_llm_config()
  └─ 从 model_store 或全局 Config 解析 LLM 参数（model/api_key/base_url/advanced）
_read_skill_md()
  └─ 读取 skill.md 正文（去掉 YAML front matter）
_build_llm()
  └─ 构建 ChatOpenAI 实例 + bind_tools（技能工具 + 系统工具），返回 (llm, system_tools)
_ensure_title()
  └─ 首次消息自动生成会话标题（取前 20 字符）
_execute_tool()
  └─ 执行工具调用（优先级：系统工具 → executor.py → skill.md 回退）
run_chat()
  └─ 非流式聊天编排：标题生成 → 消息写入 → LangGraph Agent Loop → 提取最终回复
run_chat_stream()
  └─ 流式聊天编排：通过 agent.astream_events() 逐块输出 token/thinking/tool_call/tool_result/done/error
```

### `app/storage/models.py`

```
_mask_key()
  └─ 密钥脱敏：前 4 + 后 2 截断，中间用 **** 占位
ModelConfigStore._normalize_advanced()
  └─ 兜底规整 advanced 字段为标准结构，缺字段自动补默认值
ModelConfigStore._item_out()
  └─ 统一 list/get 返回的字段形态（剥离明文 key、补全 advanced）
ModelConfigStore.__init__()
  └─ 初始化存储路径 + 线程锁 + 确保文件存在
ModelConfigStore._ensure_file()
  └─ 确保 models.json 存在，不存在则用 .env 播种
ModelConfigStore._seed_from_env()
  └─ 用环境变量生成默认模型条目
ModelConfigStore._read()
  └─ 读取 models.json，异常时重建
ModelConfigStore._write()
  └─ 原子写入 models.json（.tmp 替换）
ModelConfigStore.list_models()
  └─ 返回模型列表（含密钥脱敏 + is_default 标记）
ModelConfigStore.get_model()
  └─ 按 uid 获取单个模型（可选包含明文密钥）
ModelConfigStore.get_default()
  └─ 获取默认模型（无默认时返回第一个）
ModelConfigStore.create_model()
  └─ 新增模型配置（可选设为默认）
ModelConfigStore.update_model()
  └─ 更新模型配置（advanced 合并而非替换）
ModelConfigStore.delete_model()
  └─ 删除模型（若删除默认则自动切换）
ModelConfigStore.set_default()
  └─ 设置指定模型为默认
```

### `app/storage/session_store.py`

```
SessionManager.__init__()
  └─ 初始化存储目录 + 线程锁 + 内存缓存 + 启动加载
SessionManager._session_file()
  └─ 返回会话 JSON 文件路径
SessionManager._load_all()
  └─ 启动时加载所有会话文件到内存（按 mtime 倒序）
SessionManager._save()
  └─ 将会话写入磁盘 JSON 文件
SessionManager.create()
  └─ 创建新会话（时间戳 ID）
SessionManager.list_all()
  └─ 返回所有会话列表（含预览、消息数）
SessionManager.get()
  └─ 获取指定会话完整信息
SessionManager.delete()
  └─ 删除会话（内存 + 磁盘文件）
SessionManager.rename()
  └─ 重命名会话标题
SessionManager.exists()
  └─ 检查会话是否存在
SessionManager.add_message()
  └─ 追加消息并持久化（支持 tool_calls / tool_call_id / thinking）
SessionManager.get_messages()
  └─ 获取会话所有消息列表
```

### `app/tools/system.py`

```
bash()
  └─ @tool 装饰器：在 Windows 上执行 PowerShell 命令并返回结果
get_system_tools()
  └─ 返回所有系统内置工具列表
get_tools()
  └─ tool_loader 统一接口：返回本模块定义的所有工具
```

## 12. 其他资产

- **前端** `app/static/`（index.html / app.js / styles.css / i18n.js）
- **视觉资产** `weights/`（YOLO 图标检测 + PaddleOCR，未接入主流程）
- **演示脚本** `tests/`（手动冒烟脚本，非自动化测试）
- **工具脚本** `scripts/export_yolo_onnx.py`
