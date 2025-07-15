import logging
import sys
from pathlib import Path

# 全局标志，防止重复初始化
_logging_setup_done = False

def setup_logging(config):
    """设置日志配置"""
    global _logging_setup_done
    
    # 如果已经初始化过，直接返回
    if _logging_setup_done:
        return
    
    # 创建日志目录
    log_dir = Path('logs')
    log_dir.mkdir(exist_ok=True)
    
    # 获取配置
    level = getattr(logging, config.get('logging', 'level', fallback='INFO'))
    format_str = config.get('logging', 'format', fallback='[%(asctime)s] [%(levelname)s] %(name)s: %(message)s')
    file_enabled = config.getboolean('logging', 'file_enabled', fallback=True)
    console_enabled = config.getboolean('logging', 'console_enabled', fallback=True)
    
    # 创建根日志器
    root_logger = logging.getLogger()
    root_logger.setLevel(level)
    
    # 清除现有处理器，防止重复
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)
    
    # 创建格式化器，使用安全的格式字符串
    try:
        formatter = logging.Formatter(format_str)
    except (ValueError, TypeError) as e:
        # 如果格式字符串有问题，使用默认格式
        print(f"警告: 日志格式配置有误 ({e})，使用默认格式")
        formatter = logging.Formatter('[%(asctime)s] [%(levelname)s] %(name)s: %(message)s')
    
    # 添加控制台处理器
    if console_enabled:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(level)
        console_handler.setFormatter(formatter)
        root_logger.addHandler(console_handler)
    
    # 添加文件处理器
    if file_enabled:
        file_handler = logging.FileHandler(
            log_dir / 'bot.log',
            encoding='utf-8'
        )
        file_handler.setLevel(level)
        file_handler.setFormatter(formatter)
        root_logger.addHandler(file_handler)
    
    # 设置discord.py的日志级别
    discord_logger = logging.getLogger('discord')
    discord_logger.setLevel(logging.WARNING)
    
    # 创建过滤器来屏蔽PyNaCl警告
    class PyNaClFilter(logging.Filter):
        def filter(self, record):
            return 'PyNaCl is not installed' not in record.getMessage()
    
    # 应用过滤器到discord.client日志器
    discord_client_logger = logging.getLogger('discord.client')
    discord_client_logger.addFilter(PyNaClFilter())
    
    # 设置aiosqlite的日志级别
    aiosqlite_logger = logging.getLogger('aiosqlite')
    aiosqlite_logger.setLevel(logging.WARNING)
    
    # 标记初始化完成
    _logging_setup_done = True
    print("日志系统初始化完成")  # 用print避免循环 