#!/usr/bin/env python3
"""
WebDAV客户端工具
用于将备份文件上传到WebDAV存储桶
"""

import logging
import asyncio
import aiohttp
import base64
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any
import time
from urllib.parse import urljoin

logger = logging.getLogger(__name__)

class WebDAVClient:
    """WebDAV客户端"""
    
    def __init__(self, config):
        self.config = config
        self.base_url = config.webdav_url
        self.username = config.webdav_username
        self.password = config.webdav_password
        self.timeout = config.webdav_timeout
        self.retry_count = config.webdav_retry_count
        
        # 创建认证头
        credentials = f"{self.username}:{self.password}"
        encoded_credentials = base64.b64encode(credentials.encode()).decode()
        self.auth_header = f"Basic {encoded_credentials}"
        
    async def _make_request(self, method: str, path: str, **kwargs):
        """发送WebDAV请求"""
        # 清理路径，避免双斜杠
        path = path.lstrip('/')
        if not self.base_url.endswith('/'):
            url = f"{self.base_url}/{path}"
        else:
            url = f"{self.base_url}{path}"
        
        headers = kwargs.get('headers', {})
        headers['Authorization'] = self.auth_header
        kwargs['headers'] = headers
        
        timeout = aiohttp.ClientTimeout(total=self.timeout)
        
        for attempt in range(self.retry_count):
            try:
                async with aiohttp.ClientSession(timeout=timeout) as session:
                    logger.debug(f"WebDAV请求: {method} {url}")
                    async with session.request(method, url, **kwargs) as response:
                        # 创建一个简单的响应对象来返回
                        class SimpleResponse:
                            def __init__(self, status, text_content):
                                self.status = status
                                self._text = text_content
                            
                            async def text(self):
                                return self._text
                        
                        response_text = await response.text()
                        logger.debug(f"WebDAV响应: {response.status} {response_text[:200]}")
                        
                        if response.status >= 500 and attempt < self.retry_count - 1:
                            await asyncio.sleep(2 ** attempt)  # 指数退避
                            continue
                        
                        return SimpleResponse(response.status, response_text)
                        
            except (aiohttp.ClientError, asyncio.TimeoutError) as e:
                if attempt < self.retry_count - 1:
                    logger.warning(f"WebDAV请求失败 (尝试 {attempt + 1}/{self.retry_count}): {e}")
                    await asyncio.sleep(2 ** attempt)
                    continue
                raise
                
    async def create_directory(self, path: str) -> bool:
        """创建目录（递归创建）"""
        try:
            # 清理路径
            path = path.strip('/').rstrip('/')
            if not path:
                return True
            
            # 尝试创建目录
            response = await self._make_request('MKCOL', path + '/')
            
            if response.status == 201:
                logger.debug(f"目录创建成功: {path}")
                return True
            elif response.status == 405:
                logger.debug(f"目录已存在: {path}")
                return True
            elif response.status == 409:
                # 父目录不存在，递归创建
                parent_path = '/'.join(path.split('/')[:-1])
                if parent_path and await self.create_directory(parent_path):
                    # 父目录创建成功，再次尝试创建当前目录
                    response = await self._make_request('MKCOL', path + '/')
                    if response.status in [201, 405]:
                        logger.debug(f"递归创建目录成功: {path}")
                        return True
                
            logger.error(f"创建目录失败: {path}, 状态码: {response.status}")
            return False
            
        except Exception as e:
            logger.error(f"创建目录异常: {path}, 错误: {e}")
            return False
            
    async def upload_file(self, local_path: str, remote_path: str) -> bool:
        """上传文件"""
        try:
            # 确保远程目录存在
            remote_dir = str(Path(remote_path).parent)
            await self.create_directory(remote_dir)
            
            # 读取文件内容
            with open(local_path, 'rb') as f:
                data = f.read()
            
            response = await self._make_request('PUT', remote_path, data=data)
            
            if response.status in [200, 201, 204]:
                logger.info(f"文件上传成功: {remote_path}")
                return True
            else:
                logger.error(f"文件上传失败: {remote_path}, 状态码: {response.status}")
                return False
                
        except Exception as e:
            logger.error(f"文件上传异常: {remote_path}, 错误: {e}")
            return False
            
    async def upload_bytes(self, data: bytes, remote_path: str, filename: str) -> bool:
        """上传字节数据"""
        full_path = None
        try:
            # 清理和规范化路径
            remote_path = remote_path.strip('/').rstrip('/')
            filename = filename.strip('/')
            
            # 确保远程目录存在
            if remote_path:
                success = await self.create_directory(remote_path)
                if not success:
                    logger.error(f"无法创建目录: {remote_path}")
                    return False
            
            # 构造完整路径
            if remote_path:
                full_path = f"{remote_path}/{filename}"
            else:
                full_path = filename
            
            # 添加适当的Content-Type头
            headers = {
                'Content-Type': 'application/octet-stream',
                'Content-Length': str(len(data))
            }
            
            response = await self._make_request('PUT', full_path, data=data, headers=headers)
            
            if response.status in [200, 201, 204]:
                logger.info(f"数据上传成功: {full_path}")
                return True
            else:
                response_text = await response.text() if hasattr(response, 'text') else "无响应内容"
                logger.error(f"数据上传失败: {full_path}, 状态码: {response.status}, 响应: {response_text}")
                return False
                
        except Exception as e:
            logger.error(f"数据上传异常: {full_path}, 错误: {e}")
            return False
            
    async def delete_file(self, remote_path: str) -> bool:
        """删除文件"""
        try:
            response = await self._make_request('DELETE', remote_path)
            
            if response.status in [200, 204, 404]:  # 404也算成功（文件不存在）
                logger.info(f"文件删除成功: {remote_path}")
                return True
            else:
                logger.error(f"文件删除失败: {remote_path}, 状态码: {response.status}")
                return False
                
        except Exception as e:
            logger.error(f"文件删除异常: {remote_path}, 错误: {e}")
            return False
            
    async def file_exists(self, remote_path: str) -> bool:
        """检查文件是否存在"""
        try:
            response = await self._make_request('HEAD', remote_path)
            return response.status == 200
        except Exception:
            return False
            
    def generate_filename(self, original_filename: str, message_timestamp: datetime) -> str:
        """生成带时间戳的文件名"""
        timestamp = message_timestamp.strftime("%Y%m%d_%H%M%S")
        file_path = Path(original_filename)
        return f"{timestamp}_{file_path.name}"
        
    def get_storage_path(self, guild_id: str, author_id: str, thread_id: str) -> str:
        """获取存储路径"""
        return f"{guild_id}/{author_id}/{thread_id}"
        
    async def upload_attachment(self, attachment_data: bytes, original_filename: str, 
                              guild_id: str, author_id: str, thread_id: str, message_timestamp: datetime) -> Optional[str]:
        """上传附件到WebDAV存储桶"""
        try:
            # 生成存储路径和文件名
            storage_path = self.get_storage_path(guild_id, author_id, thread_id)
            filename = self.generate_filename(original_filename, message_timestamp)
            
            # 上传文件
            success = await self.upload_bytes(attachment_data, storage_path, filename)
            
            if success:
                return f"{storage_path}/{filename}"
            else:
                return None
                
        except Exception as e:
            logger.error(f"上传附件失败: {original_filename}, 错误: {e}")
            return None
            
    async def test_connection(self) -> bool:
        """测试WebDAV连接"""
        try:
            # 简单的HEAD请求测试根目录
            response = await self._make_request('HEAD', '')
            success = response.status in [200, 404, 405]  # 404和405也表示连接成功但方法不支持
            if success:
                logger.info("WebDAV连接测试成功")
            else:
                logger.error(f"WebDAV连接测试失败，状态码: {response.status}")
            return success
        except Exception as e:
            logger.error(f"WebDAV连接测试失败: {e}")
            return False