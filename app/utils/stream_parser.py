"""
流式响应解析工具
优化JSON解析,避免重复解析同一数据
"""
import json
from typing import Optional, Dict, Any

from app.utils.logger import get_logger

logger = get_logger(__name__)


def extract_media_from_data(data: Dict[str, Any]) -> Optional[tuple[str, str]]:
    """
    从已解析的数据中提取媒体URL
    避免重复JSON解析,提升性能

    Args:
        data: 已解析的JSON数据字典

    Returns:
        (url, type) tuple 如果找到媒体,否则返回None
    """
    try:
        # 在choices数组->每个choice下的sa_resources数组中查找type为"video"或"image"且有"url"
        if "choices" in data and isinstance(data["choices"], list):
            for choice in data["choices"]:
                if isinstance(choice, dict) and "sa_resources" in choice and isinstance(choice["sa_resources"], list):
                    for resource in choice["sa_resources"]:
                        if (
                            isinstance(resource, dict)
                            and resource.get("type") in ("video", "image")
                            and "url" in resource
                            and resource["url"]
                        ):
                            return resource["url"], resource["type"]
    except Exception as e:
        logger.debug(f"提取媒体URL时出错: {e}")

    return None


def parse_stream_response(line: str) -> Optional[tuple[str, str]]:
    """
    解析流式响应中的媒体URL(兼容旧接口)
    建议使用extract_media_from_data以避免重复JSON解析

    Args:
        line: SSE格式的响应行

    Returns:
        (url, type) tuple 如果找到媒体,否则返回None
    """
    if not line.startswith("data: "):
        return None

    try:
        json_str = line[6:]  # 移除 "data: " 前缀
        data = json.loads(json_str)
        return extract_media_from_data(data)
    except json.JSONDecodeError:
        pass
    except Exception as e:
        logger.debug(f"解析响应时出错: {e}")

    return None

