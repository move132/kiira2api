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

    支持两种数据结构:
    1. sa_resources 在 choice 层级: choices[0].sa_resources
    2. sa_resources 在 delta 层级: choices[0].delta.sa_resources

    Args:
        data: 已解析的JSON数据字典

    Returns:
        (url, type) tuple 如果找到媒体,否则返回None
        type 统一返回小写 "image" 或 "video"
    """
    try:
        # 验证 choices 字段
        choices = data.get("choices")
        if not isinstance(choices, list):
            logger.debug(
                f"extract_media_from_data: 未找到有效 choices 字段, "
                f"data_keys={list(data.keys())}"
            )
            return None

        logger.debug(f"extract_media_from_data: 收到 choices, 数量={len(choices)}")

        # 遍历每个 choice
        for idx, choice in enumerate(choices):
            if not isinstance(choice, dict):
                logger.debug(
                    f"extract_media_from_data: choice[{idx}] 类型异常: {type(choice)}"
                )
                continue

            # 收集所有可能的 sa_resources 来源
            resource_locations = []

            # 1. 检查 choice 层级的 sa_resources
            sa_resources = choice.get("sa_resources")
            if isinstance(sa_resources, list):
                resource_locations.append(("choice.sa_resources", sa_resources))
            elif sa_resources is not None:
                logger.debug(
                    f"extract_media_from_data: choice[{idx}].sa_resources "
                    f"类型异常: {type(sa_resources)}"
                )

            # 2. 检查 delta 层级的 sa_resources
            delta = choice.get("delta")
            if isinstance(delta, dict):
                delta_sa_resources = delta.get("sa_resources")
                if isinstance(delta_sa_resources, list):
                    resource_locations.append(
                        ("choice.delta.sa_resources", delta_sa_resources)
                    )
                elif delta_sa_resources is not None:
                    logger.debug(
                        f"extract_media_from_data: choice[{idx}].delta.sa_resources "
                        f"类型异常: {type(delta_sa_resources)}"
                    )

            if not resource_locations:
                logger.debug(
                    f"extract_media_from_data: choice[{idx}] 未包含 sa_resources 字段"
                )
                continue

            # 遍历所有资源位置
            for location, resources in resource_locations:
                logger.debug(
                    f"extract_media_from_data: 在 {location} 中发现 "
                    f"{len(resources)} 个资源候选"
                )

                for res_idx, resource in enumerate(resources):
                    if not isinstance(resource, dict):
                        logger.debug(
                            f"extract_media_from_data: {location}[{res_idx}] "
                            f"不是字典, 实际类型: {type(resource)}"
                        )
                        continue

                    # 提取 URL
                    url = resource.get("url")
                    if not url:
                        continue

                    # 提取并规范化 type (大小写不敏感)
                    raw_type = resource.get("type")
                    if raw_type is None:
                        continue

                    normalized_type = str(raw_type).lower()
                    if normalized_type in ("video", "image"):
                        logger.debug(
                            f"extract_media_from_data: 命中媒体资源, "
                            f"location={location}, index={res_idx}, "
                            f"type={normalized_type}, url={str(url)[:100]}"
                        )
                        return url, normalized_type

        logger.debug("extract_media_from_data: 未找到可用媒体资源")

    except Exception as e:
        logger.debug(f"提取媒体URL时出错: {e}", exc_info=True)

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

