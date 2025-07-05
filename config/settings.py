import configparser
import logging
import os
from pathlib import Path

class Config:
    def __init__(self, config_file='config.cfg'):
        self.config_file = config_file
        self.config = None
        self.load_config()
    
    def load_config(self):
        """加载配置文件"""
        if not os.path.exists(self.config_file):
            logging.error(f"配置文件 {self.config_file} 不存在")
            raise FileNotFoundError(f"配置文件 {self.config_file} 不存在")
        
        # 禁用插值功能，避免日志格式字符串中的%符号被误解
        self.config = configparser.ConfigParser(interpolation=None)
        self.config.read(self.config_file, encoding='utf-8')
        logging.info(f"配置文件 {self.config_file} 加载完成")
    
    def get(self, section, option, fallback=None):
        """获取配置值"""
        return self.config.get(section, option, fallback=fallback)
    
    def getint(self, section, option, fallback=None):
        """获取整数配置值"""
        return self.config.getint(section, option, fallback=fallback)
    
    def getboolean(self, section, option, fallback=None):
        """获取布尔值配置值"""
        return self.config.getboolean(section, option, fallback=fallback)
    
    @property
    def token(self):
        return self.get('bot', 'token')
    
    @property
    def prefix(self):
        return self.get('bot', 'prefix', fallback='!')
    
    @property
    def description(self):
        return self.get('bot', 'description', fallback='Discord Bot')
    
    @property
    def activity_type(self):
        return self.get('bot', 'activity_type', fallback='playing')
    
    @property
    def activity_name(self):
        return self.get('bot', 'activity_name', fallback='with Discord.py')
    
    @property
    def db_filename(self):
        return self.get('database', 'filename', fallback='bot_data.db')
    
    @property
    def max_scan_messages(self):
        return self.getint('database', 'max_scan_messages', fallback=1000)
    
    @property
    def allowed_extensions(self):
        extensions = self.get('backup', 'allowed_extensions', fallback='json,txt,png,jpg,jpeg,gif')
        return [ext.strip() for ext in extensions.split(',')]
    
    @property
    def max_file_size(self):
        return self.getint('backup', 'max_file_size', fallback=10485760)  # 10MB
    
    @property
    def webhook_host(self):
        return self.get('webhook', 'host', fallback='0.0.0.0')
    
    @property
    def webhook_port(self):
        return self.getint('webhook', 'port', fallback=8080)
    
    @property
    def webhook_enabled(self):
        return self.getboolean('webhook', 'enabled', fallback=True)
    
    # 网络设置
    @property
    def max_retries(self):
        return self.getint('network', 'max_retries', fallback=10)
    
    @property
    def base_retry_delay(self):
        return self.getint('network', 'base_retry_delay', fallback=5)
    
    @property
    def enable_diagnostics(self):
        return self.getboolean('network', 'enable_diagnostics', fallback=True)
    
    @property
    def connection_timeout(self):
        return self.getint('network', 'connection_timeout', fallback=60)
    
    @property
    def read_timeout(self):
        return self.getint('network', 'read_timeout', fallback=30) 