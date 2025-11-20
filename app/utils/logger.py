"""
统一日志处理模块，支持彩色输出
"""
import logging
import sys
from typing import Optional


class ColoredFormatter(logging.Formatter):
    """彩色日志格式化器"""
    
    # ANSI 颜色代码
    COLORS = {
        'DEBUG': '\033[36m',      # 青色
        'INFO': '\033[32m',       # 绿色
        'WARNING': '\033[33m',    # 黄色
        'ERROR': '\033[31m',      # 红色
        'CRITICAL': '\033[35m',   # 紫色
        'RESET': '\033[0m',       # 重置
    }
    
    def __init__(self, use_color: bool = True, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.use_color = use_color and sys.stdout.isatty()
    
    def format(self, record: logging.LogRecord) -> str:
        """格式化日志记录"""
        if self.use_color:
            # 保存原始值
            original_levelname = record.levelname
            
            # 获取颜色
            color = self.COLORS.get(record.levelname, self.COLORS['RESET'])
            reset = self.COLORS['RESET']
            
            # 给级别名称添加颜色
            record.levelname = f"{color}{record.levelname}{reset}"
            
            # 先获取格式化后的消息内容（这样能正确处理所有格式化情况）
            formatted_message = record.getMessage()
            
            # 给消息内容添加颜色
            # 临时替换消息，以便在格式化时包含颜色
            original_msg = record.msg
            original_args = record.args
            record.msg = f"{color}{formatted_message}{reset}"
            record.args = ()  # 清空参数，因为消息已经格式化
            
            # 格式化日志记录
            formatted = super().format(record)
            
            # 恢复原始值（避免影响其他处理器）
            record.levelname = original_levelname
            record.msg = original_msg
            record.args = original_args
            
            return formatted
        else:
            return super().format(record)


def setup_logger(
    name: Optional[str] = None,
    level: int = logging.INFO,
    use_color: bool = True,
    format_string: Optional[str] = None
) -> logging.Logger:
    """
    设置并返回配置好的日志记录器
    
    Args:
        name: 日志记录器名称，如果为 None 则使用调用模块的名称
        level: 日志级别，默认为 INFO
        use_color: 是否使用彩色输出，默认为 True
        format_string: 自定义格式字符串，如果为 None 则使用默认格式
        
    Returns:
        配置好的日志记录器
    """
    # 创建日志记录器
    logger = logging.getLogger(name)
    logger.setLevel(level)
    
    # 不添加处理器，让日志传播到根日志记录器统一处理
    # 这样可以避免重复输出
    # 如果根日志记录器已配置，子日志记录器会自动使用根日志记录器的配置
    
    return logger


def get_logger(name: Optional[str] = None) -> logging.Logger:
    """
    获取日志记录器（便捷函数）
    
    Args:
        name: 日志记录器名称，如果为 None 则使用调用模块的名称
        
    Returns:
        日志记录器实例
    """
    return setup_logger(name=name)


# 配置根日志记录器
def configure_root_logger(
    level: int = logging.INFO,
    use_color: bool = True,
    format_string: Optional[str] = None
) -> None:
    """
    配置根日志记录器
    
    Args:
        level: 日志级别，默认为 INFO
        use_color: 是否使用彩色输出，默认为 True
        format_string: 自定义格式字符串，如果为 None 则使用默认格式
    """
    if format_string is None:
        format_string = '%(asctime)s | %(levelname)-8s | %(name)s | %(message)s'
    
    root_logger = logging.getLogger()
    root_logger.setLevel(level)
    
    # 清除现有的处理器和基本配置
    root_logger.handlers.clear()
    
    # 禁用默认的 basicConfig，避免重复配置
    # 通过设置 root_logger 的 propagate 为 True（默认），让所有子日志记录器传播到根日志记录器
    
    # 创建控制台处理器
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(level)
    
    # 创建彩色格式化器
    formatter = ColoredFormatter(
        use_color=use_color,
        fmt=format_string,
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    console_handler.setFormatter(formatter)
    
    # 添加处理器到根日志记录器
    root_logger.addHandler(console_handler)
    
    # 设置第三方库的日志级别
    logging.getLogger("uvicorn").setLevel(logging.INFO)
    logging.getLogger("uvicorn.access").setLevel(logging.INFO)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)

