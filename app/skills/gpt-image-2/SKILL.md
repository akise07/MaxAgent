---
title: gpt-image-2 图片生成器
description: 基于 gpt-image-2 模型的 AI 图片生成技能，通过 OpenAI 兼容 API 生成图片
trigger_phrases: 画图, 生成图片, 文生图, AI 绘图, 绘图, 图片生成, gpt-image-2, 画一张, 生成一张图
author: WorkBuddy
version: 2.0.0
agent_created: true
---

# gpt-image-2 图片生成器

## 概述

通过 OpenAI 兼容 API 调用 gpt-image-2 模型生成图片。支持自定义尺寸。

**核心设计**：
- Python 代码只从 `os.environ` 读取凭证，不硬编码
- **优先直接调用 `/images/generations` 生成图片**，生成成功即结束
- 仅当生成失败（如 400 模型不支持）时，**再**查询 `/v1/models` 排查问题
- 一次 `python -c` 完成 API 调用 + 解码保存，不将 b64_json 取出后二次传递
- 用户对话中提供的凭证通过 `export` 写入环境变量，供后续复用

## 适用场景

当你需要：
- 在对话中直接生成图片
- 生成图片并保存为本地文件
- 作为任何 AI Agent 的通用生图模块

## Python 依赖

- 标准库：`os`, `json`, `urllib`, `ssl`, `base64`, `pathlib`
- 无需第三方包

## 尺寸规则

| 项目 | 说明 |
|------|------|
| 最小尺寸 | 768×768 |
| 最大尺寸 | 3840×3840 |
| 约束 | 宽和高都必须能被 16 整除 |
| 格式 | `{宽}x{高}`，如 `1024x1024`、`1536x1024` |

校验逻辑：
```python
def validate_size(width: int, height: int) -> str:
    if not (768 <= width <= 3840 and 768 <= height <= 3840):
        raise ValueError("尺寸超出范围 (768~3840)")
    if width % 16 != 0 or height % 16 != 0:
        raise ValueError("宽和高必须能被 16 整除")
    return f"{width}x{height}"
```

## 操作流程总览

```
1. 设置凭证（env / export）
       ↓
2. 直接调用 /images/generations（生成图片）
       ↓
   ┌─ 成功 ─→ 解码 b64_json → 保存 PNG → SUCCESS
   │
   └─ 失败 ─→ 判断错误类型
               ├─ 400 模型不支持 → 查询 /v1/models → 调整参数重试
               ├─ 401             → 检查凭证
               ├─ timeout         → 重试
               └─ 其他            → 报告错误
```

**核心原则**：先试再说，失败了再查原因，不预检。

## 凭证获取流程

### 1. 检查环境变量

先检查系统环境变量 `GPT_IMAGE_API_KEY` 和 `GPT_IMAGE_BASE_URL` 是否已设置。

### 2a. 已设置 → 直接使用

Python 代码直接从 `os.environ` 读取，无需做任何额外操作。

### 2b. 未设置 → 向用户询问 → export 到环境变量

提示用户提供 API Key 和 Base URL，收到后用 `export` 写入当前 shell 环境：

```bash
export GPT_IMAGE_API_KEY='<用户提供的 key>'
export GPT_IMAGE_BASE_URL='<用户提供的 base url>'
```

之后所有 Python 代码统一从 `os.environ` 读取，**不再需要任何特殊处理**。

## 核心流程：一次性生成并保存

**一次 `python -c` 完成全部工作**：调用 API → 检查响应 → 解码 b64_json → 保存 PNG → 输出结果路径。

```bash
python -c "
import os, json, urllib.request, ssl, base64, pathlib, sys

base = os.environ.get('GPT_IMAGE_BASE_URL', '').rstrip('/')
key  = os.environ.get('GPT_IMAGE_API_KEY', '')

if not base or not key:
    print('错误: 未设置 GPT_IMAGE_API_KEY 或 GPT_IMAGE_BASE_URL', file=sys.stderr)
    sys.exit(1)

api = f'{base}/images/generations'

payload = json.dumps({
    'model': 'gpt-image-2',
    'prompt': 'a cute shiba inu dog, high quality, realistic',
    'size': '1024x1024',
    'n': 1
}).encode()

req = urllib.request.Request(api, data=payload, headers={
    'Authorization': f'Bearer {key}',
    'Content-Type': 'application/json'
})

ctx = ssl.create_default_context()
try:
    with urllib.request.urlopen(req, context=ctx, timeout=180) as r:
        body = json.loads(r.read().decode('utf-8', 'ignore'))
except Exception as e:
    print(f'API 请求失败: {e}', file=sys.stderr)
    sys.exit(1)

if 'data' not in body or len(body['data']) == 0:
    print(f'响应中没有 data 字段: {body}', file=sys.stderr)
    sys.exit(1)

item = body['data'][0]

if 'b64_json' in item:
    out = pathlib.Path('gpt_image_2.png')
    out.write_bytes(base64.b64decode(item['b64_json']))
    print(f'SUCCESS:{out}')
elif 'url' in item:
    print(f'URL:{item[\"url\"]}')
else:
    print(f'未知响应格式: {item}', file=sys.stderr)
    sys.exit(1)
"
```

