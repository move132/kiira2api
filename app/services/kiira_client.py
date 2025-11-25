"""
Kiira AI 客户端服务
"""
import uuid
import time
import re
from difflib import SequenceMatcher
from pathlib import Path
from typing import Optional, Dict, Any, AsyncIterator, List
from dataclasses import dataclass, field

from app.config import (
    BASE_URL_KIIRA,
    BASE_URL_SEAART_API,
    BASE_URL_SEAART_UPLOADER,
    DEFAULT_AGENT_NAME
)
from app.utils.http_client import build_headers, make_async_request, get_async_client
from app.utils.file_utils import (
    get_image_data_and_type_async,
    get_file_extension_from_content_type
)
from app.utils.logger import get_logger

logger = get_logger(__name__)

# ============================================================================
# Agent 名称模糊匹配配置
# ============================================================================
# 名称相似度阈值（0~1），低于该值视为不匹配
# 建议值：0.7 可以容忍约30%的差异（如增加emoji、后缀等）
AGENT_NAME_SIMILARITY_THRESHOLD = 0.7

# Agent 列表缓存时间（秒），避免频繁请求
# 仅对默认参数（无分类、无关键词）的调用生效
AGENT_LIST_CACHE_TTL_SECONDS = 60


def normalize_agent_name(name: str) -> str:
    """
    标准化 Agent 名称，便于模糊匹配

    处理步骤：
    1. 去除首尾空格
    2. 转为小写（忽略大小写差异）
    3. 移除特殊符号和emoji，仅保留数字、字母和常见中文

    Args:
        name: 原始Agent名称

    Returns:
        标准化后的名称（仅包含数字、字母、中文）

    Examples:
        >>> normalize_agent_name("Nano Banana Pro🔥")
        'nanobananapro'
        >>> normalize_agent_name("换装游戏 v2.0")
        '换装游戏v20'
    """
    if not isinstance(name, str):
        return ""
    name = name.strip().lower()
    # 保留数字、字母和常见中文，移除其他字符（空格、标点、emoji等）
    return re.sub(r"[^0-9a-z\u4e00-\u9fff]+", "", name)


def get_agent_name_similarity(a: str, b: str) -> float:
    """
    计算两个 Agent 名称之间的相似度

    算法策略：
    1. 先对名称进行标准化处理
    2. 使用 SequenceMatcher 计算基础相似度
    3. 对"包含关系"进行加权（认为是增加后缀/前缀的情况）

    Args:
        a: 第一个Agent名称
        b: 第二个Agent名称

    Returns:
        相似度分数（0~1），1表示完全相同

    Examples:
        >>> get_agent_name_similarity("Nano Banana", "nano banana pro")
        0.9  # 包含关系，高相似度
        >>> get_agent_name_similarity("Agent A", "Agent B")
        0.83  # 部分相同（实际值，会根据SequenceMatcher算法计算）
        >>> get_agent_name_similarity("Agent A", "Agent Z")
        0.67  # 相似度较低
    """
    na = normalize_agent_name(a)
    nb = normalize_agent_name(b)

    if not na or not nb:
        return 0.0

    if na == nb:
        return 1.0

    # 使用 SequenceMatcher 计算基础相似度
    base_similarity = SequenceMatcher(None, na, nb).ratio()

    # 如果标准化后存在包含关系，认为是非常接近的名称
    # 例如："nanobananapro" 包含在 "nanobananapromax" 中
    if na in nb or nb in na:
        # 提升相似度到至少0.9，但不会低于原始相似度
        return max(base_similarity, 0.9)

    return base_similarity


