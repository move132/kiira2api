"""
聊天服务：处理聊天完成业务逻辑
"""
import uuid
import json
import time
import os
from typing import Optional, Dict, Any, List, Iterator
from fastapi import HTTPException

from app.services.kiira_client import KiiraAIClient
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
            if not self.client.login_guest():
                raise HTTPException(status_code=500, detail="无法获取认证token")
            logger.info("✅ Token获取成功")
        # 获取当前用户信息
        user_info, name = self.client.get_my_info()
        if user_info:
            self.client.user_name = name
        # 如果没有群组ID，获取群组列表
        if not self.client.group_id:
            logger.info(f"正在获取聊天群组ID ({agent_name})...")
            result = self.client.get_my_chat_group_list(agent_name=agent_name)
            if not result:
                raise HTTPException(
                    status_code=404, 
                    detail=f"无法找到指定的Agent群组: {agent_name}"
                )
        self.save_account_info()
        self._initialized = True
    
    def _extract_images_from_messages(self, messages: List[Any]) -> List[Dict[str, Any]]:
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
                    uploaded = self.client.upload_resource(content)
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
                            uploaded = self.client.upload_resource(image_url)
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
        agent_name: str = DEFAULT_AGENT_NAME,
        stream: bool = False
    ) -> Dict[str, Any]:
        """
        执行聊天完成
        
        Args:
            messages: 消息列表
            model: 模型名称（暂时未使用）
            model_name: 模型名称
            stream: 是否流式返回
            
        Returns:
            响应数据
        """
        # 确保已初始化
        await self._ensure_initialized(model)
        # 构建提示词
        prompt = self._build_prompt_from_messages(messages)
        if not prompt:
            raise HTTPException(status_code=400, detail="消息内容不能为空")
        
        # 提取图片资源
        resources = self._extract_images_from_messages(messages)
        agent_list = self.client.get_agent_list()
        # 遍历 agent_list 中的每一个 agent，调用 create_chat_group
        if agent_list and isinstance(agent_list, list):
            for agent in agent_list:
                label = agent.get("label", "")
                # 只处理 label 为 AGENT_LIST 的 agent
                if label in AGENT_LIST:
                    account_no = agent.get("account_no")
                    if account_no:
                        self.client.create_chat_group(account_no, label)
        # 发送消息
        task_id = self.client.send_message(
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
            return await self._collect_stream_response(task_id)
    
    async def _collect_stream_response(self, task_id: str) -> Dict[str, Any]:
        """
        收集流式响应并转换为完整响应
        
        Args:
            task_id: 任务ID
            
        Returns:
            完整的响应数据
        """
        full_content = ""
        video_url = None
        
        for line in self.client.stream_chat_completions(task_id):
            if line.startswith("data: "):
                if line[6:].strip() == "[DONE]":
                    break
                
                try:
                    json_data = json.loads(line[6:])

                    # 优化: 一次解析同时提取媒体URL和content
                    parsed_result = extract_media_from_data(json_data)
                    if parsed_result:
                        video_url, _ = parsed_result
                        break

                    choices = json_data.get('choices', [])
                    if choices and isinstance(choices, list) and len(choices) > 0:
                        choice = choices[0]
                        if isinstance(choice, dict):
                            # 优先从 delta 中获取 content
                            delta = choice.get('delta', {})
                            content = delta.get('content', '') if isinstance(delta, dict) else ''

                            # 如果没有 delta 内容，尝试从 message 中获取
                            if not content:
                                message = choice.get('message', {})
                                content = message.get('content', '') if isinstance(message, dict) else ''

                            if content:
                                full_content += content
                except json.JSONDecodeError:
                    pass
                except Exception as e:
                    logger.debug(f"解析响应数据时出错: {e}")
        
        # 构建 OpenAI 格式的响应
        response_id = f"chatcmpl-{task_id}"
        created = int(time.time())
        
        choices = [{
            "index": 0,
            "message": {
                "role": "assistant",
                "content": full_content
            },
            "finish_reason": "stop"
        }]
        
        # 如果有视频URL，添加到响应中
        if video_url:
            choices[0]["message"]["video_url"] = video_url
        
        return {
            "id": response_id,
            "object": "chat.completion",
            "created": created,
            "model": "sora-2",
            "choices": choices,
            "usage": {
                "prompt_tokens": len(full_content.split()) if full_content else 0,
                "completion_tokens": len(full_content.split()) if full_content else 0,
                "total_tokens": len(full_content.split()) * 2 if full_content else 0
            }
        }
    
    def stream_chat_completion(self, task_id: str) -> Iterator[str]:
        """
        流式返回聊天响应
        
        Args:
            task_id: 任务ID
            
        Yields:
            SSE格式的响应行
        """
        for line in self.client.stream_chat_completions(task_id):
            yield line
