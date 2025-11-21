"""
聊天相关 API 路由
"""
import json
from uuid import uuid4
import time
from fastapi import APIRouter, HTTPException, Depends
from typing import Optional
from fastapi.responses import StreamingResponse
from app.models.schemas import ChatCompletionRequest, ChatCompletionResponse
from app.services.chat_service import ChatService
from app.services.conversation_store import get_conversation_store
from app.utils.stream_parser import extract_media_from_data
from app.utils.logger import get_logger
from app.utils.conversation import (
    extract_conversation_id_from_messages,
    inject_conversation_id_into_response,
)
from app.api.dependencies import verify_api_key
from app.config import AGENT_LIST

logger = get_logger(__name__)
router = APIRouter(tags=["chat"])

@router.post("/chat/completions")
async def chat_completions(
    request: ChatCompletionRequest,
    api_key: Optional[str] = Depends(verify_api_key)
):
    """
    Chat completions endpoint compatible with OpenAI API format.
    参考 temp.py 中的运行示例实现实际业务逻辑。
    """
    try:
        # 验证 model 参数的合法性
        # 确保 model 非空且在允许的 Agent 列表中
        if not request.model or not request.model.strip():
            raise HTTPException(
                status_code=400,
                detail="model 参数不能为空"
            )

        # 使用模糊匹配验证 model 是否在 AGENT_LIST 中
        # 这样可以容忍一些大小写、空格、emoji 等差异
        from app.services.kiira_client import is_agent_name_match
        if AGENT_LIST and not any(
            is_agent_name_match(request.model, agent)
            for agent in AGENT_LIST
        ):
            logger.warning(
                f"请求的模型 '{request.model}' 不在允许列表中，"
                f"允许的模型: {AGENT_LIST}"
            )
            raise HTTPException(
                status_code=400,
                detail=f"未知模型: {request.model}，请使用 /v1/models 查看可用模型列表"
            )

        # 从消息内容中尝试解析 conversation_id（仅在未显式提供时）
        extracted_conversation_id: Optional[str] = None
        cleaned_messages = request.messages

        if not request.conversation_id and request.messages:
            # 尝试从消息中解析会话 ID
            extracted_conversation_id, cleaned_messages = extract_conversation_id_from_messages(
                request.messages
            )
            if extracted_conversation_id:
                logger.info(f"从消息中解析到会话 ID: {extracted_conversation_id}")

        # 将 Pydantic 模型转换为字典（使用清洗后的消息内容）
        messages = [{"role": msg.role, "content": msg.content} for msg in cleaned_messages]

        # 获取会话存储实例
        conversation_store = get_conversation_store()

        # 会话管理：优先使用显式传入的 conversation_id，其次使用消息中解析出的 ID
        conversation_id = request.conversation_id or extracted_conversation_id
        is_new_conversation = False

        if conversation_id:
            # 尝试从会话存储中恢复会话
            session = await conversation_store.get(conversation_id)
            if session:
                # 校验 model 一致性：确保同一会话不会跨模型使用
                if session.agent_name != request.model:
                    logger.warning(
                        f"会话 {conversation_id} 的 model 不匹配: "
                        f"会话绑定={session.agent_name}, 请求={request.model}，创建新会话"
                    )
                    chat_service = ChatService()
                    is_new_conversation = True
                else:
                    logger.info(f"复用会话: conversation_id={conversation_id}, group_id={session.group_id}")
                    chat_service = ChatService(group_id=session.group_id, token=session.token)
                    # 更新会话活跃时间
                    await conversation_store.touch(conversation_id)
            else:
                # 会话不存在或已过期
                logger.warning(f"会话不存在或已过期: conversation_id={conversation_id}，创建新会话")
                chat_service = ChatService()
                is_new_conversation = True
        else:
            # 没有提供 conversation_id，创建新会话
            logger.info("未提供 conversation_id，创建新会话")
            chat_service = ChatService()
            is_new_conversation = True

        last_message = cleaned_messages[-1] if cleaned_messages else None
        prompt = (
            last_message.content
            if last_message and hasattr(last_message, "content") and isinstance(last_message.content, str)
            else ""
        )
        if prompt == "hi":
            logger.info(f"验证接口是否可用，{request.model}，直接返回正常响应")
            return {
                "id": str(uuid4()),
                "model": request.model,
                "object":"chat.completion.chunk",
                "choices": [{
                    "index":0,
                    "message":{"role": "assistant", "content": "hi"},
                    "finish_reason":"stop"
                }],
                "created":int(time.time())
            }
        # 如果请求流式响应
        if request.stream:
            # 执行聊天完成并获取 task_id
            # 显式传递 agent_name，确保使用用户请求的模型/Agent
            result = await chat_service.chat_completion(
                messages=[last_message],
                model=request.model,
                agent_name=request.model,
                stream=True
            )

            task_id = result.get("task_id")
            group_id = result.get("group_id")
            token = result.get("token")

            if not task_id:
                raise HTTPException(status_code=500, detail="无法获取任务ID")

            # 如果是新会话，创建 conversation_id 并保存到存储
            if is_new_conversation:
                session = await conversation_store.create(
                    agent_name=request.model,
                    group_id=group_id,
                    token=token
                )
                conversation_id = session.conversation_id
                logger.info(f"创建新会话: conversation_id={conversation_id}, group_id={group_id}")
            else:
                logger.info(f"使用现有会话: conversation_id={conversation_id}")
            
            # 返回流式响应
            async def generate_stream():
                """生成 OpenAI 格式的流式响应"""
                response_id = f"chatcmpl-{task_id}"
                created = int(time.time())
                model = request.model
                media_url = None
                media_type = None
                done_sent = False

                # 在第一个 chunk 中始终返回 conversation_id（统一前端处理逻辑）
                meta_chunk = {
                    "id": response_id,
                    "object": "chat.completion.chunk",
                    "created": created,
                    "model": model,
                    "conversation_id": conversation_id,  # 始终返回会话ID，便于前端统一处理
                    "choices": [{
                        "index": 0,
                        "delta": {},
                        "finish_reason": None
                    }]
                }
                yield f"data: {json.dumps(meta_chunk)}\n\n"
                try:
                    async for line in chat_service.stream_chat_completion(task_id):
                        if not line or not line.strip():
                            continue
                        # print(line)
                        # 处理 [DONE] 标记
                        if line.startswith("data: ") and line[6:].strip() == "[DONE]":
                            # 构建最终内容（包含媒体 URL 和会话 ID）
                            content_suffix = ""

                            # 如果有媒体 URL，添加媒体相关内容
                            if media_url:
                                if media_type == "image":
                                    content_suffix = f"\n\n![Generated Image]({media_url})\n\n"
                                elif media_type == "video":
                                    content_suffix = f"生成视频完成.\n[点击下载视频]({media_url})"
                                else:
                                    content_suffix = f"\n\n{media_url}\n\n"

                            # 自动注入会话 ID 标记，实现自动上下文传递
                            if conversation_id:
                                tag = f"\n\n[CONVERSATION_ID:{conversation_id}]"
                                content_suffix = (content_suffix.rstrip() if content_suffix else "") + tag

                            # 构建最终块
                            delta = {"content": content_suffix} if content_suffix else {}
                            final_chunk = {
                                "id": response_id,
                                "object": "chat.completion.chunk",
                                "created": created,
                                "model": model,
                                "choices": [{
                                    "index": 0,
                                    "delta": delta,
                                    "finish_reason": "stop"
                                }]
                            }
                            yield f"data: {json.dumps(final_chunk)}\n\n"

                            # 发送结束标记
                            yield "data: [DONE]\n\n"
                            done_sent = True
                            break
                        
                        # 解析 SSE 格式的数据
                        if line.startswith("data: "):
                            json_str = line[6:].strip()
                            if not json_str or json_str == "[DONE]":
                                continue
                            
                            try:
                                data = json.loads(json_str)
                                # logger.info(f"解析数据: {data.get('choices', [])}")
                                # 优化: 一次解析同时提取媒体URL和content,避免重复JSON解析
                                parse_result = extract_media_from_data(data)
                                if parse_result:
                                    parsed_media_url, parsed_media_type = parse_result
                                    media_type = parsed_media_type
                                    media_url = parsed_media_url
                                    logger.debug(f"检测到媒体资源: {media_type} - {media_url[:50]}...")

                                # 提取 content
                                content = ""
                                choices_data = data.get('choices', [])
                                if choices_data and isinstance(choices_data, list) and len(choices_data) > 0:
                                    choice = choices_data[0]
                                    if isinstance(choice, dict):
                                        # 优先从 delta 中获取 content
                                        delta = choice.get('delta', {})
                                        if isinstance(delta, dict):
                                            content = delta.get('content', '')
                                        
                                        # 如果没有 delta 内容，尝试从 message 中获取
                                        if not content:
                                            message = choice.get('message', {})
                                            if isinstance(message, dict):
                                                content = message.get('content', '')
                                # 构建 OpenAI 格式的流式响应块
                                if content:
                                    chunk = {
                                        "id": response_id,
                                        "object": "chat.completion.chunk",
                                        "created": created,
                                        "model": model,
                                        "choices": [{
                                            "index": 0,
                                            "delta": {"content": content},
                                            "finish_reason": None
                                        }]
                                    }
                                    yield f"data: {json.dumps(chunk)}\n\n"
                                
                            except json.JSONDecodeError:
                                # 如果不是有效的 JSON，跳过
                                logger.debug(f"跳过无效的 JSON 行: {line[:100]}")
                                continue
                            except Exception as e:
                                logger.debug(f"解析流式数据时出错: {e}")
                                continue
                    
                    # 如果循环正常结束（没有遇到 [DONE]），发送结束标记
                    if not done_sent:
                        # 发送一个带有 finish_reason 的最终块
                        final_chunk = {
                            "id": response_id,
                            "object": "chat.completion.chunk",
                            "created": created,
                            "model": model,
                            "choices": [{
                                "index": 0,
                                "delta": {},
                                "finish_reason": "stop"
                            }]
                        }
                        yield f"data: {json.dumps(final_chunk)}\n\n"
                        yield "data: [DONE]\n\n"
                        
                except Exception as e:
                    # 发送错误信息
                    logger.error(f"流式响应错误: {e}", exc_info=True)
                    error_data = json.dumps({
                        "error": {
                            "message": str(e),
                            "type": "server_error"
                        }
                    })
                    yield f"data: {error_data}\n\n"
            
            return StreamingResponse(
                generate_stream(),
                media_type="text/event-stream",
                headers={
                    "Cache-Control": "no-cache",
                    "Connection": "keep-alive",
                }
            )
        else:
            # 非流式响应
            # 显式传递 agent_name，确保使用用户请求的模型/Agent
            response_data = await chat_service.chat_completion(
                messages=messages,
                model=request.model,
                agent_name=request.model,
                stream=False
            )

            # 如果是新会话，创建 conversation_id 并保存到存储
            if is_new_conversation:
                # 从 chat_service 获取 group_id 和 token
                group_id = chat_service.client.group_id
                token = chat_service.client.token

                session = await conversation_store.create(
                    agent_name=request.model,
                    group_id=group_id,
                    token=token
                )
                conversation_id = session.conversation_id
                logger.info(f"创建新会话: conversation_id={conversation_id}, group_id={group_id}")

            # 在响应中添加 conversation_id（确保响应中始终包含会话ID）
            response_data["conversation_id"] = conversation_id

            # 自动注入会话 ID 到响应内容中，实现自动上下文传递
            inject_conversation_id_into_response(response_data, conversation_id)

            # 转换为 Pydantic 模型
            return ChatCompletionResponse(**response_data)
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"聊天完成失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"内部服务器错误: {str(e)}")