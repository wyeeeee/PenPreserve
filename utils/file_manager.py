import aiohttp
import asyncio
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional, Tuple
from urllib.parse import urlparse
from utils.webdav_client import WebDAVClient

logger = logging.getLogger(__name__)

class FileManager:
    def __init__(self, config, max_file_size: int = None):
        self.config = config
        self.max_file_size = max_file_size or config.max_file_size
        self.webdav_client = WebDAVClient(config)
        
        # 支持的文件扩展名
        self.allowed_extensions = set(config.allowed_extensions)
    
    def is_allowed_file(self, filename: str) -> bool:
        """检查文件扩展名是否允许"""
        ext = Path(filename).suffix.lower().lstrip('.')
        return ext in self.allowed_extensions
    
    async def download_and_upload_attachment(self, attachment, guild_id: int, author_id: int, thread_id: int, 
                                           message_timestamp: datetime) -> Optional[Tuple[str, str, int]]:
        """
        下载Discord附件并上传到WebDAV
        
        Args:
            attachment: Discord attachment object
            guild_id: 服务器ID
            author_id: 作者ID
            thread_id: 帖子ID
            message_timestamp: 消息时间戳
        
        Returns:
            Tuple[webdav_path, original_filename, file_size] 或 None
        """
        try:
            # 预检查文件大小
            if attachment.size > self.max_file_size:
                logger.warning(f"附件过大: {attachment.filename} ({self.format_file_size(attachment.size)})")
                return None
            
            # 检查文件扩展名
            if not self.is_allowed_file(attachment.filename):
                logger.warning(f"不支持的文件类型: {attachment.filename}")
                return None
            
            # 下载文件内容
            async with aiohttp.ClientSession() as session:
                async with session.get(attachment.url) as response:
                    if response.status != 200:
                        logger.error(f"下载失败: HTTP {response.status} - {attachment.url}")
                        return None
                    
                    # 检查文件大小
                    content_length = response.headers.get('content-length')
                    if content_length and int(content_length) > self.max_file_size:
                        logger.warning(f"文件过大: {content_length} bytes > {self.max_file_size}")
                        return None
                    
                    # 读取文件内容
                    content = await response.read()
                    
                    # 再次检查实际文件大小
                    if len(content) > self.max_file_size:
                        logger.warning(f"文件过大: {len(content)} bytes > {self.max_file_size}")
                        return None
            
            # 上传到WebDAV
            webdav_path = await self.webdav_client.upload_attachment(
                content, attachment.filename, str(guild_id), str(author_id), str(thread_id), message_timestamp
            )
            
            if webdav_path:
                logger.info(f"附件上传成功: {attachment.filename} -> {webdav_path}")
                return webdav_path, attachment.filename, len(content)
            else:
                logger.error(f"附件上传失败: {attachment.filename}")
                return None
                    
        except asyncio.TimeoutError:
            logger.error(f"下载超时: {attachment.url}")
        except aiohttp.ClientError as e:
            logger.error(f"下载客户端错误: {e}")
        except Exception as e:
            logger.error(f"下载附件失败: {e}")
        
        return None
    
    async def test_webdav_connection(self) -> bool:
        """测试WebDAV连接"""
        return await self.webdav_client.test_connection()
    
    @staticmethod
    def format_file_size(size_bytes: int) -> str:
        """格式化文件大小"""
        if size_bytes == 0:
            return "0 B"
        
        size_names = ["B", "KB", "MB", "GB", "TB"]
        i = 0
        size = float(size_bytes)
        
        while size >= 1024.0 and i < len(size_names) - 1:
            size /= 1024.0
            i += 1
        
        return f"{size:.1f} {size_names[i]}"