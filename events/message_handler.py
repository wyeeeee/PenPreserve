import discord
import logging
import asyncio
from datetime import datetime, timezone
from typing import Optional, Tuple
from utils.file_manager import FileManager

logger = logging.getLogger(__name__)

class MessageHandler:
    def __init__(self, bot, db_manager, config):
        self.bot = bot
        self.db_manager = db_manager
        self.config = config
        self.file_manager = FileManager(
            downloads_dir="downloads",
            max_file_size=config.max_file_size
        )
    
    async def handle_message(self, message: discord.Message):
        """处理新消息 - 简化版"""
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
            
            # 记录活动（更新最后检查时间）
            await self.db_manager.update_config_check_time(config_id)
            
            # 检查并下载附件
            if message.attachments:
                await self.process_attachments(message, config_id, location_id)
            
            # 如果是帖子的首条消息，保存内容信息
            if content_type == "thread" and self.is_first_message(message):
                await self.save_thread_content(message, config_id)
            
            logger.debug(f"处理消息完成: {message.id} (作者: {message.author.name})")
            
        except Exception as e:
            logger.error(f"处理消息失败 {message.id}: {e}")
    
    async def process_attachments(self, message: discord.Message, config_id: int, location_id: int):
        """处理消息附件"""
        for attachment in message.attachments:
            try:
                # 检查是否已下载
                if await self.db_manager.is_file_downloaded(message.id, attachment.filename):
                    logger.debug(f"文件已下载，跳过: {attachment.filename}")
                    continue
                
                # 下载文件
                download_result = await self.file_manager.download_discord_attachment(
                    attachment, message.author.id, location_id
                )
                
                if download_result:
                    saved_filename, file_path, file_size = download_result
                    
                    # 记录到数据库
                    await self.db_manager.record_file_download(
                        config_id, message.id, attachment.filename,
                        saved_filename, file_path, file_size
                    )
                    
                    logger.info(f"下载附件: {attachment.filename} -> {saved_filename} ({self.file_manager.format_file_size(file_size)})")
                else:
                    logger.warning(f"下载附件失败: {attachment.filename}")
                    
            except Exception as e:
                logger.error(f"处理附件失败 {attachment.filename}: {e}")
    
    async def save_thread_content(self, message: discord.Message, config_id: int):
        """保存帖子内容信息"""
        try:
            # 获取帖子标题和首楼内容
            thread_title = message.channel.name
            first_post_content = message.content[:1000] if message.content else None  # 限制长度
            
            # 保存内容记录
            await self.db_manager.save_content_record(
                config_id=config_id,
                content_type="thread",
                title=thread_title,
                first_post_content=first_post_content,
                author_name=message.author.name,
                author_display_name=message.author.display_name or message.author.name
            )
            
            logger.info(f"保存帖子内容: {thread_title}")
            
        except Exception as e:
            logger.error(f"保存帖子内容失败: {e}")
    
    def is_first_message(self, message: discord.Message) -> bool:
        """检查是否是帖子的第一条消息"""
        if not isinstance(message.channel, discord.Thread):
            return False
        
        # 简单判断：消息ID接近帖子ID说明是首条消息
        thread_id = message.channel.id
        message_id = message.id
        id_diff = abs(message_id - thread_id)
        
        # ID差异小于1000通常表示是首条消息
        return id_diff < 1000
    
    async def scan_history(self, guild_id: int, channel_id: int, thread_id: Optional[int], 
                          author_id: int, config_id: int, after_time: Optional[datetime] = None) -> Tuple[int, int]:
        """扫描历史消息 - 简化版"""
        try:
            # 获取Discord对象
            guild = self.bot.get_guild(guild_id)
            if not guild:
                logger.error(f"找不到服务器: {guild_id}")
                return 0, 0
            
            channel = guild.get_channel(channel_id)
            if not channel:
                logger.error(f"找不到频道: {channel_id}")
                return 0, 0
            
            # 如果是帖子，获取帖子对象
            if thread_id:
                thread = channel.get_thread(thread_id)
                if not thread:
                    logger.error(f"找不到帖子: {thread_id}")
                    return 0, 0
                scan_channel = thread
                location_id = thread_id
                content_type = "thread"
            else:
                scan_channel = channel
                location_id = channel_id
                content_type = "channel"
            
            logger.info(f"开始扫描历史: {scan_channel.name} (作者: {author_id})")
            
            scanned_count = 0
            downloaded_count = 0
            
            # 扫描历史消息
            async for message in scan_channel.history(limit=self.config.max_scan_messages):
                scanned_count += 1
                
                # 只处理指定作者的消息
                if message.author.id != author_id:
                    continue
                
                # 如果指定了时间，只处理该时间之后的消息
                if after_time and message.created_at <= after_time:
                    continue
                
                # 处理附件
                if message.attachments:
                    for attachment in message.attachments:
                        if not await self.db_manager.is_file_downloaded(message.id, attachment.filename):
                            download_result = await self.file_manager.download_discord_attachment(
                                attachment, author_id, location_id
                            )
                            
                            if download_result:
                                saved_filename, file_path, file_size = download_result
                                await self.db_manager.record_file_download(
                                    config_id, message.id, attachment.filename,
                                    saved_filename, file_path, file_size
                                )
                                downloaded_count += 1
                                logger.debug(f"历史下载: {attachment.filename}")
                
                # 如果是帖子的首条消息，保存内容
                if content_type == "thread" and self.is_first_message(message):
                    await self.save_thread_content(message, config_id)
                
                # 避免过于频繁的API调用
                if scanned_count % 50 == 0:
                    await asyncio.sleep(1)
            
            # 更新检查时间
            await self.db_manager.update_config_check_time(config_id)
            
            logger.info(f"历史扫描完成: 扫描 {scanned_count} 条，下载 {downloaded_count} 个文件")
            return scanned_count, downloaded_count
            
        except Exception as e:
            logger.error(f"历史扫描失败: {e}")
            return 0, 0
    
    async def send_notification_card(self, guild_id: int, channel_id: int, thread_id: Optional[int],
                                   author_id: int, action: str, work_title: str = ""):
        """发送通知卡片"""
        try:
            # 获取Discord对象
            guild = self.bot.get_guild(guild_id)
            if not guild:
                return
            
            channel = guild.get_channel(channel_id)
            if not channel:
                return
            
            if thread_id:
                thread = channel.get_thread(thread_id)
                if thread:
                    channel = thread
                else:
                    return
            
            # 获取用户对象
            user = guild.get_member(author_id)
            if not user:
                try:
                    user = await self.bot.fetch_user(author_id)
                except:
                    user = None
            
            # 创建美观的卡片消息
            if action == "enable":
                embed = discord.Embed(
                    title="🔒 此作品已启用备份功能",
                    description="系统将自动备份您在此位置上传的文件",
                    color=discord.Color.green()
                )
                embed.add_field(
                    name="📁 备份内容",
                    value="• 您上传的所有文件和附件\n• 帖子的标题和首楼内容\n• 文件的原始信息和元数据",
                    inline=False
                )
                embed.add_field(
                    name="⚖️ 版权声明",
                    value="• 本系统仅提供备份存储服务，您的作品版权完全属于您本人，未经您同意，本系统不会以任何形式使用您的作品。",
                    inline=False
                )
                embed.set_footer(text="PenPreserve • 让作品永久保存")
                embed.timestamp = datetime.now(timezone.utc)
                
            else:
                embed = discord.Embed(
                    title="⏸️ 此作品已停用备份功能",
                    description="系统已停止备份您在此位置上传的文件",
                    color=discord.Color.orange()
                )
                embed.add_field(
                    name="📂 现有备份",
                    value="• 已备份的文件将继续保留\n• 可随时重新启用备份功能",
                    inline=False
                )
                embed.add_field(
                    name="⚖️ 版权声明",
                    value="• 本系统仅提供备份存储服务，您的作品版权完全属于您本人，未经您同意，本系统不会以任何形式使用您的作品。",
                    inline=False
                )
                embed.set_footer(text="PenPreserve • 让作品永久保存")
                embed.timestamp = datetime.now(timezone.utc)
            
            # 发送卡片消息
            await channel.send(embed=embed)
            logger.info(f"发送通知卡片: {action} 给 {author_id}")
            
        except Exception as e:
            logger.error(f"发送通知卡片失败: {e}")
    
    def get_content_preview(self, content: str) -> str:
        """获取内容预览"""
        if not content:
            return "[空消息]"
        
        preview = content.replace('\n', ' ').replace('\r', ' ').strip()
        return preview[:100] + "..." if len(preview) > 100 else preview