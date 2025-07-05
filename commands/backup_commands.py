import discord
from discord.ext import commands
from discord import app_commands
import logging
from datetime import datetime
from utils.helpers import safe_send_message

logger = logging.getLogger(__name__)

class BackupView(discord.ui.View):
    def __init__(self, bot, db_manager, message_handler, channel, author):
        super().__init__(timeout=300)
        self.bot = bot
        self.db_manager = db_manager
        self.message_handler = message_handler
        self.channel = channel
        self.author = author
        self.processing = False  # 防止重复处理
    
    async def on_error(self, interaction: discord.Interaction, error: Exception, item: discord.ui.Item):
        """视图级别的错误处理"""
        logger.error(f"视图交互错误: {error}")
        # 停止视图以避免进一步的问题
        self.stop()
    
    @discord.ui.button(label='启用备份', style=discord.ButtonStyle.green, emoji='✅')
    async def enable_backup(self, interaction: discord.Interaction, button: discord.ui.Button):
        # 防止重复处理
        if self.processing:
            logger.warning("已在处理启用备份请求，忽略重复点击")
            return
        
        self.processing = True
        
        # 立即禁用按钮以防止重复点击
        button.disabled = True
        for child in self.children:
            child.disabled = True
        
        if interaction.user.id != self.author.id:
            try:
                await interaction.response.send_message("只有作者可以启用备份功能", ephemeral=True)
            except discord.HTTPException as e:
                if e.code == 40060:  # Interaction has already been acknowledged
                    try:
                        await interaction.followup.send("只有作者可以启用备份功能", ephemeral=True)
                    except Exception as fe:
                        logger.error(f"发送权限错误消息失败: {fe}")
                else:
                    logger.error(f"响应权限检查失败: {e}")
            except Exception as e:
                logger.error(f"响应权限检查失败: {e}")
            return
        
        # 尝试响应交互
        response_sent = False
        try:
            await interaction.response.send_message("正在启用备份功能，请稍候...", ephemeral=True)
            response_sent = True
        except discord.HTTPException as e:
            if e.code == 40060:  # Interaction has already been acknowledged
                logger.warning("交互已经被响应，继续处理...")
            else:
                logger.error(f"响应交互失败: {e}")
                return
        except Exception as e:
            logger.error(f"响应交互失败: {e}")
            return
        
        try:
            # 创建备份配置
            thread_id = self.channel.id if isinstance(self.channel, discord.Thread) else None
            channel_id = self.channel.parent.id if isinstance(self.channel, discord.Thread) else self.channel.id
            
            config_id = await self.db_manager.create_backup_config(
                interaction.guild.id,
                channel_id,
                thread_id,
                self.author.id
            )
            
            if config_id:
                # 扫描历史消息
                scanned, backed_up = await self.message_handler.scan_channel_history(
                    self.channel, self.author.id, config_id
                )
                
                embed = discord.Embed(
                    title="✅ 备份已启用",
                    description=f"已为 {self.author.mention} 在此频道启用备份功能",
                    color=discord.Color.green()
                )
                embed.add_field(name="扫描消息", value=f"{scanned} 条", inline=True)
                embed.add_field(name="备份消息", value=f"{backed_up} 条", inline=True)
                
                # 发送新消息而不是使用followup
                await self.channel.send(embed=embed)
                logger.info(f"用户 {self.author.name} 在频道 {self.channel.name} 启用了备份")
            else:
                # 通知用户备份配置已存在
                if response_sent:
                    try:
                        await interaction.followup.send("备份配置已存在或创建失败", ephemeral=True)
                    except:
                        pass
                else:
                    # 如果初始响应失败，直接发送消息到频道
                    await self.channel.send(f"{self.author.mention} 备份配置已存在或创建失败")
        except Exception as e:
            logger.error(f"启用备份失败: {e}")
            # 通知用户发生错误
            if response_sent:
                try:
                    await interaction.followup.send("启用备份时发生错误，请检查日志", ephemeral=True)
                except:
                    pass
            else:
                # 如果初始响应失败，直接发送消息到频道
                try:
                    await self.channel.send(f"{self.author.mention} 启用备份时发生错误，请检查日志")
                except:
                    pass
        
        # 停止视图以避免重复操作
        self.stop()
    
    @discord.ui.button(label='取消', style=discord.ButtonStyle.grey, emoji='❌')
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        # 防止重复处理
        if self.processing:
            logger.warning("已在处理取消请求，忽略重复点击")
            return
        
        self.processing = True
        
        # 立即禁用按钮以防止重复点击
        button.disabled = True
        for child in self.children:
            child.disabled = True
            
        if interaction.user.id != self.author.id:
            try:
                await interaction.response.send_message("只有作者可以取消", ephemeral=True)
            except discord.HTTPException as e:
                if e.code == 40060:  # Interaction has already been acknowledged
                    try:
                        await interaction.followup.send("只有作者可以取消", ephemeral=True)
                    except Exception as fe:
                        logger.error(f"发送取消权限错误消息失败: {fe}")
                else:
                    logger.error(f"响应取消权限检查失败: {e}")
            except Exception as e:
                logger.error(f"响应取消权限检查失败: {e}")
            return
        
        # 尝试响应取消交互
        try:
            await interaction.response.send_message("已取消备份设置", ephemeral=True)
        except discord.HTTPException as e:
            if e.code == 40060:  # Interaction has already been acknowledged
                logger.warning("取消交互已经被响应")
            else:
                logger.error(f"响应取消交互失败: {e}")
        except Exception as e:
            logger.error(f"响应取消交互失败: {e}")
        self.stop()

