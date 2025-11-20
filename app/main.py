"""
FastAPI 应用主入口
"""
import uvicorn
import json
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from app.api.v1 import router as v1_router
from app.utils.logger import configure_root_logger, get_logger
from app.config import API_KEY, AGENT_LIST, DEFAULT_AGENT_NAME
# 配置根日志记录器（彩色输出）
configure_root_logger(level=logging.INFO, use_color=True)

logger = get_logger(__name__)
# 定义一些颜色代码
CYAN = "\033[36m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
MAGENTA = "\033[35m"
RESET = "\033[0m"
# 紫色
RED = "\033[31m"
ORANGE = "\033[38;5;208m"

settings = {
    "API_KEY": API_KEY,
    "AGENT_LIST": AGENT_LIST,
    "DEFAULT_AGENT_NAME": DEFAULT_AGENT_NAME
}
project_logo_str = fr"""{GREEN}
██ ▄█▀ ▄▄ ▄▄ ▄▄▄▄   ▄▄▄  ████▄ ▄████▄ █████▄ ██ 
████   ██ ██ ██▄█▄ ██▀██  ▄██▀ ██▄▄██ ██▄▄█▀ ██ 
██ ▀█▄ ██ ██ ██ ██ ██▀██ ███▄▄ ██  ██ ██     ██ 
--------------------------------------------------

Kiira2API - 基于Kiira AI的逆向API服务
项目地址 : https://github.com/move132/kiira2api
作者     : move132
版本     : 1.0.0
当前环境变量信息
{json.dumps(settings, ensure_ascii=False, indent=2)}
"""
@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    # 启动时执行
    print(f"{GREEN}{'=' * 50}{RESET}")
    print(f"{GREEN}🚀Kiira2API 启动成功{RESET}")
    print(project_logo_str)
    print(f"{GREEN}{'=' * 50}{RESET}")
    yield

app = FastAPI(title="Kiira2API", version="1.0.0", lifespan=lifespan)

# 注册 API 路由
app.include_router(v1_router)


@app.get("/")
async def root():
    """根路径，返回 API 基本信息"""
    return {"message": "Kiira2API is running", "version": "1.0.0", "author": "move132", "project_url": "https://github.com/move132/kiira2api"}


@app.get("/health")
async def health():
    """健康检查端点"""
    return {"status": "healthy"}


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8999, log_level="info")