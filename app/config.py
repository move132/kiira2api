"""
应用配置
使用 pydantic-settings 从环境变量或 .env 文件中读取配置
"""
import json
from typing import List
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    """应用配置类"""
    
    model_config = SettingsConfigDict(
        env_file='.env',
        env_file_encoding='utf-8',
        case_sensitive=False,
        extra='ignore',  # 忽略未定义的字段
    )
    
    # Kiira AI API 基础 URL
    base_url_kiira: str = Field(
        default='https://www.kiira.ai',
        alias='BASE_URL_KIIRA',
        description='Kiira AI API 基础 URL'
    )
    
    # SeaArt API 基础 URL
    base_url_seaart_api: str = Field(
        default='https://app-matrix-api.api.seaart.ai',
        alias='BASE_URL_SEAART_API',
        description='SeaArt API 基础 URL'
    )
    
    base_url_seaart_uploader: str = Field(
        default='https://aiart-uploader.api.seaart.dev',
        alias='BASE_URL_SEAART_UPLOADER',
        description='SeaArt Uploader API 基础 URL'
    )
    # api key
    api_key: str = Field(
        default='sk-123456',
        alias='API_KEY',
        description='API Key'
    )
    # 默认配置
    default_agent_name: str = Field(
        default='Nano Banana Pro🔥',
        alias='DEFAULT_AGENT_NAME',
        description='默认代理名称'
    )
    
    # Agent 列表配置
    # 支持两种格式：
    # 1. JSON 格式：AGENT_LIST=["Dress up Game", "NanoBanana PlayLab"]
    # 2. 逗号分隔：AGENT_LIST=Dress up Game,NanoBanana PlayLab
    agent_list: List[str] = Field(
        default_factory=list,
        alias='AGENT_LIST',
        description='Agent 列表配置'
    )
    
    @field_validator('agent_list', mode='before')
    @classmethod
    def parse_agent_list(cls, v):
        """解析 Agent 列表，支持 JSON 和逗号分隔格式"""
        if v is None:
            return []
        
        # 如果是列表，直接返回
        if isinstance(v, list):
            return v
        
        # 如果是字符串
        if isinstance(v, str):
            v = v.strip()
            # 尝试解析为 JSON
            if v.startswith('[') and v.endswith(']'):
                try:
                    return json.loads(v)
                except json.JSONDecodeError:
                    pass
            
            # 否则按逗号分隔
            if v:
                return [item.strip() for item in v.split(',') if item.strip()]
        
        return []


# 创建全局配置实例
settings = Settings()

# 为了向后兼容，导出原有的变量名（大写）
BASE_URL_KIIRA = settings.base_url_kiira
BASE_URL_SEAART_API = settings.base_url_seaart_api
BASE_URL_SEAART_UPLOADER = settings.base_url_seaart_uploader
DEFAULT_AGENT_NAME = settings.default_agent_name
AGENT_LIST = settings.agent_list
API_KEY = settings.api_key

# 导出配置类和实例，方便高级用法
__all__ = [
    'Settings',
    'settings',
    'BASE_URL_KIIRA',
    'BASE_URL_SEAART_API',
    'BASE_URL_SEAART_UPLOADER',
    'DEFAULT_AGENT_NAME',
    'AGENT_LIST',
    'API_KEY',
]