def is_agent_name_match(
    a: str,
    b: str,
    threshold: float = AGENT_NAME_SIMILARITY_THRESHOLD
) -> bool:
    """
    判断两个 Agent 名称是否"足够相似"以视为匹配

    匹配优先级（从高到低）：
    1. 完全相等（精确匹配）
    2. 忽略大小写相等
    3. 标准化后相似度达到阈值（包含关系会被提升相似度）

    Args:
        a: 第一个Agent名称
        b: 第二个Agent名称
        threshold: 相似度阈值，默认使用全局配置

    Returns:
        是否匹配

    Examples:
        >>> is_agent_name_match("Nano Banana Pro🔥", "nano banana pro")
        True  # 标准化后相同
        >>> is_agent_name_match("Agent A", "Agent B", threshold=0.7)
        True  # 相似度约0.83，达到阈值0.7
        >>> is_agent_name_match("Agent A", "Agent Z", threshold=0.7)
        False  # 相似度约0.67，低于阈值0.7
    """
    if not a or not b:
        return False

    # 优先级1：完全相等
    if a == b:
        return True

    # 优先级2：忽略大小写相等
    if a.lower() == b.lower():
        return True

    # 优先级3：基于相似度判断
    similarity = get_agent_name_similarity(a, b)
    return similarity >= threshold

