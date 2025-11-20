"""
文件处理工具函数
"""
import base64
import requests
from typing import Optional, Tuple

from app.utils.logger import get_logger

logger = get_logger(__name__)


def guess_content_type(file_name: str, default: str = "image/jpeg") -> str:
    """
    根据文件名猜测 Content-Type
    
    Args:
        file_name: 文件名
        default: 默认Content-Type
        
    Returns:
        Content-Type字符串
    """
    suffix = file_name.lower()
    if suffix.endswith((".png", ".jpeg", ".jpg", ".webp", ".gif")):
        if suffix.endswith(".png"):
            return "image/png"
        if suffix.endswith(".webp"):
            return "image/webp"
        if suffix.endswith(".gif"):
            return "image/gif"
        return "image/jpeg"
    return default



def get_file_extension_from_content_type(content_type: str) -> str:
    """
    根据 content_type 返回对应的文件扩展名
    
    Args:
        content_type: MIME类型
        
    Returns:
        文件扩展名（包含点号）
    """
    content_type_map = {
        "image/jpeg": ".jpg",
        "image/jpg": ".jpg",
        "image/png": ".png",
        "image/webp": ".webp",
        "image/gif": ".gif",
    }
    return content_type_map.get(content_type.lower(), ".jpg")



def decode_base64_img(b64_string: str, content_type: str) -> Tuple[Optional[bytes], Optional[str]]:
    """
    解码 base64 字符串到图片数据
    
    Args:
        b64_string: base64编码的字符串
        content_type: 图片的Content-Type
        
    Returns:
        (图片数据, Content-Type) 元组，失败返回 (None, None)
    """
    try:
        return base64.b64decode(b64_string), content_type
    except Exception as e:
        logger.error(f"解析 base64 图片失败：{e}")
        return None, None



def get_image_data_and_type(image_path: str, file_name: str) -> Tuple[Optional[bytes], Optional[str]]:
    """
    获取图片数据和 Content-Type，支持本地路径、URL 和 base64
    
    Args:
        image_path: 图片路径（本地路径、URL或base64字符串）
        file_name: 文件名（用于猜测类型）
        
    Returns:
        (图片数据, Content-Type) 元组，失败返回 (None, None)
    """
    # URL 图片
    if image_path.startswith(("http://", "https://")):
        logger.info("检测到 image_path 是图片URL，正在下载...")
        try:
            img_resp = requests.get(image_path, timeout=30)
            img_resp.raise_for_status()
            content_type = img_resp.headers.get("Content-Type", guess_content_type(file_name))
            if not content_type.startswith("image/"):
                content_type = guess_content_type(file_name)
            return img_resp.content, content_type
        except requests.exceptions.RequestException as e:
            logger.error(f"图片URL下载失败: {e}")
            return None, None

    # data:image/xxx;base64 格式
    data_url_prefix = "data:image/"
    if image_path.strip().startswith(data_url_prefix):
        logger.info("检测到 image_path 是 data:image/xxx;base64 格式，正在解码...")
        try:
            head, b64data = image_path.split(",", 1)
            content_type = guess_content_type(file_name)
            if ";base64" in head:
                if "png" in head:
                    content_type = "image/png"
                elif "webp" in head:
                    content_type = "image/webp"
                elif "gif" in head:
                    content_type = "image/gif"
                
                return decode_base64_img(b64data, content_type)
            logger.error("不是标准的 data:image/xxx;base64 编码")
        except Exception as e:
            logger.error(f"解析 data URL 图片失败：{e}")
        return None, None

    # 纯 base64 字符串
    _img_str = image_path.strip()
    # 简单判断是否为 base64 串（长度>128，且只包含 base64 字符）
    if len(_img_str) > 128 and all(c.isalnum() or c in "+/=" for c in _img_str):
        logger.info("检测到 image_path 可能是 base64 图片串，正在解码...")
        content_type = guess_content_type(file_name)
        return decode_base64_img(_img_str, content_type)

    # 本地文件路径
    logger.info("检测到 image_path 是本地文件，正在读取内容...")
    try:
        with open(image_path, "rb") as f:
            data = f.read()
        content_type = guess_content_type(file_name)
        return data, content_type
    except FileNotFoundError:
        logger.error(f"文件不存在: {image_path}")
        return None, None
    except Exception as e:
        logger.error(f"读取本地文件失败：{e}")
        return None, None

