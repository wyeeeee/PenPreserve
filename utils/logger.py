import logging
import sys
from pathlib import Path

def setup_logging(config):
    """设置日志配置"""
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
    
    # 清除现有处理器
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)
    
    # 创建格式化器
    formatter = logging.Formatter(format_str)
    
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
    
    # 设置aiosqlite的日志级别
    aiosqlite_logger = logging.getLogger('aiosqlite')
    aiosqlite_logger.setLevel(logging.WARNING)
    
    logging.info("日志系统初始化完成") 