@dataclass
class KiiraAIClient:
    """Kiira AI API 客户端类"""

    device_id: str
    token: Optional[str] = None
    group_id: Optional[str] = None
    at_account_no: Optional[str] = None
    user_name: Optional[str] = None

    # Agent 列表缓存，仅对默认参数调用生效，用于减少频繁接口访问
    # 使用 field(init=False, repr=False) 避免出现在构造函数和日志中
    _agent_list_cache: Optional[List[Dict[str, Any]]] = field(
        default=None, init=False, repr=False
    )
    _agent_list_cache_time: Optional[float] = field(
        default=None, init=False, repr=False
    )
    
    def __post_init__(self):
        """初始化后自动生成设备ID（如果未提供）"""
        if not self.device_id:
            self.device_id = str(uuid.uuid4())
    
    async def login_guest(self) -> Optional[str]:
        """游客登录，获取 token"""
        url = f'{BASE_URL_SEAART_API}/api/v1/login-guest'
        headers = build_headers(
            device_id=self.device_id,
            token='',
            referer=f'{BASE_URL_KIIRA}/',
            sec_fetch_site='cross-site'
        )

        response_data = await make_async_request('POST', url, device_id=self.device_id, headers=headers, json_data={})
        if response_data and 'data' in response_data and 'token' in response_data['data']:
            self.token = response_data['data']['token']
            logger.info(f"获取到游客Token: {self.token[:20]}...")
            return self.token
        else:
            logger.error("登录失败：未获取到token")
            return None
    
    async def get_my_info(self) -> Optional[tuple[Dict[str, Any], str]]:
        """获取当前用户信息"""
        url = f'{BASE_URL_KIIRA}/api/v1/my'
        headers = build_headers(device_id=self.device_id, token=self.token, referer=f'{BASE_URL_KIIRA}/chat')

        response_data = await make_async_request('POST', url, device_id=self.device_id, token=self.token, headers=headers, json_data={})
        if response_data and 'data' in response_data:
            name = response_data.get('data', {}).get('name', '')
            logger.info(f"当前用户信息：{name}")
            return response_data, name
        return None, None
    
    async def get_my_chat_group_list(self, agent_name: str = DEFAULT_AGENT_NAME) -> Optional[tuple[str, str]]:
        """
        获取当前账户的聊天群组列表，查找指定Agent的群组

        支持智能匹配策略（三级回退）：
        1. 精确匹配：在现有群组中查找完全相同的nickname
        2. 模糊匹配：在现有群组中查找相似度达标的nickname
        3. 创建群组：从agent列表中查找相似Agent并创建新群组

        Args:
            agent_name: 目标Agent名称

        Returns:
            (group_id, at_account_no) 元组，失败返回 None
        """
        url = f'{BASE_URL_KIIRA}/api/v1/my-chat-group-list'
        headers = build_headers(device_id=self.device_id, token=self.token, accept_language='eh')
        data = {"page": 1, "page_size": 999}
        response_data = await make_async_request(
            'POST', url,
            device_id=self.device_id,
            token=self.token,
            headers=headers,
            json_data=data
        )

        if not response_data or 'data' not in response_data:
            logger.warning("未在响应中找到群组数据")
            return None

        items = response_data.get('data', {}).get('items', [])

        # ========================================================================
        # 策略1：精确匹配（优先级最高，保持向后兼容）
        # ========================================================================
        for item in items:
            user_list = item.get('user_list', [])
            for user in user_list:
                if user.get('nickname') == agent_name:
                    group_id = item.get('id')
                    at_account_no = user.get('account_no')
                    logger.info(
                        f"✅ 找到群组 (精确匹配): "
                        f"group_id={group_id}, "
                        f"at_account_no={at_account_no}, "
                        f"nickname='{agent_name}'"
                    )
                    self.group_id = group_id
                    self.at_account_no = at_account_no
                    return group_id, at_account_no

        # ========================================================================
        # 策略2：模糊匹配现有群组
        # ========================================================================
        best_match = None
        best_score = 0.0

        for item in items:
            user_list = item.get('user_list', [])
            for user in user_list:
                nickname = user.get('nickname') or ""
                if not nickname:
                    continue

                similarity = get_agent_name_similarity(agent_name, nickname)
                if similarity > best_score:
                    best_score = similarity
                    best_match = (item, user, nickname)

        if best_match and best_score >= AGENT_NAME_SIMILARITY_THRESHOLD:
            item, user, nickname = best_match
            group_id = item.get('id')
            at_account_no = user.get('account_no')
            logger.info(
                f"✅ 找到群组 (模糊匹配): "
                f"group_id={group_id}, "
                f"at_account_no={at_account_no}, "
                f"target='{agent_name}', "
                f"matched='{nickname}', "
                f"similarity={best_score:.2f}"
            )
            self.group_id = group_id
            self.at_account_no = at_account_no
            return group_id, at_account_no

        # ========================================================================
        # 策略3：从agent列表中查找并创建新群组
        # ========================================================================
        logger.warning(
            f"未在现有群组中找到 '{agent_name}'，"
            f"正在尝试从agent列表中查找并创建新群组"
        )

        agent_list = await self.get_agent_list()
        if not agent_list or not isinstance(agent_list, list):
            logger.error("获取agent列表失败，无法创建群组")
            return None

        # 在agent列表中查找最佳匹配
        best_agent = None
        best_agent_score = 0.0

        for agent in agent_list:
            label = agent.get("label", "") or ""
            if not label:
                continue

            similarity = get_agent_name_similarity(agent_name, label)
            if similarity > best_agent_score:
                best_agent_score = similarity
                best_agent = agent

        if best_agent and best_agent_score >= AGENT_NAME_SIMILARITY_THRESHOLD:
            label = best_agent.get("label", "")
            account_no_base = best_agent.get("account_no")

            if account_no_base:
                logger.info(
                    f"📝 准备创建群组: "
                    f"target='{agent_name}', "
                    f"matched_label='{label}', "
                    f"similarity={best_agent_score:.2f}"
                )

                group_info = await self.create_chat_group([account_no_base], label)
                if group_info:
                    group_id = group_info.get("id")
                    user_list = group_info.get("user_list") or []

                    # 安全地获取 at_account_no
                    if user_list and isinstance(user_list, list) and len(user_list) > 0:
                        at_account_no = user_list[0].get("account_no") or account_no_base
                    else:
                        at_account_no = account_no_base

                    logger.info(
                        f"✅ 群组创建成功: "
                        f"group_id={group_id}, "
                        f"at_account_no={at_account_no}"
                    )
                    self.group_id = group_id
                    self.at_account_no = at_account_no
                    return group_id, at_account_no
                else:
                    logger.error(f"创建群组失败: label='{label}'")
            else:
                logger.error(f"Agent缺少account_no: {best_agent}")

        # 所有策略都失败
        logger.warning(
            f"❌ 未找到可用的Agent来匹配 '{agent_name}'，请检查配置或稍后重试"
        )
        return None
    
    async def get_agent_list(
        self,
        category_ids: Optional[list[str]] = None,
        keyword: str = ""
    ) -> Optional[List[Dict[str, Any]]]:
        """
        获取所有 agent(代理) 列表

        支持缓存机制：
        - 仅对默认参数（无分类、无关键词）的调用启用缓存
        - 缓存有效期由 AGENT_LIST_CACHE_TTL_SECONDS 控制
        - 避免频繁请求API，提高性能

        Args:
            category_ids (Optional[list[str]], optional): 分类ID列表，默认 None
            keyword (str, optional): 搜索关键词，默认空字符串

        Returns:
            Optional[List[Dict[str, Any]]]: Agent列表（仅包含部分字段）
        """
        # 处理可变默认值
        if category_ids is None:
            category_ids = []

        # 仅对默认参数调用使用缓存，确保语义明确
        use_cache = not category_ids and not keyword
        now = time.time()

        # 检查缓存是否有效
        if use_cache and self._agent_list_cache is not None and self._agent_list_cache_time:
            cache_age = now - self._agent_list_cache_time
            if cache_age < AGENT_LIST_CACHE_TTL_SECONDS:
                logger.debug(
                    f"命中agent列表缓存 (已缓存 {cache_age:.1f}秒, "
                    f"TTL {AGENT_LIST_CACHE_TTL_SECONDS}秒)"
                )
                return self._agent_list_cache

        # 缓存未命中或已过期，发起请求
        url = f"{BASE_URL_KIIRA}/api/v1/agent-list"
        headers = build_headers(
            device_id=self.device_id,
            token=self.token,
            accept_language='zh,zh-CN;q=0.9,en;q=0.8,ja;q=0.7',
            referer=f'{BASE_URL_KIIRA}/search'
        )

        data = {
            "category_ids": category_ids,
            "keyword": keyword
        }

        response_data = await make_async_request(
            'POST',
            url,
            device_id=self.device_id,
            token=self.token,
            headers=headers,
            json_data=data
        )

        if response_data and 'data' in response_data:
            # 提取关键字段，减少内存占用
            items = response_data['data']['items']
            filtered_items = []
            for item in items:
                filtered_items.append({
                    "id": item.get("id"),
                    "label": item.get("label"),
                    "account_no": item.get("account_no"),
                    "description": item.get("description"),
                })

            # 更新缓存（仅默认参数场景）
            if use_cache:
                self._agent_list_cache = filtered_items
                self._agent_list_cache_time = now
                logger.debug(f"已缓存agent列表 (共 {len(filtered_items)} 个agent)")

            return filtered_items

        logger.error(f"获取 agent 列表失败，响应: {response_data}")
        return None

    async def create_chat_group(self, agent_account_nos: list[str], label: str) -> Optional[Dict[str, Any]]:
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

        response_data = await make_async_request(
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

    async def _get_upload_presign(
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

        return await make_async_request('POST', url, device_id=self.device_id, token=self.token, headers=headers, json_data=data)

    async def _upload_complete(self, resource_id: str) -> Optional[Dict[str, Any]]:
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
        return await make_async_request('POST', url, device_id=self.device_id, token=self.token, headers=headers, json_data=data)

    async def upload_resource(self, image_path: str) -> Optional[Dict[str, Any]]:
        """
        上传文件资源，自动处理预签名、上传和完成步骤。
        支持本地文件、URL 及 base64 字符串。

        Args:
            image_path: 本地文件路径、图片 URL 或 base64 字符串。

        Returns:
            包含 'name', 'size', 'url', 'path' 的字典，失败返回 None。
        """
        # 1. 解析文件数据和类型（使用异步版本，避免阻塞事件循环）
        initial_file_name = Path(image_path).name if not (image_path.startswith("http") or image_path.startswith("data:")) else "upload.jpg"
        put_data, content_type = await get_image_data_and_type_async(image_path, initial_file_name)

        if not put_data or not content_type:
            logger.error("无法获取图片数据和类型，上传失败")
            return None

        file_size = len(put_data)
        # 根据实际 content_type 调整 file_name 扩展名
        base_name = Path(initial_file_name).stem
        file_name = base_name + get_file_extension_from_content_type(content_type)
        resource_id = str(int(time.time() * 1000))  # 毫秒时间戳作为 resource_id

        # 2. 请求预签名 URL
        logger.debug(f"Step 1: 正在请求预签名 URL (Size: {file_size} bytes, Type: {content_type})...")
        presign_response = await self._get_upload_presign(
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

        logger.debug(f"✅ 预签名响应成功, 资源ID {resource_ret_id}")

        # 3. 直传图片到 GCS
        logger.debug("Step 2: 正在直传图片到 GCS...")

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
            client = await get_async_client()
            put_resp = await client.put(
                upload_url,
                headers=upload_headers,
                content=put_data,
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
        logger.debug(f"Step 3: 正在调用 complete 接口获取最终图片地址...")
        complete_data = await self._upload_complete(resource_ret_id)

        if complete_data and complete_data.get("status", {}).get("code") == 10000:
            image_data = complete_data.get("data", {})
            image_path_ret = image_data.get("path")
            image_url = image_data.get("url")
            if image_url:
                logger.info(f"✅ 资源上传成功: {file_name} ({file_size} bytes)")
                return {"name": file_name, "size": file_size, "url": image_url, "path": image_path_ret, "id": resource_id}
            else:
                logger.warning("⚠️ 未在响应中找到图片URL")
        else:
            logger.error(f"⚠️ Complete 接口返回错误: {complete_data}")
            
        return None

    async def send_message(
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
        response_data = await make_async_request('POST', url, device_id=self.device_id, token=self.token, headers=headers, json_data=data)
        if response_data and 'data' in response_data:
            data_field = response_data['data']
            # 处理 data 字段可能是列表或字典的情况
            if isinstance(data_field, list):
                # 如果是列表，取第一个元素
                if data_field and isinstance(data_field[0], dict):
                    task_id = data_field[0].get('task_id')
                else:
                    logger.error(f"发送消息失败：data 字段为空列表或格式错误: {data_field}")
                    return None
            elif isinstance(data_field, dict):
                # 如果是字典，直接获取
                task_id = data_field.get('task_id')
            else:
                logger.error(f"发送消息失败：data 字段类型错误: {type(data_field)}")
                return None

            if task_id:
                logger.info(f"消息发送成功，task_id: {task_id}")
                return task_id

        logger.error("发送消息失败：未获取到task_id")
        return None
    
    async def stream_chat_completions(
        self,
        task_id: str,
        timeout: int = 180
    ) -> AsyncIterator[str]:
        """实时流式获取AI聊天响应"""
        from app.utils.http_client import stream_async_request

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
            logger.debug("开始接收异步流式数据...")

            line_count = 0
            has_data = False

            async for line in stream_async_request(
                method='POST',
                url=url,
                device_id=self.device_id,
                token=self.token,
                headers=headers,
                json_data=data,
                timeout=timeout
            ):
                line_count += 1
                if line:
                    has_data = True
                    if line_count == 1:
                        logger.debug("✅ 收到第一行数据")

                    # 跳过注释行和空行
                    if not line.startswith(":"):
                        yield line
                elif line_count == 1:
                    logger.warning("⚠ 第一行是空行，继续等待...")

            if not has_data:
                logger.warning("⚠ 警告：没有收到任何数据")
            else:
                logger.debug(f"✅ 异步流式响应接收完成，共处理 {line_count} 行")

        except Exception as e:
            logger.error(f"stream_chat_completions 错误: {e}", exc_info=True)
