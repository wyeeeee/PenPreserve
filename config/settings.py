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
            logging.warning(f"配置文件 {self.config_file} 不存在，正在创建模板...")
            self.create_config_template()
        
        # 禁用插值功能，避免日志格式字符串中的%符号被误解
        self.config = configparser.ConfigParser(interpolation=None)
        self.config.read(self.config_file, encoding='utf-8')
        logging.info(f"配置文件 {self.config_file} 加载完成")
    
    def create_config_template(self):
        """创建配置文件模板"""
        # 确保配置文件目录存在
        config_dir = Path(self.config_file).parent
        config_dir.mkdir(parents=True, exist_ok=True)
        
        template_content = """# PenPreserve Discord Bot 配置文件
# 请根据实际情况填写各项配置

[bot]
# Discord Bot Token（必填）
token = YOUR_BOT_TOKEN_HERE
# 命令前缀
prefix = !
# Bot描述
description = PenPreserve Discord备份机器人
# 活动类型
activity_type = watching
# 活动名称
activity_name = 文件备份系统

[database]
# 数据库文件名
filename = bot_data.db
# 历史扫描最大消息数
max_scan_messages = 10000

[backup]
# 允许的文件扩展名
allowed_extensions = json,txt,png,jpg,jpeg,gif,pdf,docx,xlsx,pptx,zip,rar,7z,mp4,mp3,wav
# 最大文件大小（字节）10MB
max_file_size = 10485760

[webhook]
# Webhook服务器监听地址
host = 0.0.0.0
# Webhook服务器端口
port = 8080
# 是否启用Webhook
enabled = true

[network]
# 最大重试次数
max_retries = 10
# 基础重试延迟（秒）
base_retry_delay = 5
# 启用诊断
enable_diagnostics = true
# 连接超时（秒）
connection_timeout = 60
# 读取超时（秒）
read_timeout = 30

[webdav]
# WebDAV服务器URL（必填）
url = https://your-webdav-server.com/path
# WebDAV用户名（必填）
username = your_username
# WebDAV密码（必填）
password = your_password
# 连接超时（秒）
timeout = 30
# 重试次数
retry_count = 3

# 日志配置
[logging]
# 日志级别：DEBUG, INFO, WARNING, ERROR, CRITICAL
level = INFO
# 日志文件名
filename = logs/bot.log
# 日志格式
format = [%(asctime)s] [%(levelname)s] %(name)s: %(message)s
"""
        
        try:
            with open(self.config_file, 'w', encoding='utf-8') as f:
                f.write(template_content)
            
            print(f"✅ 配置文件模板已创建: {self.config_file}")
            print("⚠️  请编辑配置文件，填写必要的配置项：")
            print("   - bot.token: Discord Bot Token")
            print("   - webdav.url: WebDAV服务器地址")
            print("   - webdav.username: WebDAV用户名")
            print("   - webdav.password: WebDAV密码")
            print("然后重新运行程序。")
            
            import sys
            sys.exit(0)
            
        except Exception as e:
            logging.error(f"创建配置文件模板失败: {e}")
            raise
    
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
    
    # WebDAV设置
    @property
    def webdav_url(self):
        return self.get('webdav', 'url')
    
    @property
    def webdav_username(self):
        return self.get('webdav', 'username')
    
    @property
    def webdav_password(self):
        return self.get('webdav', 'password')
    
    @property
    def webdav_timeout(self):
        return self.getint('webdav', 'timeout', fallback=30)
    
    @property
    def webdav_retry_count(self):
        return self.getint('webdav', 'retry_count', fallback=3) 