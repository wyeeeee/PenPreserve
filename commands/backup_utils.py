#!/usr/bin/env python3
"""
备份相关工具函数
包含文件下载、压缩包创建、文件名处理等工具函数
"""

import os
import zipfile
import tempfile
import aiohttp
import logging
import asyncio
from datetime import datetime
from typing import Optional, List, Tuple
from utils.file_manager import FileManager

logger = logging.getLogger(__name__)

class BackupUtils:
    """备份工具类"""
    
    @staticmethod
    async def download_file_from_url(url: str) -> Optional[bytes]:
        """从URL下载文件"""
        try:
            timeout = aiohttp.ClientTimeout(total=30)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(url) as response:
                    if response.status == 200:
                        return await response.read()
                    else:
                        logger.warning(f"下载文件失败: HTTP {response.status} - {url}")
                        return None
        except Exception as e:
            logger.error(f"下载文件异常: {url}, 错误: {e}")
            return None
    
    @staticmethod
    def make_safe_filename(filename: str) -> str:
        """创建安全的文件名"""
        # 替换不安全的字符
        unsafe_chars = '<>:"/\\|?*'
        safe_filename = filename
        for char in unsafe_chars:
            safe_filename = safe_filename.replace(char, '_')
        return safe_filename
    
    @staticmethod
    async def get_backup_messages(db_manager, config_id: int) -> List:
        """获取备份的消息"""
        try:
            import aiosqlite
            async with aiosqlite.connect(db_manager.db_path) as db:
                cursor = await db.execute('''
                    SELECT message_id, content, created_at, backup_time, content_type
                    FROM message_backups 
                    WHERE config_id = ? 
                    ORDER BY created_at ASC
                ''', (config_id,))
                return await cursor.fetchall()
        except Exception as e:
            logger.error(f"获取备份消息失败: {e}")
            return []
    
    @staticmethod
    async def create_info_text(bot, db_manager, guild_id: int, author_id: int, thread_id: int, 
                             thread_name: str, messages: List, files: List, config_id: int) -> str:
        """创建帖子信息文本"""
        # 从数据库获取保存的标题
        try:
            # 直接根据config_id查询配置信息
            import aiosqlite
            async with aiosqlite.connect(db_manager.db_path) as db:
                cursor = await db.execute('''
                    SELECT title FROM backup_configs WHERE id = ?
                ''', (config_id,))
                result = await cursor.fetchone()
                saved_title = result[0] if result and result[0] else None
            
            display_title = saved_title or thread_name or "未知标题"
            
            # 获取服务器信息
            guild = bot.get_guild(guild_id)
            display_guild = guild.name if guild else f"服务器ID: {guild_id}"
            
            # 获取首楼内容（从消息列表中找第一条消息）
            first_message_content = ""
            if messages:
                first_message_content = messages[0][1] or ""  # 第一条消息的内容
            
            display_channel = "未知频道"
            
            # 尝试获取频道名称
            if guild:
                # 这里需要判断是帖子还是频道
                if thread_id:
                    # 尝试获取父频道名称
                    for channel in guild.channels:
                        if hasattr(channel, 'threads'):
                            for thread in channel.threads:
                                if thread.id == thread_id:
                                    display_channel = channel.name
                                    break
                else:
                    # 直接是频道
                    channel = guild.get_channel(thread_id)
                    if channel:
                        display_channel = channel.name
        except Exception as e:
            logger.warning(f"获取备份信息失败: {e}")
            display_title = thread_name or "未知标题"
            display_guild = f"服务器ID: {guild_id}"
            display_channel = "未知频道"
            first_message_content = ""
        
        info_lines = [
            f"=== 帖子备份信息 ===",
            f"帖子名称: {display_title}",
            f"帖子ID: {thread_id}",
            f"服务器: {display_guild}",
            f"频道: {display_channel}",
            f"作者ID: {author_id}",
            f"备份时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            f"消息数量: {len(messages)}",
            f"附件数量: {len(files)}",
            "",
        ]
        
        if first_message_content:
            info_lines.extend([
                "=== 首楼内容 ===",
                first_message_content,
                "",
            ])
        
        info_lines.extend([
            "=== 消息内容 ===",
            ""
        ])
        
        for i, message in enumerate(messages, 1):
            message_id, content, created_at, backup_time, content_type = message
            
            # 处理创建时间
            try:
                if isinstance(created_at, str):
                    created_time = datetime.fromisoformat(created_at).strftime('%Y-%m-%d %H:%M:%S')
                else:
                    created_time = created_at.strftime('%Y-%m-%d %H:%M:%S')
            except (ValueError, AttributeError):
                created_time = "时间格式错误"
            
            info_lines.extend([
                f"--- 消息 {i} ---",
                f"消息ID: {message_id}",
                f"发送时间: {created_time}",
                f"内容: {content or '(无文本内容)'}",
                ""
            ])
        
        if files:
            info_lines.extend([
                "=== 附件列表 ===",
                ""
            ])
            
            for i, file_record in enumerate(files, 1):
                file_id, message_backup_id, original_filename, stored_filename, file_size, file_url, webdav_path, backup_time = file_record
                info_lines.extend([
                    f"附件 {i}: {original_filename}",
                    f"文件大小: {FileManager.format_file_size(file_size)}",
                    f"WebDAV路径: {webdav_path}",
                    ""
                ])
        
        return "\n".join(info_lines)
    
    @staticmethod
    async def create_multi_volume_backup(temp_dir: str, thread_id: int, info_content: str, 
                                       attachment_data: list, max_size: int, messages: list, attachment_count: int) -> list:
        """创建分卷备份包"""
        zip_files = []
        
        try:
            # 第一卷：信息文件 + 部分附件
            volume_num = 1
            zip_path = os.path.join(temp_dir, f"backup_{thread_id}_vol{volume_num}.zip")
            
            with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
                # 添加信息文件到第一卷
                zipf.writestr("帖子信息.txt", info_content.encode('utf-8'))
                current_size = len(info_content.encode('utf-8'))
                
                # 添加附件直到接近大小限制
                attachment_index = 0
                for safe_filename, file_data in attachment_data:
                    file_size = len(file_data)
                    
                    # 检查是否需要新的分卷
                    if current_size + file_size > max_size and current_size > len(info_content.encode('utf-8')):
                        # 当前分卷已满，创建新分卷
                        break
                    
                    zipf.writestr(f"附件/{safe_filename}", file_data)
                    current_size += file_size
                    attachment_index += 1
            
            zip_files.append(zip_path)
            
            # 创建后续分卷
            while attachment_index < len(attachment_data):
                volume_num += 1
                zip_path = os.path.join(temp_dir, f"backup_{thread_id}_vol{volume_num}.zip")
                
                with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
                    current_size = 0
                    
                    # 添加剩余附件
                    while attachment_index < len(attachment_data):
                        safe_filename, file_data = attachment_data[attachment_index]
                        file_size = len(file_data)
                        
                        # 检查是否超过限制
                        if current_size + file_size > max_size and current_size > 0:
                            break
                        
                        zipf.writestr(f"附件/{safe_filename}", file_data)
                        current_size += file_size
                        attachment_index += 1
                
                zip_files.append(zip_path)
            
            logger.info(f"分卷备份包创建完成: {len(zip_files)} 个文件, 包含 {len(messages)} 条消息, {attachment_count} 个附件")
            return zip_files
            
        except Exception as e:
            logger.error(f"创建分卷备份包失败: {e}")
            # 清理已创建的文件
            for zip_file in zip_files:
                try:
                    os.remove(zip_file)
                except:
                    pass
            return None