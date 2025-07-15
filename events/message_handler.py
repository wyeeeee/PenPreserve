#!/usr/bin/env python3
"""
增强的消息处理器
包含自动删除通知、历史扫描、WebDAV存储等功能
"""

import discord
import logging
import asyncio
from datetime import datetime, timezone, timedelta
from typing import Optional, Tuple, List
from utils.file_manager import FileManager

logger = logging.getLogger(__name__)

class MessageHandler:
    def __init__(self, bot, db_manager, config):
        self.bot = bot
        self.db_manager = db_manager
        self.config = config
        self.file_manager = FileManager(config)
    
    async def handle_message(self, message: discord.Message):
        """处理新消息"""
        # 忽略机器人消息
        if message.author.bot:
            return
        
        try:
            # 确定位置信息
            if isinstance(message.channel, discord.Thread):
                # 帖子消息
                thread_id = message.channel.id
                channel_id = message.channel.parent.id
                location_id = thread_id
                content_type = "thread"
            else:
                # 频道消息
                thread_id = None
                channel_id = message.channel.id
                location_id = channel_id
                content_type = "channel"
            
            # 检查是否有备份配置
            backup_config = await self.db_manager.get_backup_config(
                message.guild.id, channel_id, thread_id, message.author.id
            )
            
            if not backup_config:
                return  # 没有配置，不处理
            
            config_id = backup_config[0]
            
            # 检查消息是否已备份（防重复）
            existing_backup = await self.db_manager.get_message_backup_by_message_id(message.id)
            if existing_backup:
                logger.debug(f"消息已备份，跳过: {message.id}")
                return
            
            # 处理消息和附件
            await self.process_message_backup(message, config_id, content_type)
            
            # 更新最后活动时间
            await self.db_manager.update_last_activity_time(datetime.now(timezone.utc))
            
        except Exception as e:
            logger.error(f"处理消息失败: {e}")
    
    async def backup_message(self, message: discord.Message, config_id: int) -> bool:
        """手动备份单个消息，返回成功状态"""
        try:
            # 确定内容类型
            if isinstance(message.channel, discord.Thread):
                content_type = "thread"
            else:
                content_type = "channel"
            
            # 调用备份处理函数
            result = await self.process_message_backup(message, config_id, content_type)
            
            # 更新最后活动时间
            await self.db_manager.update_last_activity_time(datetime.now(timezone.utc))
            
            return result is not False  # 如果没有明确返回 False，则认为成功
            
        except Exception as e:
            logger.error(f"手动备份消息失败: {e}")
            return False
    
    async def process_message_backup(self, message: discord.Message, config_id: int, content_type: str):
        """处理消息备份"""
        try:
            # 确定正确的存储ID
            if isinstance(message.channel, discord.Thread):
                storage_id = message.channel.id  # 帖子ID
            else:
                storage_id = message.channel.id  # 频道ID
            
            # 保存消息信息
            message_backup_id = await self.db_manager.save_message_backup(
                config_id=config_id,
                message_id=message.id,
                content=message.content or "",
                created_at=message.created_at,
                content_type=content_type
            )
            
            if not message_backup_id:
                logger.error(f"保存消息备份失败: {message.id}")
                return False
            
            # 处理附件
            if message.attachments:
                attachment_count = 0
                for attachment in message.attachments:
                    result = await self.process_attachment(
                        attachment, message_backup_id, message.guild.id, message.author.id, 
                        storage_id, message.created_at
                    )
                    if result:
                        attachment_count += 1
                
                logger.info(f"消息 {message.id} 备份完成: {attachment_count}/{len(message.attachments)} 个附件")
            else:
                logger.debug(f"消息 {message.id} 无附件，仅保存文本")
            
            return True  # 备份成功
            
        except Exception as e:
            logger.error(f"处理消息备份失败: {e}")
            return False
    
    async def process_attachment(self, attachment, message_backup_id: int, guild_id: int, author_id: int, 
                               thread_id: int, message_timestamp: datetime) -> bool:
        """处理单个附件"""
        try:
            # 下载并上传到WebDAV
            result = await self.file_manager.download_and_upload_attachment(
                attachment, guild_id, author_id, thread_id, message_timestamp
            )
            
            if not result:
                logger.warning(f"附件处理失败: {attachment.filename}")
                return False
            
            webdav_path, original_filename, file_size = result
            
            # 保存附件备份记录
            file_backup_id = await self.db_manager.save_file_backup(
                message_backup_id=message_backup_id,
                original_filename=original_filename,
                stored_filename=webdav_path,
                file_size=file_size,
                file_url=attachment.url,
                webdav_path=webdav_path
            )
            
            if file_backup_id:
                logger.info(f"附件备份成功: {original_filename} -> {webdav_path}")
                return True
            else:
                logger.error(f"附件备份记录保存失败: {original_filename}")
                return False
            
        except Exception as e:
            logger.error(f"处理附件失败 {attachment.filename}: {e}")
            return False
    
    async def send_notification_card(self, guild_id: int, channel_id: int, thread_id: Optional[int], 
                                   author_id: int, action: str):
        """发送通知卡片（3分钟后删除）"""
        try:
            # 获取目标频道或帖子
            guild = self.bot.get_guild(guild_id)
            if not guild:
                logger.error(f"找不到服务器: {guild_id}")
                return
            
            if thread_id:
                # 帖子通知
                channel = guild.get_channel(channel_id)
                if not channel:
                    logger.error(f"找不到频道: {channel_id}")
                    return
                
                thread = channel.get_thread(thread_id)
                if not thread:
                    logger.error(f"找不到帖子: {thread_id}")
                    return
                
                target = thread
                location_type = "帖子"
            else:
                # 频道通知
                channel = guild.get_channel(channel_id)
                if not channel:
                    logger.error(f"找不到频道: {channel_id}")
                    return
                
                target = channel
                location_type = "频道"
            
            # 获取用户信息
            user = guild.get_member(author_id) or await guild.fetch_member(author_id)
            if not user:
                logger.error(f"找不到用户: {author_id}")
                return
            
            # 创建通知消息
            if action == "enable":
                embed = discord.Embed(
                    title="✅ 备份功能已启用",
                    description=f"{user.mention} 您好！根据协议授权，已为您在此{location_type}启用备份功能。",
                    color=discord.Color.green(),
                    timestamp=datetime.now(timezone.utc)
                )
                embed.add_field(
                    name="📝 备份说明", 
                    value="• 系统将自动备份您发布的消息和附件\n• 仅备份您自己的内容\n• 备份数据安全存储", 
                    inline=False
                )
            else:  # disable
                embed = discord.Embed(
                    title="⏸️ 备份功能已暂停",
                    description=f"{user.mention} 您好！根据协议设置，已暂停您在此{location_type}的备份功能。",
                    color=discord.Color.orange(),
                    timestamp=datetime.now(timezone.utc)
                )
                embed.add_field(
                    name="📝 说明", 
                    value="• 已停止新内容的备份\n• 之前的备份内容保持不变\n• 可随时重新启用", 
                    inline=False
                )
            
            embed.set_footer(text="此消息将在3分钟后自动删除")
            
            # 发送消息
            message = await target.send(embed=embed)
            
            # 3分钟后删除
            asyncio.create_task(self.delete_message_after_delay(message, 180))
            
            logger.info(f"通知消息已发送: {action} 在 {location_type} {target.name}")
            
        except Exception as e:
            logger.error(f"发送通知失败: {e}")
    
    async def delete_message_after_delay(self, message: discord.Message, delay: int):
        """延迟删除消息"""
        try:
            await asyncio.sleep(delay)
            await message.delete()
            logger.debug(f"已删除通知消息: {message.id}")
        except discord.NotFound:
            logger.debug("消息已被删除")
        except discord.Forbidden:
            logger.warning("没有权限删除消息")
        except Exception as e:
            logger.error(f"删除消息失败: {e}")
    
    async def scan_history(self, guild_id: int, channel_id: int, thread_id: Optional[int], 
                         author_id: int, config_id: int, start_time: Optional[datetime] = None) -> Tuple[int, int]:
        """
        扫描历史消息
        
        Returns:
            Tuple[扫描消息数, 下载文件数]
        """
        try:
            guild = self.bot.get_guild(guild_id)
            if not guild:
                logger.error(f"找不到服务器: {guild_id}")
                return 0, 0
            
            if thread_id:
                # 扫描帖子
                channel = guild.get_channel(channel_id)
                if not channel:
                    logger.error(f"找不到频道: {channel_id}")
                    return 0, 0
                
                thread = channel.get_thread(thread_id)
                if not thread:
                    logger.error(f"找不到帖子: {thread_id}")
                    return 0, 0
                
                target = thread
                content_type = "thread"
                
                # 检查帖子消息数量
                message_count = 0
                async for _ in thread.history(limit=None):
                    message_count += 1
                    if message_count > 10000:
                        logger.warning(f"帖子消息数量超过10000，跳过历史扫描: {thread_id}")
                        return 0, 0
                
            else:
                # 扫描频道
                channel = guild.get_channel(channel_id)
                if not channel:
                    logger.error(f"找不到频道: {channel_id}")
                    return 0, 0
                
                target = channel
                content_type = "channel"
            
            # 开始扫描
            scanned_count = 0
            downloaded_count = 0
            
            # 设置扫描起始时间
            after = start_time
            
            logger.info(f"开始历史扫描: {target.name}, 起始时间: {after}")
            
            async for message in target.history(limit=None, after=after, oldest_first=True):
                # 只处理目标作者的消息
                if message.author.id != author_id or message.author.bot:
                    continue
                
                scanned_count += 1
                
                # 检查消息是否已备份
                existing_backup = await self.db_manager.get_message_backup_by_message_id(message.id)
                if existing_backup:
                    continue
                
                # 备份消息
                await self.process_message_backup(message, config_id, content_type)
                
                # 统计下载的文件数
                if message.attachments:
                    downloaded_count += len(message.attachments)
                
                # 避免过于频繁的操作
                if scanned_count % 10 == 0:
                    await asyncio.sleep(0.1)
            
            # 更新配置的最后检查时间
            await self.db_manager.update_backup_config_check_time(config_id)
            
            logger.info(f"历史扫描完成: 扫描 {scanned_count} 条消息, 下载 {downloaded_count} 个文件")
            return scanned_count, downloaded_count
            
        except Exception as e:
            logger.error(f"历史扫描失败: {e}")
            return 0, 0
    
    async def scan_thread_content(self, thread: discord.Thread, author_id: int) -> Tuple[str, str, List[str]]:
        """
        扫描帖子内容（标题、首楼内容、作者附件列表）
        
        Returns:
            Tuple[帖子标题, 首楼内容, 附件URL列表]
        """
        try:
            title = thread.name or "无标题"
            first_message_content = ""
            attachment_urls = []
            
            # 获取首条消息（可能需要特殊处理）
            async for message in thread.history(limit=None, oldest_first=True):
                if message.author.id == author_id and not message.author.bot:
                    if not first_message_content:
                        first_message_content = message.content or ""
                    
                    # 收集附件URL
                    for attachment in message.attachments:
                        attachment_urls.append(attachment.url)
            
            logger.info(f"扫描帖子内容完成: {title}, 首楼长度: {len(first_message_content)}, 附件数: {len(attachment_urls)}")
            return title, first_message_content, attachment_urls
            
        except Exception as e:
            logger.error(f"扫描帖子内容失败: {e}")
            return "", "", []
    
    async def handle_message_edit(self, before: discord.Message, after: discord.Message):
        """处理消息编辑事件"""
        # 忽略机器人消息
        if after.author.bot:
            return
        
        # 只有内容发生变化才处理
        if before.content == after.content:
            return
        
        try:
            # 确定位置信息
            if isinstance(after.channel, discord.Thread):
                thread_id = after.channel.id
                channel_id = after.channel.parent.id
                content_type = "thread"
            else:
                thread_id = None
                channel_id = after.channel.id
                content_type = "channel"
            
            # 检查是否有备份配置
            backup_config = await self.db_manager.get_backup_config(
                after.guild.id, channel_id, thread_id, after.author.id
            )
            
            if not backup_config:
                return  # 没有配置，不处理
            
            # 检查消息是否已备份
            existing_backup = await self.db_manager.get_message_backup_by_message_id(after.id)
            if not existing_backup:
                # 消息未备份，按新消息处理
                await self.handle_message(after)
                return
            
            # 更新已有备份的内容
            await self.update_message_backup_content(after.id, after.content)
            
            # 更新最后活动时间
            await self.db_manager.update_last_activity_time(datetime.now(timezone.utc))
            
            logger.info(f"消息编辑备份已更新: {after.id}")
            
        except Exception as e:
            logger.error(f"处理消息编辑失败: {e}")
    
    async def update_message_backup_content(self, message_id: int, new_content: str):
        """更新消息备份的内容"""
        try:
            import aiosqlite
            async with aiosqlite.connect(self.db_manager.db_path) as db:
                await db.execute('''
                    UPDATE message_backups 
                    SET content = ?, backup_time = CURRENT_TIMESTAMP 
                    WHERE message_id = ?
                ''', (new_content, message_id))
                await db.commit()
                logger.debug(f"更新消息内容: {message_id}")
        except Exception as e:
            logger.error(f"更新消息备份内容失败: {e}")