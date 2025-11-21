"""
聊天服务：处理聊天完成业务逻辑
"""
import uuid
import json
import time
import os
from typing import Optional, Dict, Any, List, AsyncIterator
from fastapi import HTTPException

from app.services.kiira_client import KiiraAIClient, is_agent_name_match
from app.utils.stream_parser import extract_media_from_data
from app.config import DEFAULT_AGENT_NAME, AGENT_LIST
from app.utils.logger import get_logger

logger = get_logger(__name__)


class ChatService:
    """聊天服务类"""
    
    def __init__(self, device_id: Optional[str] = None, token: Optional[str] = None, group_id: Optional[str] = None):
        """
        初始化聊天服务
        
        Args:
            device_id: 设备ID，如果未提供则自动生成
            token: 认证token，如果未提供则自动登录获取
            group_id: 群组ID，如果未提供则自动查找
        """
        self.device_id = device_id or str(uuid.uuid4())
        self.client = KiiraAIClient(device_id=self.device_id, token=token, group_id=group_id)
        self._initialized = False
    def save_account_info(self):
        """保存账号信息到文件（数组格式）"""
        try:
            account_info = {
                "user_name": self.client.user_name,
                "group_id": self.client.group_id,
                "token": self.client.token
            }
            os.makedirs("data", exist_ok=True)
            account_file = "data/account.json"
            accounts = []
            if os.path.exists(account_file):
                with open(account_file, "r", encoding="utf-8") as f:
                    try:
                        accounts = json.load(f)
                        if not isinstance(accounts, list):
                            accounts = []
                    except Exception:
                        accounts = []
            # 追加当前账号信息
            accounts.append(account_info)
            with open(account_file, "w", encoding="utf-8") as f:
                json.dump(accounts, f, ensure_ascii=False, indent=2)
            
        except Exception as e:
            logger.error(f"写入账号信息失败: {e}")
            pass
    async def _ensure_initialized(self, agent_name: str = DEFAULT_AGENT_NAME):
        """确保客户端已初始化（登录并获取群组）"""
        if self._initialized:
            return
        # 如果没有token，先登录
        if not self.client.token:
            logger.info("正在获取游客Token...")
            if not await self.client.login_guest():
                raise HTTPException(status_code=500, detail="无法获取认证token")
            logger.info("✅ Token获取成功")
        # 获取当前用户信息
        user_info, name = await self.client.get_my_info()
        if user_info:
            self.client.user_name = name
        # 如果没有群组ID，获取群组列表
        if not self.client.group_id:
            logger.info(f"正在获取聊天群组ID ({agent_name})...")
            result = await self.client.get_my_chat_group_list(agent_name=agent_name)
            if not result:
                raise HTTPException(
                    status_code=404,
                    detail=f"无法找到指定的Agent群组: {agent_name}"
                )
        self.save_account_info()
        self._initialized = True
    
    async def _extract_images_from_messages(self, messages: List[Any]) -> List[Dict[str, Any]]:
        """
        从消息中提取图片资源

        Args:
            messages: 消息列表（可以是字典或 Pydantic 模型对象）

        Returns:
            资源列表
        """
        resources = []
        for message in messages:
            # 处理 Pydantic 模型对象或字典
            if hasattr(message, 'content'):
                content = message.content
            elif isinstance(message, dict):
                content = message.get("content", "")
            else:
                continue

            if isinstance(content, str):
                # 检查是否包含图片URL
                if content.startswith(("http://", "https://")):
                    # 尝试上传图片
                    uploaded = await self.client.upload_resource(content)
                    if uploaded:
                        resources.append({
                            "name": uploaded.get('name'),
                            "size": uploaded.get('size'),
                            "url": uploaded.get('url'),
                            "type": "image"
                        })
            elif isinstance(content, list):
                # 处理多模态内容（文本+图片）
                for item in content:
                    if isinstance(item, dict) and item.get("type") == "image_url":
                        image_url = item.get("image_url", {}).get("url", "")
                        if image_url:
                            uploaded = await self.client.upload_resource(image_url)
                            if uploaded:
                                resources.append({
                                    "name": uploaded.get('name'),
                                    "size": uploaded.get('size'),
                                    "url": uploaded.get('url'),
                                    "type": "image"
                                })
        return resources
    
    def _build_prompt_from_messages(self, messages: List[Any]) -> str:
        """
        从消息列表构建提示词
        
        Args:
            messages: 消息列表（可以是字典或 Pydantic 模型对象）
            
        Returns:
            组合后的提示词
        """
        prompt_parts = []
        for msg in messages:
            # 处理 Pydantic 模型对象或字典
            if hasattr(msg, 'role') and hasattr(msg, 'content'):
                role = msg.role
                content = msg.content
            elif isinstance(msg, dict):
                role = msg.get("role", "")
                content = msg.get("content", "")
            else:
                continue
            
            if isinstance(content, str):
                # 如果是字符串，直接使用（但排除纯URL，因为URL会被提取为图片）
                if role == "user" and not content.startswith(("http://", "https://")):
                    prompt_parts.append(content)
                elif role == "assistant":
                    # 可以添加助手回复的上下文
                    pass
            elif isinstance(content, list):
                # 处理多模态内容（文本+图片）
                text_parts = []
                for item in content:
                    if isinstance(item, dict):
                        if item.get("type") == "text":
                            text_parts.append(item.get("text", ""))
                if text_parts:
                    prompt_parts.append(" ".join(text_parts))
        
        return "\n".join(prompt_parts) if prompt_parts else ""
    
    async def chat_completion(
        self,
        messages: List[Any],
        model: str = "",
        agent_name: Optional[str] = None,
        stream: bool = False
    ) -> Dict[str, Any]:
        """
        执行聊天完成

        Args:
            messages: 消息列表
            model: 模型名称，用于响应中的 model 字段
            agent_name: Agent 名称，用于选择聊天群组。
                       如果未指定，将使用 model 参数；
                       如果 model 也为空，则使用默认配置 DEFAULT_AGENT_NAME
            stream: 是否流式返回

        Returns:
            响应数据（流式返回 task_id 等信息，非流式返回完整响应）
        """
        # 确保已初始化：优先使用调用方传入的 agent_name，其次使用 model，最后回退到默认配置
        # 这样设计符合 KISS 原则：简单直观的参数优先级
        # 对空白字符串做显式处理，避免隐式回退导致的行为差异
        name_candidates = [agent_name, model, DEFAULT_AGENT_NAME]
        effective_agent_name = DEFAULT_AGENT_NAME
        for candidate in name_candidates:
            if isinstance(candidate, str) and candidate.strip():
                effective_agent_name = candidate.strip()
                break

        # 记录调试日志，便于问题排查
        logger.debug(
            f"chat_completion: model='{model}', "
            f"agent_name_param='{agent_name}', "
            f"effective_agent_name='{effective_agent_name}'"
        )

        await self._ensure_initialized(agent_name=effective_agent_name)
        # 构建提示词
        prompt = self._build_prompt_from_messages(messages)
        if not prompt:
            raise HTTPException(status_code=400, detail="消息内容不能为空")

        # 提取图片资源
        resources = await self._extract_images_from_messages(messages)

        # 批量创建配置的agent群组（使用模糊匹配）
        if AGENT_LIST:
            agent_list = await self.client.get_agent_list()
            if agent_list and isinstance(agent_list, list):
                for agent in agent_list:
                    label = agent.get("label", "") or ""
                    if not label:
                        continue

                    # 使用模糊匹配判断当前 label 是否属于配置的 AGENT_LIST
                    is_configured = any(
                        is_agent_name_match(label, configured)
                        for configured in AGENT_LIST
                    )

                    if is_configured:
                        account_no = agent.get("account_no")
                        if account_no:
                            # create_chat_group 接口期望的是列表
                            await self.client.create_chat_group([account_no], label)

        # 发送消息
        task_id = await self.client.send_message(
            message=prompt,
            at_account_no=self.client.at_account_no,
            resources=resources if resources else None
        )
        
        if not task_id:
            raise HTTPException(status_code=500, detail="发送消息失败")
        
        if stream:
            # 流式响应在路由中处理
            return {"task_id": task_id, "stream": True, "group_id": self.client.group_id, "token": self.client.token}
        else:
            # 非流式响应：收集所有流式数据后返回
            return await self._collect_stream_response(task_id, model=model)
    
    async def _collect_stream_response(self, task_id: str, model: str = "") -> Dict[str, Any]:
        """
        收集流式响应并转换为完整响应

        Args:
            task_id: 任务ID
            model: 模型名称，用于响应中的 model 字段

        Returns:
            完整的响应数据
        """
        full_content = ""
        media_url = None
        media_type = None
        sa_resources: List[Dict[str, Any]] = []

        async for line in self.client.stream_chat_completions(task_id):
            # 只处理 SSE data 行，其它行直接跳过
            if not line or not line.startswith("data: "):
                continue

            json_str = line[6:].strip()
            # 处理结束标记
            if not json_str or json_str == "[DONE]":
                break

            try:
                json_data = json.loads(json_str)

                # 提取媒体资源（图片/视频）
                parsed_result = extract_media_from_data(json_data)
                if parsed_result:
                    parsed_url, parsed_type = parsed_result
                    media_url = parsed_url
                    media_type = parsed_type

                    # 保留上游返回的 sa_resources 结构，方便调用方自定义渲染
                    # 兼容 sa_resources 在 choice 层级和 delta 层级的两种情况
                    choices_data = json_data.get("choices", [])
                    if choices_data and isinstance(choices_data, list):
                        first_choice = choices_data[0]
                        if isinstance(first_choice, dict):
                            collected_resources: List[Dict[str, Any]] = []

                            # 1. 收集 choice 层级的 sa_resources
                            top_level_resources = first_choice.get("sa_resources")
                            if isinstance(top_level_resources, list):
                                collected_resources.extend(top_level_resources)

                            # 2. 收集 delta 层级的 sa_resources
                            delta = first_choice.get("delta")
                            if isinstance(delta, dict):
                                delta_resources = delta.get("sa_resources")
                                if isinstance(delta_resources, list):
                                    collected_resources.extend(delta_resources)

                            # 3. 合并到总资源列表
                            if collected_resources:
                                sa_resources.extend(collected_resources)

                # 提取文本内容（优先从 delta，其次从 message）
                choices = json_data.get("choices", [])
                if choices and isinstance(choices, list):
                    choice = choices[0]
                    if isinstance(choice, dict):
                        delta = choice.get("delta", {})
                        content = delta.get("content", "") if isinstance(delta, dict) else ""

                        if not content:
                            message = choice.get("message", {})
                            content = message.get("content", "") if isinstance(message, dict) else ""

                        if content:
                            full_content += content
            except json.JSONDecodeError:
                # 记录解析失败的行，方便排查问题
                logger.debug(f"JSON 解析失败, task_id={task_id}, line={json_str[:200]}")
                continue
            except Exception as e:
                logger.error(f"解析响应数据异常, task_id={task_id}: {e}", exc_info=True)
                continue

        # 结果有效性校验：既没有文本也没有媒体时认为是异常
        if not full_content and not sa_resources and not media_url:
            logger.error(f"流式响应为空, task_id={task_id}")
            raise HTTPException(status_code=500, detail="流式响应为空或解析失败")

        # 在文本末尾追加媒体 Markdown，与流式模式保持一致
        if media_url:
            if media_type == "image":
                full_content += f"\n\n![Generated Image]({media_url})\n\n"
            elif media_type == "video":
                full_content += f"\n\n生成视频完成.\n[点击下载视频]({media_url})\n\n"
            else:
                full_content += f"\n\n{media_url}\n\n"

        # 构建 OpenAI 格式的响应
        response_id = f"chatcmpl-{task_id}"
        created = int(time.time())

        message_payload: Dict[str, Any] = {
            "role": "assistant",
            "content": full_content
        }

        # 添加结构化媒体字段，便于前端自定义渲染
        if sa_resources:
            message_payload["sa_resources"] = sa_resources

        choices = [{
            "index": 0,
            "message": message_payload,
            "finish_reason": "stop"
        }]

        response_model = model or "sora-2"

        return {
            "id": response_id,
            "object": "chat.completion",
            "created": created,
            "model": response_model,
            "choices": choices,
            "usage": {
                "prompt_tokens": len(full_content.split()) if full_content else 0,
                "completion_tokens": len(full_content.split()) if full_content else 0,
                "total_tokens": len(full_content.split()) * 2 if full_content else 0
            }
        }
    
    async def stream_chat_completion(self, task_id: str) -> AsyncIterator[str]:
        """
        流式返回聊天响应

        Args:
            task_id: 任务ID

        Yields:
            SSE格式的响应行
        """
        async for line in self.client.stream_chat_completions(task_id):
            yield line
