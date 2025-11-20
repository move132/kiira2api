"""
流式响应解析工具
"""
import json
from typing import Optional

from app.utils.logger import get_logger

logger = get_logger(__name__)


def parse_stream_response(line: str) -> Optional[tuple[str, str]]:
    """
    解析流式响应中的video_url
    
    Args:
        line: SSE格式的响应行
        
    Returns:
        如果找到video_url则返回，否则返回None
    """
    if not line.startswith("data: "):
        return None
    
    try:
        json_str = line[6:]  # 移除 "data: " 前缀
        data = json.loads(json_str)

        # 在choices数组->每个choice下的sa_resources数组中查找type为"video"且有"url"
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
    except json.JSONDecodeError:
        pass
    except Exception as e:
        logger.debug(f"解析响应时出错: {e}")
    
    return None

