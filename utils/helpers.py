import aiohttp
import aiofiles
import logging
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

async def download_file(url, max_size=10485760):
    """下载文件数据"""
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                if response.status != 200:
                    logger.warning(f"无法下载文件: {url}, 状态码: {response.status}")
                    return None
                
                # 检查文件大小
                content_length = response.headers.get('content-length')
                if content_length and int(content_length) > max_size:
                    logger.warning(f"文件过大: {url}, 大小: {content_length}")
                    return None
                
                # 读取文件数据
                data = await response.read()
                if len(data) > max_size:
                    logger.warning(f"文件过大: {url}, 实际大小: {len(data)}")
                    return None
                
                return data
    except Exception as e:
        logger.error(f"下载文件失败: {url}, 错误: {e}")
        return None

def is_allowed_extension(filename, allowed_extensions):
    """检查文件扩展名是否允许"""
    if not filename:
        return False
    
    extension = Path(filename).suffix.lower().lstrip('.')
    return extension in allowed_extensions

def format_file_size(size_bytes):
    """格式化文件大小"""
    if size_bytes == 0:
        return "0B"
    
    size_names = ["B", "KB", "MB", "GB"]
    i = 0
    while size_bytes >= 1024 and i < len(size_names) - 1:
        size_bytes /= 1024
        i += 1
    
    return f"{size_bytes:.1f}{size_names[i]}"

def parse_datetime(timestamp):
    """解析时间戳"""
    if isinstance(timestamp, str):
        try:
            return datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
        except ValueError:
            return datetime.now()
    return timestamp

async def safe_send_message(channel, content=None, embed=None, view=None):
    """安全发送消息"""
    try:
        return await channel.send(content=content, embed=embed, view=view)
    except Exception as e:
        logger.error(f"发送消息失败: {e}")
        return None

def truncate_text(text, max_length=2000):
    """截断文本"""
    if len(text) <= max_length:
        return text
    return text[:max_length-3] + "..."

def extract_user_id_from_mention(mention):
    """从提及中提取用户ID"""
    if mention.startswith('<@') and mention.endswith('>'):
        user_id = mention[2:-1]
        if user_id.startswith('!'):
            user_id = user_id[1:]
        try:
            return int(user_id)
        except ValueError:
            return None
    return None 