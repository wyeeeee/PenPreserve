import discord
import logging
import json
import asyncio
from datetime import datetime
from utils.helpers import download_file, is_allowed_extension, format_file_size
from utils.rate_limiter import rate_limiter

logger = logging.getLogger(__name__)

class MessageHandler:
    def __init__(self, bot, db_manager, config):
        self.bot = bot
        self.db_manager = db_manager
        self.config = config
    
    async def handle_message(self, message):
        """处理新消息"""
        # 忽略机器人消息
        if message.author.bot:
            return
        
        # 记录所有接收到的消息
        logger.info(f"接收消息: {message.id}, 作者: {message.author.name}, 频道: {message.channel.name}, 类型: {type(message.channel).__name__}")
        
        # 正确识别频道和帖子
        if isinstance(message.channel, discord.Thread):
            # 消息在帖子中
            thread_id = message.channel.id
            channel_id = message.channel.parent.id
        else:
            # 消息在普通频道中
            thread_id = None
            channel_id = message.channel.id
        
        # 检查是否有备份配置
        backup_config = await self.db_manager.get_backup_config(
            message.guild.id,
            channel_id,
            thread_id,
            message.author.id
        )
        
        if not backup_config:
            logger.info(f"未找到备份配置 - 频道: {channel_id}, 帖子: {thread_id}, 作者: {message.author.id}")
            return
        
        logger.info(f"处理新消息: {message.id}, 作者: {message.author.name}, 频道: {channel_id}, 帖子: {thread_id}")
        
        # 获取内容类型和备份规则
        content_type_info = await self.db_manager.get_content_type_by_config(backup_config[0])
        backup_rules = {}
        if content_type_info:
            backup_rules = json.loads(content_type_info[2])  # backup_rules字段
        
        # 备份消息
        await self._backup_message(message, backup_config[0], backup_rules)
    
    async def _backup_message(self, message, config_id, backup_rules=None):
        """备份单个消息"""
        try:
            if backup_rules is None:
                backup_rules = {}
            
            # 检查是否应该备份此消息
            if not self._should_backup_message(message, backup_rules):
                return
            
            # 根据内容类型处理不同的备份逻辑
            content_to_backup = self._get_content_to_backup(message, backup_rules)
            
            # 备份消息内容
            message_backup_id = await self.db_manager.backup_message(
                config_id,
                message.id,
                message.author.id,
                content_to_backup,
                message.created_at
            )
            
            if not message_backup_id:
                return
            
            # 备份附件（如果规则允许）
            if backup_rules.get('backup_attachments', True) and message.attachments:
                await self._backup_attachments(message.attachments, message_backup_id)
            
            # 备份嵌入内容中的文件
            if message.embeds:
                await self._backup_embeds(message.embeds, message_backup_id)
            
            logger.info(f"成功备份消息: {message.id}")
            
        except Exception as e:
            logger.error(f"备份消息失败: {message.id}, 错误: {e}")
    
    def _should_backup_message(self, message, backup_rules):
        """检查是否应该备份此消息"""
        # 如果规则中指定只备份作者消息，且当前消息不是作者的，则跳过
        if backup_rules.get('backup_author_posts_only', False) or backup_rules.get('backup_author_messages_only', False):
            # 这个检查已经在上层处理了，这里总是返回True
            return True
        
        # 其他规则检查
        return True
    
    def _get_content_to_backup(self, message, backup_rules):
        """根据备份规则获取要备份的内容"""
        content = message.content
        
        # 如果是帖子，处理特殊逻辑
        if isinstance(message.channel, discord.Thread):
            # 获取帖子标题
            thread_title = message.channel.name
            
            # 如果是第一条消息且需要备份帖子标题
            if backup_rules.get('backup_thread_title', False):
                if not content.startswith(thread_title):
                    content = f"[帖子标题: {thread_title}]\n{content}"
            
            # 如果是第一条消息且需要备份顶楼内容
            if backup_rules.get('backup_first_post', False):
                # 这里可以添加特殊标记来标识这是顶楼内容
                if self._is_first_post(message):
                    content = f"[顶楼内容]\n{content}"
        
        # 如果是频道，处理特殊逻辑
        elif backup_rules.get('backup_channel_name', False):
            channel_name = message.channel.name
            content = f"[频道: {channel_name}]\n{content}"
        
        return content
    
    def _is_first_post(self, message):
        """检查是否是帖子的第一条消息"""
        # 这个检查比较复杂，需要获取帖子历史
        # 简单起见，这里返回True，实际应用中可以优化
        return True
    
    async def _backup_attachments(self, attachments, message_backup_id):
        """备份附件"""
        for attachment in attachments:
            if not is_allowed_extension(attachment.filename, self.config.allowed_extensions):
                logger.info(f"跳过不允许的文件类型: {attachment.filename}")
                continue
            
            if attachment.size > self.config.max_file_size:
                logger.info(f"跳过过大的文件: {attachment.filename}, 大小: {format_file_size(attachment.size)}")
                continue
            
            # 下载文件
            file_data = await download_file(attachment.url, self.config.max_file_size)
            
            # 备份文件信息
            await self.db_manager.backup_file(
                message_backup_id,
                attachment.filename,
                attachment.size,
                attachment.url,
                file_data
            )
            
            logger.info(f"备份附件: {attachment.filename}")
    
    async def _backup_embeds(self, embeds, message_backup_id):
        """备份嵌入内容"""
        for embed in embeds:
            # 备份嵌入的图片
            if embed.image:
                await self._backup_embed_media(embed.image.url, message_backup_id, "embed_image")
            
            # 备份嵌入的缩略图
            if embed.thumbnail:
                await self._backup_embed_media(embed.thumbnail.url, message_backup_id, "embed_thumbnail")
    
    async def _backup_embed_media(self, url, message_backup_id, media_type):
        """备份嵌入媒体"""
        try:
            # 简单的文件名生成
            filename = f"{media_type}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jpg"
            
            # 下载文件
            file_data = await download_file(url, self.config.max_file_size)
            
            if file_data:
                await self.db_manager.backup_file(
                    message_backup_id,
                    filename,
                    len(file_data),
                    url,
                    file_data
                )
                logger.info(f"备份嵌入媒体: {filename}")
        except Exception as e:
            logger.error(f"备份嵌入媒体失败: {url}, 错误: {e}")
    
    async def scan_channel_history(self, channel, author_id, config_id, limit=None, after_time=None):
        """扫描频道历史消息"""
        if limit is None:
            limit = self.config.max_scan_messages
        
        logger.info(f"开始扫描频道历史: {channel.name}, 作者: {author_id}, 限制: {limit}")
        if after_time:
            logger.info(f"只扫描 {after_time} 之后的消息")
        
        scanned_count = 0
        backed_up_count = 0
        
        try:
            # 获取备份规则
            content_type_info = await self.db_manager.get_content_type_by_config(config_id)
            backup_rules = {}
            if content_type_info:
                backup_rules = json.loads(content_type_info[2])
            
            # 获取最新备份的消息时间（除非指定了after_time）
            if not after_time:
                latest_time = await self.db_manager.get_latest_message_time(config_id)
            else:
                latest_time = after_time.isoformat() if isinstance(after_time, datetime) else after_time
            
            # 特殊处理：如果是帖子，需要特别处理第一条消息
            if isinstance(channel, discord.Thread) and backup_rules.get('backup_first_post', False):
                await self._backup_thread_first_post(channel, author_id, config_id, backup_rules)
            
            # 使用速率限制的消息历史获取
            async for message in self._get_channel_history_with_rate_limit(channel, limit):
                scanned_count += 1
                
                # 只备份指定作者的消息
                if message.author.id != author_id:
                    continue
                
                # 如果消息时间早于指定时间，跳过
                if latest_time:
                    compare_time = datetime.fromisoformat(latest_time) if isinstance(latest_time, str) else latest_time
                    if message.created_at <= compare_time:
                        continue
                
                # 备份消息
                await self._backup_message(message, config_id, backup_rules)
                backed_up_count += 1
                
                # 避免超过API限制
                if scanned_count >= limit:
                    logger.warning(f"达到扫描限制: {limit}")
                    break
                
                # 在消息之间添加小延迟
                await asyncio.sleep(0.1)
            
            # 更新最后扫描时间
            await self.db_manager.update_last_scan_time(config_id)
            
            logger.info(f"扫描完成: 扫描 {scanned_count} 条消息, 备份 {backed_up_count} 条消息")
            
        except Exception as e:
            logger.error(f"扫描频道历史失败: {e}")
        
        return scanned_count, backed_up_count
    
    async def _backup_thread_first_post(self, thread, author_id, config_id, backup_rules):
        """备份帖子的第一条消息"""
        try:
            # 获取帖子的第一条消息
            async for message in thread.history(limit=1, oldest_first=True):
                if message.author.id == author_id:
                    logger.info(f"备份帖子首条消息: {message.id}")
                    await self._backup_message(message, config_id, backup_rules)
                break
        except Exception as e:
            logger.error(f"备份帖子首条消息失败: {e}")
    
    async def _get_channel_history_with_rate_limit(self, channel, limit):
        """使用速率限制获取频道历史"""
        try:
            await rate_limiter.wait_for_rate_limit(f"/channels/{channel.id}/messages", "GET")
            
            batch_size = min(100, limit)  # Discord API单次最多100条消息
            processed = 0
            
            async for message in channel.history(limit=batch_size, oldest_first=False):
                yield message
                processed += 1
                
                # 每处理一批消息后稍作等待
                if processed % 50 == 0:
                    await asyncio.sleep(1)
                    
                if processed >= limit:
                    break
                    
        except discord.HTTPException as e:
            if e.status == 429:  # Too Many Requests
                retry_after = int(e.response.headers.get('Retry-After', 5))
                logger.warning(f"遇到速率限制，等待 {retry_after} 秒")
                await asyncio.sleep(retry_after)
                # 递归重试
                async for message in self._get_channel_history_with_rate_limit(channel, limit):
                    yield message
            else:
                raise 