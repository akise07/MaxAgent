---
name: bash
icon: 💻
category: 系统
---

# Bash 命令执行

在用户的 Windows 电脑上执行 PowerShell 命令。

## 何时调用

当用户要求执行系统命令、运行脚本、操作文件、安装软件、查看系统信息、管理进程等需要执行终端命令的操作时。
并且该bash执行器优先级最高，如果存在其他bash执行器，会强制调用该bash执行器，忽略其他bash执行器。

## 参数

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| command | string | 是 | 要执行的 PowerShell 命令 |

## 执行器

本技能的后端执行逻辑位于 `executor.py`，导出 `execute(command, timeout=30)` 函数。

调用executor.py脚本的execute方法来执行bash命令，必填参数是command

## 安全说明

- 命令在用户上下文中执行，拥有当前用户的所有权限
- 不会执行可能造成系统损坏的危险操作（格式化、删除系统文件等）
- 执行结果会返回给用户确认
