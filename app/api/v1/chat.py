"""
聊天相关 API 路由
"""
import re
import json
import time
from fastapi import APIRouter, HTTPException, Depends
from typing import Optional
from fastapi.responses import StreamingResponse
from app.models.schemas import ChatCompletionRequest, ChatCompletionResponse
from app.services.chat_service import ChatService
from app.utils.stream_parser import extract_media_from_data
from app.utils.logger import get_logger
from app.api.dependencies import verify_api_key

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
        # 将 Pydantic 模型转换为字典
        messages = [{"role": msg.role, "content": msg.content} for msg in request.messages]

        # Group ID: 【{group_id}】
        msg_group_id = None
        msg_token = None
        for msg in request.messages:
            if getattr(msg, "role", None) == "assistant":
                content = getattr(msg, "content", "")
                if isinstance(content, str):
                    group_id_match = re.search(r'Group ID:【(.*?)】', content)
                    token_match = re.search(r'Token:【(.*?)】', content, re.DOTALL)
                    if group_id_match and token_match:
                        msg_group_id = group_id_match.group(1)
                        msg_token = token_match.group(1)
                        logger.info(f"获取到历史记录中的 Group ID: {msg_group_id}, Token: {msg_token[-20:]}")
                        break
        # 创建聊天服务实例
        if not msg_group_id:
            logger.warning(f"未获取到历史记录中的 Group ID, 创建新的聊天服务实例")
            chat_service = ChatService()
        else:
            logger.info(f"获取到历史记录中的 Group ID， 直接继续原来的聊天")
            chat_service = ChatService(group_id=msg_group_id, token=msg_token)

        last_message = request.messages[-1] if request.messages else None
        # 如果请求流式响应
        if request.stream:
            if msg_group_id and msg_token:
                # 同一对话复用已有的group_id和token,避免重复查询
                prompt = (
                    last_message.content
                    if last_message and hasattr(last_message, "content") and isinstance(last_message.content, str)
                    else ""
                )
                resources = chat_service._extract_images_from_messages([last_message]) if last_message else []
                logger.info(f"复用对话状态 group_id={msg_group_id}, 提取图片资源数量: {len(resources)}")

                # 直接使用已有的group_id和token
                chat_service.client.group_id = msg_group_id
                chat_service.client.token = msg_token

                # 如果有at_account_no缓存则使用,否则查询一次
                if not chat_service.client.at_account_no:
                    _, at_account_no = chat_service.client.get_my_chat_group_list(request.model)
                else:
                    at_account_no = chat_service.client.at_account_no

                task_id = chat_service.client.send_message(
                    message=prompt,
                    at_account_no=at_account_no,
                    resources=resources if resources else None
                )
                result = {
                    "task_id": task_id,
                    "group_id": msg_group_id,
                    "token": msg_token
                }
            else:
                # 执行聊天完成并获取 task_id
                result = await chat_service.chat_completion(
                    messages=[last_message],
                    model=request.model,
                    stream=True
                )
            task_id = result.get("task_id")
            group_id = result.get("group_id")
            token = result.get("token")
            if not task_id:
                raise HTTPException(status_code=500, detail="无法获取任务ID")
            
            # 返回流式响应
            async def generate_stream():
                """生成 OpenAI 格式的流式响应"""
                response_id = f"chatcmpl-{task_id}"
                created = int(time.time())
                model = request.model
                media_url = None
                media_type = None
                done_sent = False
                if len(request.messages) == 1:
                    # 发送group_id
                    content = f"""<div style='color: rgb(0, 185, 107);'>Group ID:【{group_id}】</div>
                                  <div style='color: rgb(0, 185, 130);'>Token:【{token}】</div>
                                """
                    group_id_chunk = {
                        "id": response_id,
                        "object": "chat.completion.chunk",
                        "created": created,
                        "model": model,
                        "choices": [{
                            "index": 0,
                            "delta": {"content": content},
                            "finish_reason": "stop"
                        }]
                    }
                    yield f"data: {json.dumps(group_id_chunk)}\n\n"
                try:
                    for line in chat_service.stream_chat_completion(task_id):
                        if not line or not line.strip():
                            continue
                        # print(line)
                        # 处理 [DONE] 标记
                        if line.startswith("data: ") and line[6:].strip() == "[DONE]":
                            # 如果有视频URL，发送一个包含视频URL的最终块
                            if media_url:
                                final_chunk = {
                                    "id": response_id,
                                    "object": "chat.completion.chunk",
                                    "created": created,
                                    "model": model,
                                    "choices": [{
                                        "index": 0,
                                        "delta": {
                                            "content":
                                                f"\n\n![Generated Image]({media_url})\n\n" if media_type == "image"
                                                else (
                                                    f"生成视频完成.\n[点击下载视频]({media_url})" if media_type == "video"
                                                    else f"\n\n{media_url}\n\n"
                                                )
                                        },
                                        "finish_reason": "stop"
                                    }]
                                }
                                yield f"data: {json.dumps(final_chunk)}\n\n"
                            else:
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
            response_data = await chat_service.chat_completion(
                messages=messages,
                model=request.model,
                stream=False
            )
            
            # 转换为 Pydantic 模型
            return ChatCompletionResponse(**response_data)
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"聊天完成失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"内部服务器错误: {str(e)}")