> ⚠️ 注意：`prompt` 和 `size` 根据用户需求替换。`SUCCESS:xxx` 前缀用于程序化判断结果。

## 完整执行示例

### 场景：用户首次使用，提供凭证后生成图片

**用户：画一只可爱的柴犬，1024x1024**

步骤：
1. 检查 `GPT_IMAGE_API_KEY` 和 `GPT_IMAGE_BASE_URL` → 不存在
2. 提示用户提供
3. 用户提供后：`export GPT_IMAGE_API_KEY='sk-xxx'; export GPT_IMAGE_BASE_URL='https://...'`
4. **直接调用 `/images/generations`** 尝试生成（更换 prompt 和 size）
5a. 成功 → 输出 `SUCCESS:gpt_image_2.png` → `present_files` 展示
5b. 失败（400 模型不支持） → 查询 `/v1/models` 确认可用模型 → 调整参数或告知用户

### 场景：环境变量已存在，直接生成

**用户：画一张山水画，1536x1024**

步骤：
1. 检查环境变量 → 已存在，跳过询问
2. **直接执行 `python -c` 调用 `/images/generations`**（更换 prompt 和 size）
3. 成功则展示结果；失败则查 `/v1/models` 排查

## 错误处理

### 401 Unauthorized
- 检查 API Key 是否正确
- 检查 Base URL 和 API Key 是否来自同一套配置
- 确认 `export` 后环境变量已正确注入（可执行 `echo $GPT_IMAGE_API_KEY` 验证）

### 400 / 不支持模型

**注意：这是生成失败后的排查步骤，不是前置预检。** 生成图片本身直接调 `/images/generations`，遇到 400 错误（如模型不支持）时，才查询 `/v1/models` 确认该 gateway 上是否真的存在 gpt-image-2 模型：

```bash
python -c "
import os, json, urllib.request, ssl

base = os.environ.get('GPT_IMAGE_BASE_URL', '').rstrip('/')
key  = os.environ.get('GPT_IMAGE_API_KEY', '')

url = f'{base}/models'
req = urllib.request.Request(url, headers={'Authorization': f'Bearer {key}'})
ctx = ssl.create_default_context()
with urllib.request.urlopen(req, context=ctx, timeout=30) as r:
    data = json.loads(r.read().decode('utf-8', 'ignore'))
    models = [m.get('id') for m in data.get('data', [])]
    print('has_gpt_image_2 =', 'gpt-image-2' in models)
    print('可用模型:', models)
"
```

> ⚠️ 确认 `/v1/models` 和 `/v1/images/generations` 使用的是同一 gateway，不要混用。

### 证书错误
- 优先检查系统证书链、代理和网络环境
- **不要通过跳过证书校验来规避**

### 请求超时
- gpt-image-2 可能生成较慢，超时建议 180 秒
- 超时可重试一次

### 余额不足
- 出现 `insufficient balance` 说明是账户额度问题，不是接口问题

## 注意事项

1. **输出文件**：生成图片保存为当前工作目录下的 `gpt_image_2.png`
2. **一次性完成**：API 调用 + b64_json 解码 + 保存 PNG，全部在同一个 `python -c` 中完成，不将 b64_json 取出后在 AI 对话中二次传递
3. **凭证持久化**：用户对话中提供的凭证通过 `export` 写入环境变量，当前 shell 会话中后续命令可直接使用，无需重复提供
4. **结果判断**：成功输出 `SUCCESS:文件名`，失败输出到 stderr，方便 AI 判断是否生成功
5. **展示结果**：生成成功后用 `present_files` 展示图片给用户
6. **重试**：超时可重试一次；其他错误根据类型给出明确提示

## 安全原则

- 不在技能文档中保存真实密钥
- 不提供跳过 SSL 证书验证的示例
- 优先使用环境变量注入 API Key
- 如果接口不可用，先检查网络、证书、额度与配置，再重试
- 验证 `/v1/models` 与 `/v1/images/generations` 时必须使用同一个 base URL 和同一组凭证
