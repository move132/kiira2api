"""
HTTP 客户端工具函数
提供复用连接的HTTP Session和统一超时管理
"""
import json
import requests
from typing import Optional, Dict, Any, Tuple

from app.config import BASE_URL_KIIRA
from app.utils.logger import get_logger

logger = get_logger(__name__)

# 全局Session单例,复用HTTP连接以提升性能
_session: Optional[requests.Session] = None

# 默认超时配置: (连接超时, 读取超时) 秒
DEFAULT_TIMEOUT: Tuple[int, int] = (3, 15)


def build_headers(
    device_id: str,
    token: Optional[str] = None,
    referer: Optional[str] = None,
    content_type: str = 'application/json',
    accept: str = '*/*',
    accept_language: str = 'zh,zh-CN;q=0.9,en;q=0.8,ja;q=0.7',
    sec_fetch_site: str = 'same-origin'
) -> Dict[str, str]:
    """
    构建通用请求头
    
    Args:
        device_id: 设备ID
        token: 认证token
        referer: Referer头
        content_type: Content-Type
        accept: Accept头
        accept_language: Accept-Language头
        sec_fetch_site: Sec-Fetch-Site头
        
    Returns:
        请求头字典
    """
    
    headers = {
        'accept': accept,
        'accept-language': accept_language,
        'cache-control': 'no-cache',
        'content-type': content_type,
        'origin': BASE_URL_KIIRA,
        'pragma': 'no-cache',
        'priority': 'u=1, i',
        'referer': referer or BASE_URL_KIIRA,
        'sec-fetch-dest': 'empty',
        'sec-fetch-mode': 'cors',
        'sec-fetch-site': sec_fetch_site,
        'user-agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 13_2_3 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/13.0.3 Mobile/15E148 Safari/604.1',
        'x-app-id': 'gen.seagen.app',
        'x-device-id': device_id,
        'x-language': 'en',
        'x-platform': 'web'
    }
    
    if token:
        headers['token'] = token
    
    return headers


def get_session() -> requests.Session:
    """
    获取全局HTTP Session单例
    Session会复用TCP连接,减少握手开销

    Returns:
        requests.Session实例
    """
    global _session
    if _session is None:
        _session = requests.Session()
        # 设置连接池大小
        adapter = requests.adapters.HTTPAdapter(
            pool_connections=10,
            pool_maxsize=20,
            pool_block=False
        )
        _session.mount('http://', adapter)
        _session.mount('https://', adapter)
    return _session


def make_request(
    method: str,
    url: str,
    device_id: str,
    token: Optional[str] = None,
    headers: Optional[Dict[str, str]] = None,
    json_data: Optional[Dict[str, Any]] = None,
    timeout: Optional[Tuple[int, int]] = None,
    **kwargs
) -> Optional[Dict[str, Any]]:
    """
    发送HTTP请求的通用方法
    使用全局Session复用连接,提升性能

    Args:
        method: HTTP方法
        url: 请求URL
        device_id: 设备ID
        token: 认证token
        headers: 自定义请求头（如果提供，将覆盖默认头）
        json_data: JSON数据
        timeout: 超时配置(连接超时,读取超时),默认(3,15)秒
        **kwargs: 其他requests参数

    Returns:
        响应JSON数据，失败返回None
    """
    if headers is None:
        headers = build_headers(device_id=device_id, token=token)

    # 使用默认超时
    if timeout is None:
        timeout = DEFAULT_TIMEOUT

    try:
        session = get_session()
        response = session.request(
            method=method,
            url=url,
            headers=headers,
            json=json_data,
            timeout=timeout,
            **kwargs
        )
        response.raise_for_status()
        return response.json()
    except requests.exceptions.Timeout as e:
        logger.error(f"请求超时 {method} {url}: {e}")
        return None
    except requests.exceptions.RequestException as e:
        logger.error(f"请求失败 {method} {url}: {e}")
        return None
    except json.JSONDecodeError as e:
        logger.error(f"JSON解析失败: {e}")
        return None
    except Exception as e:
        logger.error(f"未知错误: {e}", exc_info=True)
        return None
