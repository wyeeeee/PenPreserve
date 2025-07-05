import discord
from discord.ext import commands
from discord import app_commands
import logging
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)

class BackupCommands(commands.Cog):
    """备份管理命令 - 简化版"""
    
    def __init__(self, bot):
        self.bot = bot
        self.db_manager = bot.db_manager
        self.message_handler = bot.message_handler
    
    @app_commands.command(name="status", description="查看备份系统状态")
    async def status(self, interaction: discord.Interaction):
        """查看备份系统状态"""
        try:
            embed = discord.Embed(
                title="📊 备份系统状态",
                color=discord.Color.blue()
            )
            
            # 获取所有备份配置
            configs = await self.db_manager.get_all_backup_configs()
            embed.add_field(name="活跃备份配置", value=f"{len(configs)} 个", inline=True)
            
            # 获取总文件数
            total_files = await self.db_manager.get_total_file_count()
            embed.add_field(name="已备份文件", value=f"{total_files} 个", inline=True)
            
            # 服务器数量
            embed.add_field(name="连接服务器", value=f"{len(self.bot.guilds)} 个", inline=True)
            
            # 启动时间
            if self.bot.startup_time:
                startup_timestamp = int(self.bot.startup_time.timestamp())
                embed.add_field(
                    name="启动时间", 
                    value=f"<t:{startup_timestamp}:R>", 
                    inline=True
                )
            
            # Webhook服务器状态
            from server.webhook_server import get_webhook_server
            webhook_server = get_webhook_server()
            if webhook_server:
                embed.add_field(name="Webhook服务器", value="运行中", inline=True)
            else:
                embed.add_field(name="Webhook服务器", value="未启用", inline=True)
            
            await interaction.response.send_message(embed=embed, ephemeral=True)
            
        except Exception as e:
            logger.error(f"获取系统状态失败: {e}")
            await interaction.response.send_message("获取系统状态失败", ephemeral=True)
    
    @app_commands.command(name="my_backup", description="查看我的备份配置")
    async def my_backup(self, interaction: discord.Interaction):
        """查看用户的备份配置"""
        try:
            # 获取当前频道的备份配置
            channel = interaction.channel
            thread_id = channel.id if isinstance(channel, discord.Thread) else None
            channel_id = channel.parent.id if isinstance(channel, discord.Thread) else channel.id
            
            config = await self.db_manager.get_backup_config(
                interaction.guild.id, channel_id, thread_id, interaction.user.id
            )
            
            if not config:
                embed = discord.Embed(
                    title="📋 我的备份配置",
                    description="您在此位置没有备份配置",
                    color=discord.Color.grey()
                )
            else:
                config_id = config[0]
                
                # 获取文件统计
                file_count = await self.db_manager.get_config_file_count(config_id)
                
                embed = discord.Embed(
                    title="📋 我的备份配置",
                    description="备份功能已启用",
                    color=discord.Color.green()
                )
                embed.add_field(name="配置ID", value=str(config_id), inline=True)
                embed.add_field(name="已备份文件", value=f"{file_count} 个", inline=True)
                
                # 创建时间
                created_at = config[5]  # created_at字段
                if isinstance(created_at, str):
                    created_at = datetime.fromisoformat(created_at)
                embed.add_field(
                    name="创建时间", 
                    value=f"<t:{int(created_at.timestamp())}:R>", 
                    inline=True
                )
                
                # 最后检查时间
                last_check = config[6]  # last_check_time字段
                if last_check:
                    if isinstance(last_check, str):
                        last_check = datetime.fromisoformat(last_check)
                    embed.add_field(
                        name="最后检查", 
                        value=f"<t:{int(last_check.timestamp())}:R>", 
                        inline=True
                    )
            
            await interaction.response.send_message(embed=embed, ephemeral=True)
            
        except Exception as e:
            logger.error(f"获取备份配置失败: {e}")
            await interaction.response.send_message("获取备份配置失败", ephemeral=True)
    
    @app_commands.command(name="admin_stats", description="查看管理员统计（仅管理员可用）")
    @app_commands.describe(user="查看指定用户的统计")
    async def admin_stats(self, interaction: discord.Interaction, user: Optional[discord.Member] = None):
        """查看管理员统计"""
        # 检查权限
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("此命令仅限管理员使用", ephemeral=True)
            return
        
        try:
            if user:
                # 查看特定用户的统计
                user_configs = await self.db_manager.get_user_backup_configs(user.id)
                
                embed = discord.Embed(
                    title=f"👤 {user.display_name} 的备份统计",
                    color=discord.Color.blue()
                )
                embed.add_field(name="备份配置", value=f"{len(user_configs)} 个", inline=True)
                
                # 获取用户的文件统计
                total_files = 0
                for config in user_configs:
                    file_count = await self.db_manager.get_config_file_count(config[0])
                    total_files += file_count
                
                embed.add_field(name="备份文件", value=f"{total_files} 个", inline=True)
                
                # 添加配置详情
                if user_configs:
                    config_list = []
                    for config in user_configs[:5]:  # 最多显示5个
                        config_list.append(f"配置ID: {config[0]}")
                    if len(user_configs) > 5:
                        config_list.append(f"... 还有 {len(user_configs) - 5} 个配置")
                    
                    embed.add_field(
                        name="配置列表", 
                        value="\n".join(config_list), 
                        inline=False
                    )
            
            else:
                # 查看整体统计
                embed = discord.Embed(
                    title="🔧 系统管理统计",
                    color=discord.Color.orange()
                )
                
                # 获取各种统计
                total_configs = await self.db_manager.get_total_config_count()
                total_files = await self.db_manager.get_total_file_count()
                total_records = await self.db_manager.get_total_record_count()
                
                embed.add_field(name="总备份配置", value=f"{total_configs} 个", inline=True)
                embed.add_field(name="总备份文件", value=f"{total_files} 个", inline=True)
                embed.add_field(name="总内容记录", value=f"{total_records} 个", inline=True)
                
                # 最近活跃的配置
                recent_configs = await self.db_manager.get_recent_active_configs(5)
                if recent_configs:
                    config_list = []
                    for config in recent_configs:
                        config_list.append(f"配置ID: {config[0]} (用户: {config[4]})")
                    
                    embed.add_field(
                        name="最近活跃配置", 
                        value="\n".join(config_list), 
                        inline=False
                    )
            
            await interaction.response.send_message(embed=embed, ephemeral=True)
            
        except Exception as e:
            logger.error(f"获取管理员统计失败: {e}")
            await interaction.response.send_message("获取统计失败", ephemeral=True)
    
    @app_commands.command(name="force_recovery", description="强制执行宕机恢复（仅管理员可用）")
    @app_commands.describe(minutes="模拟宕机分钟数（默认10分钟）")
    async def force_recovery(self, interaction: discord.Interaction, minutes: int = 10):
        """强制执行宕机恢复"""
        # 检查权限
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("此命令仅限管理员使用", ephemeral=True)
            return
        
        try:
            from datetime import timedelta
            
            await interaction.response.send_message(
                f"开始强制恢复，模拟宕机 {minutes} 分钟...", 
                ephemeral=True
            )
            
            # 模拟关闭时间
            fake_shutdown_time = datetime.now(timezone.utc) - timedelta(minutes=minutes)
            
            # 临时设置关闭时间
            original_shutdown_time = self.bot.last_shutdown_time
            self.bot.last_shutdown_time = fake_shutdown_time
            
            # 执行恢复
            await self.bot.handle_downtime_recovery()
            
            # 恢复原始时间
            self.bot.last_shutdown_time = original_shutdown_time
            
            await interaction.followup.send("强制恢复完成！", ephemeral=True)
            logger.info(f"管理员 {interaction.user.name} 执行了强制恢复")
            
        except Exception as e:
            logger.error(f"强制恢复失败: {e}")
            await interaction.followup.send("强制恢复失败，请检查日志", ephemeral=True)
    
    @app_commands.command(name="manual_scan", description="手动扫描指定用户的消息（仅管理员可用）")
    @app_commands.describe(
        user="要扫描的用户",
        hours="扫描最近几小时的消息（默认24小时）"
    )
    async def manual_scan(self, interaction: discord.Interaction, user: discord.Member, hours: int = 24):
        """手动扫描指定用户的消息"""
        # 检查权限
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("此命令仅限管理员使用", ephemeral=True)
            return
        
        try:
            # 获取用户的备份配置
            channel = interaction.channel
            thread_id = channel.id if isinstance(channel, discord.Thread) else None
            channel_id = channel.parent.id if isinstance(channel, discord.Thread) else channel.id
            
            config = await self.db_manager.get_backup_config(
                interaction.guild.id, channel_id, thread_id, user.id
            )
            
            if not config:
                await interaction.response.send_message(
                    f"{user.mention} 在此位置没有备份配置", 
                    ephemeral=True
                )
                return
            
            config_id = config[0]
            
            await interaction.response.send_message(
                f"开始扫描 {user.mention} 最近 {hours} 小时的消息...", 
                ephemeral=True
            )
            
            # 计算扫描时间
            from datetime import timedelta
            scan_time = datetime.now(timezone.utc) - timedelta(hours=hours)
            
            # 执行扫描
            scanned, downloaded = await self.message_handler.scan_history(
                interaction.guild.id, channel_id, thread_id, user.id, config_id, scan_time
            )
            
            await interaction.followup.send(
                f"扫描完成！\n- 扫描消息：{scanned} 条\n- 下载文件：{downloaded} 个", 
                ephemeral=True
            )
            
            logger.info(f"管理员 {interaction.user.name} 手动扫描了用户 {user.name}")
            
        except Exception as e:
            logger.error(f"手动扫描失败: {e}")
            await interaction.followup.send("手动扫描失败，请检查日志", ephemeral=True)
    
    @app_commands.command(name="simulate_webhook", description="模拟协议授权webhook请求（仅管理员可用）")
    @app_commands.describe(
        target_user="要操作备份的用户（默认为自己）",
        enable_backup="是否启用备份（true=启用，false=暂停）"
    )
    async def simulate_webhook(
        self, 
        interaction: discord.Interaction, 
        target_user: Optional[discord.Member] = None,
        enable_backup: bool = True
    ):
        """模拟协议授权webhook请求"""
        # 检查权限
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("此命令仅限管理员使用", ephemeral=True)
            return
        
        try:
            channel = interaction.channel
            target_author = target_user or interaction.user
            
            # 确定频道和帖子ID
            if isinstance(channel, discord.Thread):
                thread_id = channel.id
                channel_id = channel.parent.id
                location_desc = f"帖子「{channel.name}」"
            else:
                thread_id = None
                channel_id = channel.id
                location_desc = f"频道「{channel.name}」"
            
            await interaction.response.send_message(
                f"正在为 {target_author.mention} 在{location_desc}中模拟协议授权...", 
                ephemeral=True
            )
            
            # 模拟webhook数据
            webhook_data = {
                "event_type": "backup_permission_update",
                "guild_id": str(interaction.guild.id),
                "channel_id": str(channel_id),
                "thread_id": str(thread_id) if thread_id else None,
                "author_id": str(target_author.id),
                "backup_allowed": enable_backup
            }
            
            # 使用webhook服务器处理逻辑
            from server.webhook_server import get_webhook_server
            webhook_server = get_webhook_server()
            
            if webhook_server:
                # 直接添加到通知队列
                notification_data = {
                    "action": "enable" if enable_backup else "disable",
                    "config_id": None,  # 将由处理器填充
                    "guild_id": int(webhook_data["guild_id"]),
                    "channel_id": int(webhook_data["channel_id"]),
                    "thread_id": int(webhook_data["thread_id"]) if webhook_data["thread_id"] else None,
                    "author_id": int(webhook_data["author_id"])
                }
                
                if enable_backup:
                    # 创建备份配置
                    config_id = await self.db_manager.create_backup_config(
                        notification_data["guild_id"],
                        notification_data["channel_id"],
                        notification_data["thread_id"],
                        notification_data["author_id"]
                    )
                    notification_data["config_id"] = config_id
                else:
                    # 获取现有配置
                    existing_config = await self.db_manager.get_backup_config(
                        notification_data["guild_id"],
                        notification_data["channel_id"],
                        notification_data["thread_id"],
                        notification_data["author_id"]
                    )
                    if existing_config:
                        config_id = existing_config[0]
                        notification_data["config_id"] = config_id
                        await self.db_manager.disable_backup_config(config_id)
                
                # 添加到通知队列
                await webhook_server.notification_queue.put(notification_data)
                
                action_desc = "启用" if enable_backup else "暂停"
                await interaction.followup.send(
                    f"✅ 模拟{action_desc}备份成功！\n"
                    f"配置ID: {notification_data.get('config_id', 'N/A')}\n"
                    f"Bot将在几秒内处理此通知", 
                    ephemeral=True
                )
            else:
                await interaction.followup.send(
                    "❌ Webhook服务器未运行，无法模拟请求", 
                    ephemeral=True
                )
            
            logger.info(f"管理员 {interaction.user.name} 模拟了webhook请求")
            
        except Exception as e:
            logger.error(f"模拟webhook失败: {e}")
            await interaction.followup.send(f"模拟失败: {str(e)}", ephemeral=True)

async def setup(bot):
    """设置命令"""
    await bot.add_cog(BackupCommands(bot)) 