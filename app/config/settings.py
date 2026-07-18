"""应用配置：从 .env 文件与环境变量读取。

凡 import 本模块即触发 load_dotenv()，保证后续 os.getenv 调用能读到 .env。
"""
import os

from dotenv import load_dotenv

load_dotenv()


class Config:
    """应用配置类，从 .env 文件和环境变量中读取配置"""

    # MAXAGENT API 配置
    API_ENDPOINT: str = os.getenv("MAXAGENT_API_ENDPOINT", "http://localhost:8111/v1")
    API_KEY: str = os.getenv("MAXAGENT_API_KEY", "")
    MODEL_NAME: str = os.getenv("MAXAGENT_MODEL_NAME", "hy3")
