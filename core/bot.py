import discord
from discord.ext import commands
import logging
import asyncio
from datetime import datetime, timedelta
from database.models import DatabaseManager
from events.message_handler import MessageHandler
from utils.helpers import safe_send_message

logger = logging.getLogger(__name__)

class DiscordBot(commands.Bot):
    def __init__(self, config):
        self.config = config
        
        # 设置Bot意图
        intents = discord.Intents.default()
        intents.message_content = True
        intents.guilds = True
        intents.messages = True
        
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
        self.last_shutdown_time = None
        self.startup_time = None
    
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
        self.startup_time = datetime.now()
        logger.info(f"Bot已登录: {self.user.name} (ID: {self.user.id})")
        logger.info(f"已连接到 {len(self.guilds)} 个服务器")
        
        # 保存启动时间到数据库
        await self.db_manager.save_startup_time(self.startup_time)
        
        # 从数据库获取上次关闭时间
        self.last_shutdown_time = await self.db_manager.get_last_shutdown_time()
        
        # 设置Bot状态
        await self.set_activity()
        
        # 处理宕机恢复
        await self.handle_downtime_recovery()
        
        # 处理待处理的扫描任务
        await self.process_pending_scan_tasks()
        
        # 启动定期扫描任务处理
        self.start_periodic_scan_task_processing()
        
        # 显示当前所有备份配置（用于调试）
        await self.log_backup_configs()
    
    async def log_backup_configs(self):
        """记录所有备份配置（用于调试）"""
        try:
            configs = await self.db_manager.get_all_backup_configs()
            logger.info(f"当前共有 {len(configs)} 个备份配置:")
            for config in configs:
                config_id, guild_id, channel_id, thread_id, author_id, enabled, created_at, last_scan_time = config
                guild = self.get_guild(guild_id)
                guild_name = guild.name if guild else f"未知服务器({guild_id})"
                logger.info(f"  配置ID: {config_id}, 服务器: {guild_name}, 频道ID: {channel_id}, 帖子ID: {thread_id}, 作者ID: {author_id}")
        except Exception as e:
            logger.error(f"记录备份配置失败: {e}")
    
    async def set_activity(self):
        """设置Bot活动状态"""
        try:
            activity_type = getattr(discord.ActivityType, self.config.activity_type, discord.ActivityType.playing)
            activity = discord.Activity(type=activity_type, name=self.config.activity_name)
            await self.change_presence(activity=activity)
            logger.info(f"设置活动状态: {self.config.activity_type} {self.config.activity_name}")
        except Exception as e:
            logger.error(f"设置活动状态失败: {e}")
    
    async def handle_downtime_recovery(self):
        """处理宕机恢复"""
        if not self.last_shutdown_time:
            logger.info("首次启动，跳过宕机恢复")
            return
        
        # 解析时间字符串为datetime对象
        if isinstance(self.last_shutdown_time, str):
            try:
                self.last_shutdown_time = datetime.fromisoformat(self.last_shutdown_time)
            except ValueError:
                logger.error(f"无法解析关闭时间: {self.last_shutdown_time}")
                return
        
        # 计算宕机时长
        downtime = self.startup_time - self.last_shutdown_time
        logger.info(f"检测到宕机，持续时间: {downtime}")
        logger.info(f"上次关闭时间: {self.last_shutdown_time}")
        logger.info(f"本次启动时间: {self.startup_time}")
        
        # 获取所有备份配置
        configs = await self.db_manager.get_all_backup_configs()
        
        if not configs:
            logger.info("没有备份配置，跳过宕机恢复")
            return
        
        logger.info(f"开始处理宕机恢复，共 {len(configs)} 个配置...")
        
        recovery_tasks = []
        for config in configs:
            task = asyncio.create_task(self.recover_config(config))
            recovery_tasks.append(task)
        
        if recovery_tasks:
            await asyncio.gather(*recovery_tasks, return_exceptions=True)
        
        logger.info("宕机恢复完成")
    
    async def recover_config(self, config):
        """恢复单个配置的消息"""
        try:
            guild = self.get_guild(config[1])  # guild_id
            if not guild:
                logger.warning(f"找不到服务器 ID: {config[1]}")
                return
            
            channel = guild.get_channel(config[2])  # channel_id
            if not channel:
                logger.warning(f"找不到频道 ID: {config[2]}")
                return
            
            # 如果是帖子，获取帖子
            if config[3]:  # thread_id
                thread = channel.get_thread(config[3])
                if thread:
                    channel = thread
                else:
                    logger.warning(f"找不到帖子 ID: {config[3]}")
                    return
            
            # 扫描宕机期间的消息，从上次关闭时间开始
            await self.message_handler.scan_channel_history(
                channel, config[4], config[0], after_time=self.last_shutdown_time  # author_id, config_id
            )
            
            logger.info(f"恢复配置 {config[0]} 完成")
            
        except Exception as e:
            logger.error(f"恢复配置 {config[0]} 失败: {e}")
    
    async def process_pending_scan_tasks(self):
        """处理待处理的扫描任务"""
        try:
            tasks = await self.db_manager.get_pending_scan_tasks()
            if not tasks:
                logger.info("没有待处理的扫描任务")
                return
            
            logger.info(f"发现 {len(tasks)} 个待处理的扫描任务")
            
            # 处理每个任务
            for task in tasks:
                await self.process_scan_task(task)
                
        except Exception as e:
            logger.error(f"处理扫描任务失败: {e}")
    
    async def process_scan_task(self, task):
        """处理单个扫描任务"""
        task_id = task[0]
        config_id = task[1]
        guild_id = task[2]
        channel_id = task[3]
        thread_id = task[4]
        author_id = task[5]
        work_title = task[6]
        
        try:
            logger.info(f"处理扫描任务 {task_id}: 服务器 {guild_id}, 频道 {channel_id}, 作者 {author_id}")
            
            # 更新任务状态为进行中
            await self.db_manager.update_scan_task_status(task_id, 'in_progress')
            
            # 获取服务器和频道
            guild = self.get_guild(guild_id)
            if not guild:
                raise Exception(f"找不到服务器 {guild_id}")
            
            channel = guild.get_channel(channel_id)
            if not channel:
                raise Exception(f"找不到频道 {channel_id}")
            
            # 如果是帖子，获取帖子
            if thread_id:
                thread = channel.get_thread(thread_id)
                if thread:
                    channel = thread
                else:
                    raise Exception(f"找不到帖子 {thread_id}")
            
            # 执行历史扫描
            scanned, backed_up = await self.message_handler.scan_channel_history(
                channel, author_id, config_id, limit=self.config.max_scan_messages
            )
            
            # 更新任务状态为完成
            await self.db_manager.update_scan_task_status(task_id, 'completed')
            
            logger.info(f"扫描任务 {task_id} 完成: 扫描 {scanned} 条消息, 备份 {backed_up} 条消息")
            
        except Exception as e:
            logger.error(f"处理扫描任务 {task_id} 失败: {e}")
            await self.db_manager.update_scan_task_status(task_id, 'failed', str(e))
    
    def start_periodic_scan_task_processing(self):
        """启动定期扫描任务处理"""
        async def periodic_processor():
            while True:
                try:
                    await asyncio.sleep(60)  # 每分钟检查一次
                    await self.process_pending_scan_tasks()
                except Exception as e:
                    logger.error(f"定期扫描任务处理失败: {e}")
        
        # 创建后台任务
        asyncio.create_task(periodic_processor())
        logger.info("已启动定期扫描任务处理")
    
    async def on_message(self, message):
        """处理消息事件"""
        # 处理备份
        await self.message_handler.handle_message(message)
        
        # 处理命令
        await self.process_commands(message)
    
    
    async def on_error(self, event, *args, **kwargs):
        """处理错误事件"""
        import traceback
        logger.error(f"发生错误 - 事件: {event}")
        logger.error(traceback.format_exc())
    
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
        logger.info("Bot正在关闭...")
        self.last_shutdown_time = datetime.now()
        
        # 保存关闭时间到数据库
        try:
            await self.db_manager.save_shutdown_time(self.last_shutdown_time)
            logger.info(f"已保存关闭时间: {self.last_shutdown_time}")
        except Exception as e:
            logger.error(f"保存关闭时间失败: {e}")
        
        await super().close()
    
    def run_bot(self):
        """运行Bot"""
        try:
            self.run(self.config.token)
        except Exception as e:
            logger.error(f"Bot运行失败: {e}")
            raise 