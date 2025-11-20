"""
Kiira AI 客户端服务
"""
import uuid
import time
import requests
from pathlib import Path
from typing import Optional, Dict, Any, Iterator, List
from dataclasses import dataclass

from app.config import (
    BASE_URL_KIIRA,
    BASE_URL_SEAART_API,
    BASE_URL_SEAART_UPLOADER,
    DEFAULT_AGENT_NAME
)
from app.utils.http_client import build_headers, make_request
from app.utils.file_utils import (
    get_image_data_and_type,
    get_file_extension_from_content_type
)
from app.utils.logger import get_logger

logger = get_logger(__name__)

@dataclass
class KiiraAIClient:
    """Kiira AI API 客户端类"""
    
    device_id: str
    token: Optional[str] = None
    group_id: Optional[str] = None
    at_account_no: Optional[str] = None
    user_name: Optional[str] = None
    
    def __post_init__(self):
        """初始化后自动生成设备ID（如果未提供）"""
        if not self.device_id:
            self.device_id = str(uuid.uuid4())
    
    def login_guest(self) -> Optional[str]:
        """游客登录，获取 token"""
        url = f'{BASE_URL_SEAART_API}/api/v1/login-guest'
        headers = build_headers(
            device_id=self.device_id,
            token='',
            referer=f'{BASE_URL_KIIRA}/',
            sec_fetch_site='cross-site'
        )
        
        response_data = make_request('POST', url, device_id=self.device_id, headers=headers, json_data={})
        if response_data and 'data' in response_data and 'token' in response_data['data']:
            self.token = response_data['data']['token']
            logger.info(f"获取到游客Token: {self.token[:20]}...")
            return self.token
        else:
            logger.error("登录失败：未获取到token")
            return None
    
    def get_my_info(self) -> Optional[tuple[Dict[str, Any], str]]:
        """获取当前用户信息"""
        url = f'{BASE_URL_KIIRA}/api/v1/my'
        headers = build_headers(device_id=self.device_id, token=self.token, referer=f'{BASE_URL_KIIRA}/chat')
        
        response_data = make_request('POST', url, device_id=self.device_id, token=self.token, headers=headers, json_data={})
        if response_data and 'data' in response_data:
            name = response_data.get('data', {}).get('name', '')
            logger.info(f"当前用户信息：{name}")
            return response_data, name
        return None, None
    
    def get_my_chat_group_list(self, agent_name: str = DEFAULT_AGENT_NAME) -> Optional[tuple[str, str]]:
        """获取当前账户的聊天群组列表，查找指定昵称的群组"""
        url = f'{BASE_URL_KIIRA}/api/v1/my-chat-group-list'
        headers = build_headers(device_id=self.device_id, token=self.token, accept_language='eh')
        data = {"page": 1, "page_size": 999}
        response_data = make_request('POST', url, device_id=self.device_id, token=self.token, headers=headers, json_data=data)

        # logger.info(f"获取当前账户的聊天群组列表，查找指定昵称的群组，响应数据: {response_data}")
        if not response_data or 'data' not in response_data:
            logger.warning("未在响应中找到群组数据")
            return None
        
        items = response_data.get('data', {}).get('items', [])
        for item in items:
            user_list = item.get('user_list', [])
            for user in user_list:
                if user.get('nickname') == agent_name:
                    group_id = item.get('id')
                    at_account_no = user.get('account_no')
                    logger.info(f"✅ 找到群组ID: {group_id}, at_account_no: {at_account_no}")
                    self.group_id = group_id
                    self.at_account_no = at_account_no
                    return group_id, at_account_no
        
        logger.warning(f"未在 user_list 中找到 '{agent_name}'")
        return None
    
    def get_agent_list(self, category_ids: list[str] = [], keyword: str = "") -> Optional[Dict[str, Any]]:
        """
        获取所有 agent(代理) 列表

        Args:
            category_ids (list[str], optional): 分类ID列表，默认 []
            keyword (str, optional): 搜索关键词, 默认空字符串

        Returns:
            Optional[Dict[str, Any]]: 响应数据
        """
        url = f"{BASE_URL_KIIRA}/api/v1/agent-list"
        headers = build_headers(
            device_id=self.device_id,
            token=self.token,
            accept_language='zh,zh-CN;q=0.9,en;q=0.8,ja;q=0.7',
            referer=f'{BASE_URL_KIIRA}/search'
        )
        # curl 的 body 是 {"category_ids":[],"keyword":""}
        data = {
            "category_ids": category_ids,
            "keyword": keyword
        }
        response_data = make_request(
            'POST',
            url,
            device_id=self.device_id,
            token=self.token,
            headers=headers,
            json_data=data
        )
        if response_data and 'data' in response_data:
            # 只返回指定字段
            items = response_data['data']['items']
            filtered_items = []
            for item in items:
                filtered_items.append({
                    "id": item.get("id"),
                    "label": item.get("label"),
                    "account_no": item.get("account_no"),
                    "description": item.get("description"),
                })
            # logger.info(f"获取 agent 列表成功，响应: {filtered_items}")
            return filtered_items
        logger.error(f"获取 agent 列表失败，响应: {response_data}")
        return None

    def create_chat_group(self, agent_account_nos: list[str], label: str) -> Optional[Dict[str, Any]]:
        """
        创建新的聊天群组

        Args:
            agent_account_nos (list[str]): 代理账户编号列表

        Returns:
            Optional[Dict[str, Any]]: 响应数据
        """
        url = f"{BASE_URL_KIIRA}/api/v1/create-chat-group"
        headers = build_headers(
            device_id=self.device_id,
            token=self.token,
            accept_language='zh,zh-CN;q=0.9,en;q=0.8,ja;q=0.7',
            referer=f'{BASE_URL_KIIRA}/search'
        )

        data = {
            "agent_account_nos": agent_account_nos
        }

        response_data = make_request(
            'POST',
            url,
            device_id=self.device_id,
            token=self.token,
            headers=headers,
            json_data=data
        )
        if response_data and 'data' in response_data:
            logger.info(f"✅添加聊天群组{label}成功")
            return response_data['data']
        logger.error(f"添加聊天群组{label}失败，响应: {response_data}")
        return None

    def _get_upload_presign(
        self,
        resource_id: str,
        file_name: str,
        file_size: int,
        category: int = 74,
        content_type: str = 'image/jpeg'
    ) -> Optional[Dict[str, Any]]:
        """获取图片上传的 presign 信息（内部方法）"""
        url = f"{BASE_URL_SEAART_UPLOADER}/api/upload/pre-sign"
        headers = build_headers(
            device_id=self.device_id,
            token=self.token,
            referer=f'{BASE_URL_KIIRA}/',
            accept_language='zh',
            sec_fetch_site='cross-site'
        )
        
        data = {
            "id": resource_id,
            "category": category,
            "content_type": content_type,
            "file_name": file_name,
            "file_size": file_size,
            "name": file_name,
            "size": file_size
        }
        
        return make_request('POST', url, device_id=self.device_id, token=self.token, headers=headers, json_data=data)
    
    def _upload_complete(self, resource_id: str) -> Optional[Dict[str, Any]]:
        """通知 seaart.dev 上传已完成（内部方法）"""
        url = f"{BASE_URL_SEAART_UPLOADER}/api/upload/complete"
        headers = build_headers(
            device_id=self.device_id,
            token=self.token,
            referer=f'{BASE_URL_KIIRA}/',
            accept_language='zh',
            sec_fetch_site='cross-site'
        )
        
        data = {"id": resource_id}
        return make_request('POST', url, device_id=self.device_id, token=self.token, headers=headers, json_data=data)

    def upload_resource(self, image_path: str) -> Optional[Dict[str, Any]]:
        """
        上传文件资源，自动处理预签名、上传和完成步骤。
        支持本地文件、URL 及 base64 字符串。
        
        Args:
            image_path: 本地文件路径、图片 URL 或 base64 字符串。
            
        Returns:
            包含 'name', 'size', 'url', 'path' 的字典，失败返回 None。
        """
        # 1. 解析文件数据和类型
        initial_file_name = Path(image_path).name if not (image_path.startswith("http") or image_path.startswith("data:")) else "upload.jpg"
        put_data, content_type = get_image_data_and_type(image_path, initial_file_name)

        if not put_data or not content_type:
            logger.error("无法获取图片数据和类型，上传失败")
            return None
        
        file_size = len(put_data)
        # 根据实际 content_type 调整 file_name 扩展名
        base_name = Path(initial_file_name).stem
        file_name = base_name + get_file_extension_from_content_type(content_type)
        resource_id = str(int(time.time() * 1000))  # 毫秒时间戳作为 resource_id

        # 2. 请求预签名 URL
        logger.info(f"Step 1: 正在请求预签名 URL (Size: {file_size} bytes, Type: {content_type})...")
        presign_response = self._get_upload_presign(
            resource_id=resource_id,
            file_name=file_name,
            file_size=file_size,
            content_type=content_type
        )
        
        if not presign_response or 'data' not in presign_response:
            logger.error("预签名请求失败或响应格式错误")
            return None

        presign_data = presign_response.get("data", {})
        pre_signs = presign_data.get("pre_signs", [])
        resource_ret_id = presign_data.get("id")
        upload_url = (pre_signs[0].get("url") if pre_signs and isinstance(pre_signs, list) else None)
        
        if not upload_url:
            logger.error(f"没有拿到预签名 URL，响应: {presign_response}")
            return None
        
        logger.info(f"✅ 预签名响应成功, 资源ID {resource_ret_id}")

        # 3. 直传图片到 GCS
        logger.info("Step 2: 正在直传图片到 GCS...")
        
        # 检查预签名响应中是否有指定的 headers
        presign_headers = {}
        if pre_signs and isinstance(pre_signs, list) and len(pre_signs) > 0 and "headers" in pre_signs[0]:
            presign_headers.update(pre_signs[0]["headers"])
            
        # 实际上传 headers - 使用最少的必要 headers，避免干扰 GCS 签名验证
        upload_headers = {
            "Content-Type": content_type,
            "Content-Length": str(file_size),
        }
        upload_headers.update(presign_headers)  # 合并预签名指定的 headers
        
        try:
            put_resp = requests.put(
                upload_url,
                headers=upload_headers,
                data=put_data,
                timeout=60
            )
            if put_resp.status_code == 200:
                logger.info("✅ 上传成功！")
            else:
                logger.error(f"上传失败，状态码：{put_resp.status_code}，响应：{put_resp.text[:200]}")
                return None
        except Exception as e:
            logger.error(f"上传失败：{e}")
            return None

        # 4. 调用 complete 接口获取最终图片地址
        logger.info(f"Step 3: 正在调用 complete 接口获取最终图片地址...")
        complete_data = self._upload_complete(resource_ret_id)

        if complete_data and complete_data.get("status", {}).get("code") == 10000:
            image_data = complete_data.get("data", {})
            image_path_ret = image_data.get("path")
            image_url = image_data.get("url")
            if image_url:
                logger.info(f"✅ Complete 成功，最终 URL: {image_url}")
                return {"name": file_name, "size": file_size, "url": image_url, "path": image_path_ret, "id": resource_id}
            else:
                logger.warning("⚠️ 未在响应中找到图片URL")
        else:
            logger.error(f"⚠️ Complete 接口返回错误: {complete_data}")
            
        return None

    def send_message(
        self,
        message: str,
        at_account_no: str = 'seagen_sora2_agent',
        agent_type: str = "agent",
        at_account_no_type: str = "bot",
        resources: Optional[List[Dict[str, Any]]] = None,
        message_id: Optional[str] = None
    ) -> Optional[str]:
        """向群组发送消息"""
        if not self.group_id:
            logger.error("未设置群组ID，请先调用 get_my_chat_group_list()")
            return None
        
        url = f'{BASE_URL_KIIRA}/api/v1/send-message'
        headers = build_headers(device_id=self.device_id, token=self.token, accept_language='zh')
        
        if resources is None:
            resources = []
        
        if message_id is None:
            # 使用 uuid1().int 的前17位作为消息ID
            message_id = str(uuid.uuid1().int)[:17]
        
        data = {
            "id": message_id,
            "at_account_no": at_account_no,
            "at_account_no_type": at_account_no_type,
            "resources": resources,
            "group_id": self.group_id,
            "message": message,
            "agent_type": agent_type
        }
        logger.info(f"发送消息: {data}")
        response_data = make_request('POST', url, device_id=self.device_id, token=self.token, headers=headers, json_data=data)
        if response_data and 'data' in response_data:
            task_id = response_data['data'].get('task_id')
            if task_id:
                logger.info(f"消息发送成功，task_id: {task_id}")
                return task_id
        
        logger.error("发送消息失败：未获取到task_id")
        return None
    
    def stream_chat_completions(
        self,
        task_id: str,
        timeout: int = 180
    ) -> Iterator[str]:
        """实时流式获取AI聊天响应"""
        url = f'{BASE_URL_KIIRA}/api/v1/stream/chat/completions'
        headers = build_headers(
            device_id=self.device_id,
            token=self.token,
            accept='text/event-stream',
            accept_language='zh'
        )
        
        data = {"message_id": task_id}
        
        try:
            logger.info(f"开始请求流式响应，task_id: {task_id}")
            response = requests.post(
                url,
                headers=headers,
                json=data,
                cookies={},
                stream=True,
                timeout=timeout
            )
            
            logger.info(f"收到响应，状态码: {response.status_code}")
            if response.status_code != 200:
                logger.error(f"流式响应状态码错误: {response.status_code}")
                logger.error(f"响应内容: {response.text[:500]}")
                return
            
            response.encoding = 'utf-8'
            logger.info("开始接收流式数据...")
            
            line_count = 0
            has_data = False
            for line in response.iter_lines(decode_unicode=True):
                line_count += 1
                if line:
                    has_data = True
                    if line_count == 1:
                        logger.info("✅ 收到第一行数据")
                    
                    if isinstance(line, bytes):
                        line = line.decode('utf-8')
                    
                    # 跳过注释行和空行
                    if not line.startswith(":"):
                        yield line
                elif line_count == 1:
                    logger.warning("⚠ 第一行是空行，继续等待...")
            
            if not has_data:
                logger.warning("⚠ 警告：没有收到任何数据")
            else:
                logger.info(f"✅ 流式响应接收完成，共处理 {line_count} 行")
                
        except requests.exceptions.RequestException as e:
            logger.error(f"stream_chat_completions 网络错误: {e}")
        except Exception as e:
            logger.error(f"stream_chat_completions 错误: {e}", exc_info=True)
