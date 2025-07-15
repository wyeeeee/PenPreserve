import discord
from discord.ext import commands
import logging
import asyncio
from datetime import datetime, timezone, timedelta
from database.models import DatabaseManager
from events.message_handler import MessageHandler
from server.webhook_server import get_webhook_server
from utils.reconnect_manager import ReconnectManager

logger = logging.getLogger(__name__)

class DiscordBot(commands.Bot):
    def __init__(self, config):
        self.config = config
        
        # 设置Bot意图
        intents = discord.Intents.none()
        intents.guilds = True
        intents.messages = True
        intents.message_content = True
        
        # 初始化Bot
        super().__init__(
            command_prefix=config.prefix,
            description=config.description,
            intents=intents
        )
        
        # 初始化组件
        self.db_manager = DatabaseManager(config.db_filename)
        self.message_handler = MessageHandler(self, self.db_manager, config)
        
        # 状态变量
        self.startup_time = None
        self.last_shutdown_time = None
        self.webhook_processor_running = False
        self._shutdown_in_progress = False
        
        # 重连管理器
        self.reconnect_manager = ReconnectManager(self)
    
    async def setup_hook(self):
        """Bot启动时的设置"""
        logger.info("开始设置Bot...")
        
        # 初始化数据库
        await self.db_manager.init_db()
        
        # 加载命令
        await self.load_extension('commands.backup_commands')
        
        # 同步命令树
        try:
            synced = await self.tree.sync()
            logger.info(f"同步了 {len(synced)} 个斜杠命令")
        except Exception as e:
            logger.error(f"同步命令失败: {e}")
        
        logger.info("Bot设置完成")
    
    async def on_ready(self):
        """当Bot准备就绪时"""
        self.startup_time = datetime.now(timezone.utc)
        logger.info(f"Bot已登录: {self.user.name} (ID: {self.user.id})")
        logger.info(f"已连接到 {len(self.guilds)} 个服务器")
        
        # 启动时更新活动时间
        await self.db_manager.update_last_activity_time(self.startup_time)
        
        # 获取最后活动时间（用于宕机恢复）
        self.last_activity_time = await self.db_manager.get_last_activity_time()
        
        # 设置Bot状态
        await self.set_activity()
        
        # 启动后台任务
        self.start_background_tasks()
        
        # 显示统计信息
        configs = await self.db_manager.get_all_backup_configs()
        logger.info(f"当前有 {len(configs)} 个活跃备份配置")
        
        logger.info("Bot启动完成")
    
    def start_background_tasks(self):
        """启动后台任务"""
        # 宕机恢复任务
        asyncio.create_task(self.handle_downtime_recovery())
        
        # Webhook通知处理任务
        if get_webhook_server():
            asyncio.create_task(self.process_webhook_notifications())
            self.webhook_processor_running = True
        
        logger.info("后台任务已启动")
    
    async def set_activity(self):
        """设置Bot活动状态"""
        try:
            activity = discord.Activity(
                type=discord.ActivityType.watching,
                name="文件备份系统"
            )
            await self.change_presence(activity=activity)
            logger.info("设置活动状态完成")
        except Exception as e:
            logger.error(f"设置活动状态失败: {e}")
    
    async def handle_downtime_recovery(self):
        """处理宕机恢复 - 基于最后活动时间"""
        try:
            await asyncio.sleep(2)  # 等待Bot完全启动
            
            if not self.last_activity_time:
                logger.info("首次启动或无活动记录，跳过宕机恢复")
                return
            
            # 解析最后活动时间
            if isinstance(self.last_activity_time, str):
                last_activity = datetime.fromisoformat(self.last_activity_time)
            else:
                last_activity = self.last_activity_time
            
            if last_activity.tzinfo is None:
                last_activity = last_activity.replace(tzinfo=timezone.utc)
            
            # 计算离线时长
            offline_duration = self.startup_time - last_activity
            
            # 只有离线超过5分钟才进行恢复
            if offline_duration.total_seconds() < 300:
                logger.info(f"离线时间较短({offline_duration})，跳过恢复")
                return
            
            logger.info(f"检测到长时间离线，开始恢复，离线时长: {offline_duration}")
            
            # 获取所有配置并并发恢复
            configs = await self.db_manager.get_all_backup_configs()
            if not configs:
                logger.info("没有备份配置，跳过恢复")
                return
            
            recovery_tasks = []
            for config in configs:
                task = asyncio.create_task(self.recover_single_config(config, last_activity))
                recovery_tasks.append(task)
            
            # 等待所有恢复任务完成
            if recovery_tasks:
                results = await asyncio.gather(*recovery_tasks, return_exceptions=True)
                success_count = sum(1 for r in results if not isinstance(r, Exception))
                logger.info(f"宕机恢复完成: {success_count}/{len(configs)} 个配置恢复成功")
            
        except Exception as e:
            logger.error(f"宕机恢复失败: {e}")
    
    async def recover_single_config(self, config, last_activity_time):
        """恢复单个配置"""
        try:
            config_id, guild_id, channel_id, thread_id, author_id = config[:5]
            
            # 获取该配置的最后检查时间
            last_check = await self.db_manager.get_latest_message_time(config_id)
            
            if last_check:
                if isinstance(last_check, str):
                    recovery_time = datetime.fromisoformat(last_check)
                else:
                    recovery_time = last_check
                
                if recovery_time.tzinfo is None:
                    recovery_time = recovery_time.replace(tzinfo=timezone.utc)
            else:
                recovery_time = last_activity_time
            
            # 执行历史扫描
            scanned, downloaded = await self.message_handler.scan_history(
                guild_id, channel_id, thread_id, author_id, config_id, recovery_time
            )
            
            if downloaded > 0:
                logger.info(f"配置 {config_id} 恢复完成: 下载 {downloaded} 个文件")
            
            return True
            
        except Exception as e:
            logger.error(f"恢复配置 {config[0]} 失败: {e}")
            return False
    
    async def process_webhook_notifications(self):
        """处理Webhook通知队列"""
        webhook_server = get_webhook_server()
        if not webhook_server:
            logger.warning("Webhook服务器未找到，跳过通知处理")
            return
        
        logger.info("开始处理Webhook通知")
        
        while self.webhook_processor_running:
            try:
                # 获取通知
                notification = await webhook_server.get_notification()
                if not notification:
                    await asyncio.sleep(5)  # 没有通知时等待
                    continue
                
                # 处理通知
                await self.handle_webhook_notification(notification)
                
            except Exception as e:
                logger.error(f"处理Webhook通知失败: {e}")
                await asyncio.sleep(5)
    
    async def handle_webhook_notification(self, notification):
        """处理单个Webhook通知"""
        try:
            action = notification.get("action")
            config_id = notification.get("config_id")
            guild_id = notification.get("guild_id")
            channel_id = notification.get("channel_id")
            thread_id = notification.get("thread_id")
            author_id = notification.get("author_id")
            
            logger.info(f"处理Webhook通知: {action} 配置 {config_id}")
            
            if action == "enable":
                # 发送开启通知
                await self.message_handler.send_notification_card(
                    guild_id, channel_id, thread_id, author_id, "enable"
                )
                
                
                # 执行历史扫描
                scanned, downloaded = await self.message_handler.scan_history(
                    guild_id, channel_id, thread_id, author_id, config_id
                )
                
                logger.info(f"备份启用完成: 配置 {config_id}, 扫描 {scanned} 条, 下载 {downloaded} 个文件")
                
            elif action == "disable":
                # 发送暂停通知
                await self.message_handler.send_notification_card(
                    guild_id, channel_id, thread_id, author_id, "disable"
                )
                
                logger.info(f"备份暂停完成: 配置 {config_id}")
            
        except Exception as e:
            logger.error(f"处理Webhook通知失败: {e}")
    
    
    async def on_message(self, message):
        """处理消息事件"""
        # 处理备份
        await self.message_handler.handle_message(message)
        
        # 处理命令
        await self.process_commands(message)
    
    async def on_message_edit(self, before, after):
        """处理消息编辑事件"""
        # 处理消息编辑的备份更新
        await self.message_handler.handle_message_edit(before, after)
    
    async def on_thread_update(self, before, after):
        """处理帖子更新事件（包括标题变更）"""
        try:
            # 如果帖子名称发生变化
            if before.name != after.name:
                # 获取该帖子的所有备份配置
                configs = await self.db_manager.get_backup_config_by_location(
                    after.guild.id, after.parent.id, after.id
                )
                
                # 更新所有相关配置的标题
                for config in configs:
                    config_id = config[0]
                    await self.db_manager.update_backup_config_title(config_id, after.name)
                
                if configs:
                    logger.info(f"帖子标题更新: {before.name} -> {after.name}, 影响 {len(configs)} 个配置")
                    
        except Exception as e:
            logger.error(f"处理帖子更新失败: {e}")
    
    async def on_guild_channel_update(self, before, after):
        """处理频道更新事件（包括频道名称变更）"""
        try:
            # 如果频道名称发生变化
            if before.name != after.name:
                # 获取该频道的所有备份配置
                configs = await self.db_manager.get_backup_config_by_location(
                    after.guild.id, after.id, None
                )
                
                # 更新所有相关配置的标题
                for config in configs:
                    config_id = config[0]
                    await self.db_manager.update_backup_config_title(config_id, after.name)
                
                if configs:
                    logger.info(f"频道标题更新: {before.name} -> {after.name}, 影响 {len(configs)} 个配置")
                    
        except Exception as e:
            logger.error(f"处理频道更新失败: {e}")
    
    async def on_error(self, event, *args, **kwargs):
        """处理错误事件"""
        import traceback
        logger.error(f"发生错误 - 事件: {event}")
        logger.error(traceback.format_exc())
    
    async def on_disconnect(self):
        """当Bot断开连接时"""
        logger.warning("Bot与Discord断开连接")
    
    async def on_connect(self):
        """当Bot连接到Discord时"""
        logger.info("Bot已连接到Discord")
        # 重置重连计数
        self.reconnect_manager.reset_retry_count()
    
    async def on_resumed(self):
        """当Bot恢复连接时"""
        logger.info("Bot已恢复连接到Discord")
        # 重置重连计数
        self.reconnect_manager.reset_retry_count()
    
    async def on_command_error(self, ctx, error):
        """处理命令错误"""
        if isinstance(error, commands.CommandNotFound):
            return
        
        logger.error(f"命令错误: {error}")
        
        if ctx.interaction:
            try:
                await ctx.interaction.response.send_message("命令执行时发生错误", ephemeral=True)
            except:
                pass
    
    async def close(self):
        """关闭Bot"""
        if self._shutdown_in_progress:
            logger.debug("关闭已在进行中，跳过重复关闭")
            return
            
        self._shutdown_in_progress = True
        logger.info("Bot正在关闭...")
        
        # 停止Webhook处理
        self.webhook_processor_running = False
        
        try:
            await super().close()
            logger.info("Bot关闭完成")
        except Exception as e:
            logger.error(f"Bot关闭异常: {e}")
    
    def run_bot(self):
        """运行Bot"""
        try:
            self.run(self.config.token)
        except Exception as e:
            logger.error(f"Bot运行失败: {e}")
            raise