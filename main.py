"""
兼容入口：从 app.main 导入应用
保留此文件以便使用 uvicorn main:app 启动
"""

from app.main import app

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8999)