class BackupCommands(commands.Cog):
    def __init__(self, bot, db_manager, message_handler):
        self.bot = bot
        self.db_manager = db_manager
        self.message_handler = message_handler
    
    @app_commands.command(name="enable_backup", description="为当前频道/帖子启用备份功能")
    async def enable_backup(self, interaction: discord.Interaction):
        """启用备份功能"""
        channel = interaction.channel
        author = interaction.user
        
        # 检查是否已存在备份配置
        thread_id = channel.id if isinstance(channel, discord.Thread) else None
        channel_id = channel.parent.id if isinstance(channel, discord.Thread) else channel.id
        
        existing_config = await self.db_manager.get_backup_config(
            interaction.guild.id, channel_id, thread_id, author.id
        )
        
        if existing_config:
            await interaction.response.send_message("您已在此频道启用了备份功能", ephemeral=True)
            return
        
        # 创建确认视图
        view = BackupView(self.bot, self.db_manager, self.message_handler, channel, author)
        
        embed = discord.Embed(
            title="🔄 启用备份功能",
            description=f"是否为 {author.mention} 在此频道启用备份功能？\n\n"
                       "启用后将备份您的消息和附件（图片、文档等）",
            color=discord.Color.blue()
        )
        embed.add_field(name="注意", value="只会备份您发送的内容，不会备份其他人的消息", inline=False)
        
        await interaction.response.send_message(embed=embed, view=view)
    
    @app_commands.command(name="disable_backup", description="禁用当前频道/帖子的备份功能")
    async def disable_backup(self, interaction: discord.Interaction):
        """禁用备份功能"""
        channel = interaction.channel
        author = interaction.user
        
        # 检查备份配置
        thread_id = channel.id if isinstance(channel, discord.Thread) else None
        channel_id = channel.parent.id if isinstance(channel, discord.Thread) else channel.id
        
        config = await self.db_manager.get_backup_config(
            interaction.guild.id, channel_id, thread_id, author.id
        )
        
        if not config:
            await interaction.response.send_message("您在此频道没有启用备份功能", ephemeral=True)
            return
        
        # 禁用备份配置
        await self.db_manager.disable_backup_config(config[0])
        
        embed = discord.Embed(
            title="❌ 备份已禁用",
            description=f"已为 {author.mention} 在此频道禁用备份功能",
            color=discord.Color.red()
        )
        
        await interaction.response.send_message(embed=embed)
        logger.info(f"用户 {author.name} 在频道 {channel.name} 禁用了备份")
    
    @app_commands.command(name="backup_status", description="查看当前频道/帖子的备份状态")
    async def backup_status(self, interaction: discord.Interaction):
        """查看备份状态"""
        channel = interaction.channel
        author = interaction.user
        
        # 检查备份配置
        thread_id = channel.id if isinstance(channel, discord.Thread) else None
        channel_id = channel.parent.id if isinstance(channel, discord.Thread) else channel.id
        
        config = await self.db_manager.get_backup_config(
            interaction.guild.id, channel_id, thread_id, author.id
        )
        
        if not config:
            embed = discord.Embed(
                title="📊 备份状态",
                description="此频道未启用备份功能",
                color=discord.Color.grey()
            )
        else:
            # 获取备份统计
            import aiosqlite
            async with aiosqlite.connect(self.db_manager.db_path) as db:
                # 消息数量
                cursor = await db.execute(
                    'SELECT COUNT(*) FROM message_backups WHERE config_id = ?',
                    (config[0],)
                )
                message_count = (await cursor.fetchone())[0]
                
                # 文件数量
                cursor = await db.execute('''
                    SELECT COUNT(*) FROM file_backups 
                    WHERE message_backup_id IN (
                        SELECT id FROM message_backups WHERE config_id = ?
                    )
                ''', (config[0],))
                file_count = (await cursor.fetchone())[0]
            
            embed = discord.Embed(
                title="📊 备份状态",
                description="备份功能已启用",
                color=discord.Color.green()
            )
            embed.add_field(name="备份消息", value=f"{message_count} 条", inline=True)
            embed.add_field(name="备份文件", value=f"{file_count} 个", inline=True)
            
            # 处理创建时间
            created_at = config[6]
            if isinstance(created_at, str):
                created_at = datetime.fromisoformat(created_at)
            embed.add_field(name="创建时间", value=f"<t:{int(created_at.timestamp())}:R>", inline=True)
            
            # 处理最后扫描时间
            if config[7]:  # last_scan_time
                last_scan = config[7]
                if isinstance(last_scan, str):
                    last_scan = datetime.fromisoformat(last_scan)
                embed.add_field(name="最后扫描", value=f"<t:{int(last_scan.timestamp())}:R>", inline=True)
        
        await interaction.response.send_message(embed=embed, ephemeral=True)
    
    @app_commands.command(name="force_recovery", description="强制执行宕机恢复（仅用于测试）")
    @app_commands.describe(minutes="模拟宕机分钟数（默认10分钟）")
    async def force_recovery(self, interaction: discord.Interaction, minutes: int = 10):
        """强制执行宕机恢复"""
        try:
            from datetime import timedelta
            
            # 模拟关闭时间
            fake_shutdown_time = datetime.now() - timedelta(minutes=minutes)
            
            # 临时设置关闭时间
            original_shutdown_time = self.bot.last_shutdown_time
            self.bot.last_shutdown_time = fake_shutdown_time
            
            await interaction.response.send_message(f"开始强制恢复，模拟宕机 {minutes} 分钟...", ephemeral=True)
            
            # 执行恢复
            await self.bot.handle_downtime_recovery()
            
            # 恢复原始时间
            self.bot.last_shutdown_time = original_shutdown_time
            
            await interaction.followup.send("强制恢复完成！", ephemeral=True)
            logger.info(f"用户 {interaction.user.name} 执行了强制恢复")
            
        except Exception as e:
            logger.error(f"强制恢复失败: {e}")
            await interaction.followup.send("强制恢复失败，请检查日志", ephemeral=True)
    
    @app_commands.command(name="status", description="查看Bot运行状态")
    async def status(self, interaction: discord.Interaction):
        """查看Bot状态"""
        try:
            embed = discord.Embed(
                title="🤖 Bot运行状态",
                color=discord.Color.blue()
            )
            
            # 当前启动时间
            if self.bot.startup_time:
                startup_timestamp = int(self.bot.startup_time.timestamp())
                embed.add_field(
                    name="当前启动时间", 
                    value=f"<t:{startup_timestamp}:F>\n<t:{startup_timestamp}:R>", 
                    inline=False
                )
            
            # 上次关闭时间
            if self.bot.last_shutdown_time:
                if isinstance(self.bot.last_shutdown_time, str):
                    shutdown_time = datetime.fromisoformat(self.bot.last_shutdown_time)
                else:
                    shutdown_time = self.bot.last_shutdown_time
                
                shutdown_timestamp = int(shutdown_time.timestamp())
                embed.add_field(
                    name="上次关闭时间", 
                    value=f"<t:{shutdown_timestamp}:F>\n<t:{shutdown_timestamp}:R>", 
                    inline=False
                )
                
                # 宕机时长
                if self.bot.startup_time:
                    downtime = self.bot.startup_time - shutdown_time
                    hours, remainder = divmod(int(downtime.total_seconds()), 3600)
                    minutes, seconds = divmod(remainder, 60)
                    downtime_str = f"{hours}小时 {minutes}分钟 {seconds}秒"
                    embed.add_field(name="宕机时长", value=downtime_str, inline=True)
            else:
                embed.add_field(name="上次关闭时间", value="首次启动", inline=False)
            
            # 备份配置数量
            configs = await self.db_manager.get_all_backup_configs()
            embed.add_field(name="活跃备份配置", value=f"{len(configs)} 个", inline=True)
            
            # 服务器数量
            embed.add_field(name="连接服务器", value=f"{len(self.bot.guilds)} 个", inline=True)
            
            await interaction.response.send_message(embed=embed, ephemeral=True)
            
        except Exception as e:
            logger.error(f"获取Bot状态失败: {e}")
            await interaction.response.send_message("获取Bot状态失败，请检查日志", ephemeral=True)

async def setup(bot):
    """设置命令"""
    db_manager = bot.db_manager
    message_handler = bot.message_handler
    await bot.add_cog(BackupCommands(bot, db_manager, message_handler)) 