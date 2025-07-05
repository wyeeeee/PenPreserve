import os
import aiohttp
import asyncio
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional, Tuple
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

class FileManager:
    def __init__(self, downloads_dir: str = "downloads", max_file_size: int = 10485760):
        self.downloads_dir = Path(downloads_dir)
        self.max_file_size = max_file_size
        self.downloads_dir.mkdir(exist_ok=True)
        
        # 支持的文件扩展名
        self.allowed_extensions = {
            'json', 'txt', 'png', 'jpg', 'jpeg', 'gif', 'pdf', 
            'doc', 'docx', 'zip', 'rar', 'mp4', 'mp3', 'wav',
            'webp', 'svg', 'bmp', 'xlsx', 'pptx', 'mov', 'avi'
        }
    
    def get_file_path(self, author_id: int, location_id: int, filename: str) -> Path:
        """获取文件存储路径"""
        # 创建目录结构: downloads/author_id/location_id/
        dir_path = self.downloads_dir / str(author_id) / str(location_id)
        dir_path.mkdir(parents=True, exist_ok=True)
        return dir_path / filename
    
    def generate_filename(self, original_filename: str) -> str:
        """生成带时间戳的文件名"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:19]  # 精确到毫秒
        return f"{timestamp}_{original_filename}"
    
    def is_allowed_file(self, filename: str) -> bool:
        """检查文件扩展名是否允许"""
        ext = Path(filename).suffix.lower().lstrip('.')
        return ext in self.allowed_extensions
    
    async def download_file(self, url: str, author_id: int, location_id: int, 
                          original_filename: str) -> Optional[Tuple[str, str, int]]:
        """
        下载文件到本地
        
        Returns:
            Tuple[saved_filename, file_path, file_size] 或 None
        """
        try:
            # 检查文件扩展名
            if not self.is_allowed_file(original_filename):
                logger.warning(f"不支持的文件类型: {original_filename}")
                return None
            
            # 生成保存文件名
            saved_filename = self.generate_filename(original_filename)
            file_path = self.get_file_path(author_id, location_id, saved_filename)
            
            # 检查文件是否已存在（通过文件大小判断）
            if file_path.exists():
                logger.debug(f"文件已存在: {file_path}")
                return saved_filename, str(file_path), file_path.stat().st_size
            
            # 下载文件
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as response:
                    if response.status != 200:
                        logger.error(f"下载失败: HTTP {response.status} - {url}")
                        return None
                    
                    # 检查文件大小
                    content_length = response.headers.get('content-length')
                    if content_length and int(content_length) > self.max_file_size:
                        logger.warning(f"文件过大: {content_length} bytes > {self.max_file_size}")
                        return None
                    
                    # 写入文件
                    content = await response.read()
                    
                    # 再次检查实际文件大小
                    if len(content) > self.max_file_size:
                        logger.warning(f"文件过大: {len(content)} bytes > {self.max_file_size}")
                        return None
                    
                    # 保存文件
                    file_path.write_bytes(content)
                    file_size = len(content)
                    
                    logger.info(f"下载完成: {saved_filename} ({self.format_file_size(file_size)})")
                    return saved_filename, str(file_path), file_size
                    
        except asyncio.TimeoutError:
            logger.error(f"下载超时: {url}")
        except aiohttp.ClientError as e:
            logger.error(f"下载客户端错误: {e}")
        except OSError as e:
            logger.error(f"文件系统错误: {e}")
        except Exception as e:
            logger.error(f"下载未知错误: {e}")
        
        return None
    
    async def download_discord_attachment(self, attachment, author_id: int, location_id: int) -> Optional[Tuple[str, str, int]]:
        """
        下载Discord附件
        
        Args:
            attachment: Discord attachment object
            author_id: 作者ID
            location_id: 位置ID（帖子ID或频道ID）
        
        Returns:
            Tuple[saved_filename, file_path, file_size] 或 None
        """
        try:
            # 预检查文件大小
            if attachment.size > self.max_file_size:
                logger.warning(f"附件过大: {attachment.filename} ({self.format_file_size(attachment.size)})")
                return None
            
            return await self.download_file(attachment.url, author_id, location_id, attachment.filename)
            
        except Exception as e:
            logger.error(f"下载Discord附件失败: {e}")
            return None
    
    def get_directory_stats(self, author_id: int, location_id: Optional[int] = None) -> dict:
        """获取目录统计信息"""
        try:
            if location_id:
                # 特定位置的统计
                dir_path = self.downloads_dir / str(author_id) / str(location_id)
                if not dir_path.exists():
                    return {'file_count': 0, 'total_size': 0, 'path': str(dir_path)}
                
                files = list(dir_path.glob('*'))
                file_count = len(files)
                total_size = sum(f.stat().st_size for f in files if f.is_file())
                
                return {
                    'file_count': file_count,
                    'total_size': total_size,
                    'path': str(dir_path),
                    'formatted_size': self.format_file_size(total_size)
                }
            else:
                # 作者的所有文件统计
                author_path = self.downloads_dir / str(author_id)
                if not author_path.exists():
                    return {'file_count': 0, 'total_size': 0, 'path': str(author_path)}
                
                file_count = 0
                total_size = 0
                
                for file_path in author_path.rglob('*'):
                    if file_path.is_file():
                        file_count += 1
                        total_size += file_path.stat().st_size
                
                return {
                    'file_count': file_count,
                    'total_size': total_size,
                    'path': str(author_path),
                    'formatted_size': self.format_file_size(total_size)
                }
                
        except Exception as e:
            logger.error(f"获取目录统计失败: {e}")
            return {'file_count': 0, 'total_size': 0, 'error': str(e)}
    
    def cleanup_empty_directories(self, author_id: int):
        """清理空目录"""
        try:
            author_path = self.downloads_dir / str(author_id)
            if not author_path.exists():
                return
            
            # 遍历并删除空目录
            for dir_path in author_path.iterdir():
                if dir_path.is_dir() and not any(dir_path.iterdir()):
                    dir_path.rmdir()
                    logger.debug(f"删除空目录: {dir_path}")
                    
            # 如果作者目录也空了，删除它
            if author_path.exists() and not any(author_path.iterdir()):
                author_path.rmdir()
                logger.debug(f"删除空的作者目录: {author_path}")
                
        except Exception as e:
            logger.error(f"清理空目录失败: {e}")
    
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
    
    def get_file_info(self, file_path: str) -> dict:
        """获取文件信息"""
        try:
            path = Path(file_path)
            if not path.exists():
                return {'exists': False}
            
            stat = path.stat()
            return {
                'exists': True,
                'size': stat.st_size,
                'formatted_size': self.format_file_size(stat.st_size),
                'created_time': datetime.fromtimestamp(stat.st_ctime),
                'modified_time': datetime.fromtimestamp(stat.st_mtime),
                'extension': path.suffix.lower().lstrip('.'),
                'is_allowed': self.is_allowed_file(path.name)
            }
            
        except Exception as e:
            logger.error(f"获取文件信息失败: {e}")
            return {'exists': False, 'error': str(e)}