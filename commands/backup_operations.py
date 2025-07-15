#!/usr/bin/env python3
"""
备份操作相关的业务逻辑
包含备份创建、下载、删除等核心业务逻辑
"""

import discord
import os
import zipfile
import tempfile
import asyncio
import logging
from datetime import datetime, timezone
from typing import Optional, List
from utils.file_manager import FileManager
from .backup_utils import BackupUtils

logger = logging.getLogger(__name__)

class BackupOperations:
    """备份操作类"""
    
    def __init__(self, bot, db_manager, message_handler):
        self.bot = bot
        self.db_manager = db_manager
        self.message_handler = message_handler
    
    async def process_backup_download(self, interaction: discord.Interaction, config_id: int, config_data):
        """处理备份下载"""
        try:
            config_id, guild_id, channel_id, thread_id = config_data[:4]
            title = config_data[5] if len(config_data) > 5 and config_data[5] else None
            
            # 确定下载文件名
            if thread_id:
                download_name = title or f"thread_{thread_id}"
            else:
                download_name = title or f"channel_{channel_id}"
            
            # 生成备份包（可能是多个文件）
            zip_file_paths = await self.create_backup_package(
                config_id, guild_id, interaction.user.id, 
                thread_id or channel_id, download_name
            )
            
            if zip_file_paths and len(zip_file_paths) > 0:
                # 检查是否是分卷
                if len(zip_file_paths) == 1:
                    # 单个文件
                    zip_file_path = zip_file_paths[0]
                    if os.path.exists(zip_file_path):
                        file_size = os.path.getsize(zip_file_path)
                        
                        # 发送文件
                        embed = discord.Embed(
                            title="✅ 备份下载完成",
                            description=f"备份: {download_name}\n文件大小: {FileManager.format_file_size(file_size)}",
                            color=discord.Color.green()
                        )
                        
                        safe_filename = BackupUtils.make_safe_filename(download_name)
                        file = discord.File(zip_file_path, filename=f"backup_{safe_filename}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.zip")
                        await interaction.edit_original_response(embed=embed, attachments=[file])
                        
                        # 清理临时文件
                        try:
                            os.remove(zip_file_path)
                        except:
                            pass
                else:
                    # 多个分卷文件
                    await self.send_multi_volume_files(interaction, zip_file_paths, download_name)
                    
            else:
                embed = discord.Embed(
                    title="❌ 生成失败",
                    description="生成备份包时发生错误",
                    color=discord.Color.red()
                )
                await interaction.edit_original_response(embed=embed)
                
        except Exception as e:
            logger.error(f"处理备份下载失败: {e}")
            embed = discord.Embed(
                title="❌ 处理失败",
                description="生成备份包时发生错误",
                color=discord.Color.red()
            )
            await interaction.edit_original_response(embed=embed)
    
    async def send_multi_volume_files(self, interaction: discord.Interaction, zip_file_paths: list, download_name: str):
        """发送多个分卷文件"""
        try:
            total_size = sum(os.path.getsize(path) for path in zip_file_paths if os.path.exists(path))
            
            # 发送第一条消息说明分卷情况
            embed = discord.Embed(
                title="📦 分卷备份下载",
                description=f"备份: {download_name}\n"
                          f"文件过大，已分为 {len(zip_file_paths)} 个分卷\n"
                          f"总大小: {FileManager.format_file_size(total_size)}\n\n"
                          f"请下载所有分卷文件，解压时请使用支持分卷的解压软件。",
                color=discord.Color.blue()
            )
            await interaction.edit_original_response(embed=embed)
            
            # 逐个发送分卷文件
            safe_filename = BackupUtils.make_safe_filename(download_name)
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            
            for i, zip_path in enumerate(zip_file_paths, 1):
                if os.path.exists(zip_path):
                    try:
                        file_size = os.path.getsize(zip_path)
                        
                        # 创建文件对象
                        file = discord.File(
                            zip_path, 
                            filename=f"backup_{safe_filename}_{timestamp}_vol{i}.zip"
                        )
                        
                        # 发送分卷文件
                        embed = discord.Embed(
                            title=f"📁 分卷 {i}/{len(zip_file_paths)}",
                            description=f"文件大小: {FileManager.format_file_size(file_size)}",
                            color=discord.Color.green()
                        )
                        
                        await interaction.followup.send(embed=embed, file=file, ephemeral=True)
                        
                    except Exception as e:
                        logger.error(f"发送分卷 {i} 失败: {e}")
                        error_embed = discord.Embed(
                            title=f"❌ 分卷 {i} 发送失败",
                            description="发送此分卷时发生错误",
                            color=discord.Color.red()
                        )
                        await interaction.followup.send(embed=error_embed, ephemeral=True)
            
            # 清理所有临时文件
            for zip_path in zip_file_paths:
                try:
                    os.remove(zip_path)
                except:
                    pass
                    
        except Exception as e:
            logger.error(f"发送分卷文件失败: {e}")
            # 清理临时文件
            for zip_path in zip_file_paths:
                try:
                    os.remove(zip_path)
                except:
                    pass

    async def create_backup_package(self, config_id: int, guild_id: int, author_id: int, 
                                  thread_id: int, thread_name: str) -> Optional[list]:
        """创建备份压缩包，如果文件过大则分卷"""
        try:
            # 创建临时目录
            temp_dir = tempfile.mkdtemp()
            
            # 获取消息和文件数据
            messages = await BackupUtils.get_backup_messages(self.db_manager, config_id)
            files = await self.db_manager.get_files_by_config(config_id)
            
            # 创建信息文件内容
            info_content = await BackupUtils.create_info_text(
                self.bot, self.db_manager, guild_id, author_id, thread_id, thread_name, messages, files, config_id
            )
            
            # 下载所有附件到内存
            attachment_data = []
            attachment_count = 0
            total_attachment_size = 0
            
            for file_record in files:
                file_id, message_backup_id, original_filename, stored_filename, file_size, file_url, webdav_path, backup_time = file_record
                
                if file_url and original_filename:
                    try:
                        # 下载文件
                        file_data = await BackupUtils.download_file_from_url(file_url)
                        if file_data:
                            safe_filename = BackupUtils.make_safe_filename(original_filename)
                            attachment_data.append((safe_filename, file_data))
                            attachment_count += 1
                            total_attachment_size += len(file_data)
                    except Exception as e:
                        logger.warning(f"下载附件失败: {original_filename}, 错误: {e}")
                        continue
            
            # 估算总大小 (信息文件 + 附件)
            info_size = len(info_content.encode('utf-8'))
            estimated_total_size = info_size + total_attachment_size
            
            # Discord限制: 25MB = 25 * 1024 * 1024 bytes
            max_size = 20 * 1024 * 1024  # 留一些余量，用20MB作为单个包的最大大小
            
            if estimated_total_size <= max_size:
                # 单个文件即可
                zip_path = os.path.join(temp_dir, f"backup_{thread_id}.zip")
                with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
                    # 添加信息文件
                    zipf.writestr("帖子信息.txt", info_content.encode('utf-8'))
                    
                    # 添加所有附件
                    for safe_filename, file_data in attachment_data:
                        zipf.writestr(f"附件/{safe_filename}", file_data)
                
                logger.info(f"备份包创建完成: {zip_path}, 包含 {len(messages)} 条消息, {attachment_count} 个附件")
                return [zip_path]
            else:
                # 需要分卷
                return await BackupUtils.create_multi_volume_backup(
                    temp_dir, thread_id, info_content, attachment_data, max_size, messages, attachment_count
                )
            
        except Exception as e:
            logger.error(f"创建备份包失败: {e}")
            return None
    
    async def delete_backup_data(self, config_id: int) -> bool:
        """删除备份配置和所有相关数据"""
        try:
            import aiosqlite
            async with aiosqlite.connect(self.db_manager.db_path) as db:
                # 开始事务
                await db.execute('BEGIN TRANSACTION')
                
                try:
                    # 删除文件备份记录
                    await db.execute('''
                        DELETE FROM file_backups 
                        WHERE message_backup_id IN (
                            SELECT id FROM message_backups WHERE config_id = ?
                        )
                    ''', (config_id,))
                    
                    # 删除消息备份记录
                    await db.execute('DELETE FROM message_backups WHERE config_id = ?', (config_id,))
                    
                    # 删除备份配置
                    await db.execute('DELETE FROM backup_configs WHERE id = ?', (config_id,))
                    
                    # 提交事务
                    await db.commit()
                    logger.info(f"删除备份配置成功: {config_id}")
                    return True
                    
                except Exception as e:
                    # 回滚事务
                    await db.execute('ROLLBACK')
                    logger.error(f"删除备份配置失败，已回滚: {e}")
                    return False
                    
        except Exception as e:
            logger.error(f"删除备份配置异常: {e}")
            return False
    
    async def background_history_scan(self, guild_id: int, channel_id: int, thread_id: Optional[int], 
                                    author_id: int, config_id: int):
        """后台历史扫描任务"""
        try:
            await asyncio.sleep(2)  # 等待响应发送完成
            scanned, downloaded = await self.message_handler.scan_history(
                guild_id, channel_id, thread_id, author_id, config_id
            )
            logger.info(f"后台历史扫描完成: 配置 {config_id}, 扫描 {scanned} 条, 下载 {downloaded} 个文件")
        except Exception as e:
            logger.error(f"后台历史扫描失败: {e}")