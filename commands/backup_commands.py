#!/usr/bin/env python3
"""
简化的备份管理命令
重构后的版本，拆分了业务逻辑到不同文件
"""

import discord
from discord.ext import commands
from discord import app_commands
import logging
import asyncio
from datetime import datetime, timezone
from typing import Optional
from utils.file_manager import FileManager
from .backup_operations import BackupOperations
from .backup_views import DeleteBackupSelectView, DownloadBackupView

logger = logging.getLogger(__name__)

class BackupCommands(commands.Cog):
    """备份管理命令"""
    
    def __init__(self, bot):
        self.bot = bot
        self.db_manager = bot.db_manager
        self.message_handler = bot.message_handler
        # 创建备份操作实例
        self.backup_ops = BackupOperations(bot, self.db_manager, self.message_handler)
    
    @app_commands.command(name="备份状态", description="查看当前频道/帖子的备份状态")
    async def backup_status(self, interaction: discord.Interaction):
        """查看当前频道/帖子的备份状态"""
        try:
            await interaction.response.defer()
            
            # 确定位置信息
            if isinstance(interaction.channel, discord.Thread):
                thread_id = interaction.channel.id
                channel_id = interaction.channel.parent.id
                location_type = "帖子"
                location_name = interaction.channel.name
            else:
                thread_id = None
                channel_id = interaction.channel.id
                location_type = "频道"
                location_name = interaction.channel.name
            
            # 检查备份配置
            backup_config = await self.db_manager.get_backup_config(
                interaction.guild.id, channel_id, thread_id, interaction.user.id
            )
            
            embed = discord.Embed(
                title=f"📋 {location_type}备份状态",
                description=f"位置: #{location_name}",
                color=discord.Color.green() if backup_config else discord.Color.red(),
                timestamp=datetime.now(timezone.utc)
            )
            
            if backup_config:
                config_id = backup_config[0]
                # 字段顺序: id, guild_id, channel_id, thread_id, author_id, title, enabled, created_at, last_check_time
                created_at = backup_config[7] if len(backup_config) > 7 else None
                
                # 获取统计信息
                stats = await self.db_manager.get_backup_stats(config_id)
                
                # 处理创建时间
                time_text = "未知时间"
                if created_at:
                    try:
                        if isinstance(created_at, str):
                            time_text = f"<t:{int(datetime.fromisoformat(created_at).timestamp())}:R>"
                        else:
                            time_text = f"<t:{int(created_at.timestamp())}:R>"
                    except (ValueError, AttributeError):
                        time_text = "时间格式错误"
                
                embed.add_field(
                    name="✅ 备份已启用",
                    value=f"创建时间: {time_text}",
                    inline=False
                )
                embed.add_field(name="消息备份", value=f"{stats['message_count']} 条", inline=True)
                embed.add_field(name="文件备份", value=f"{stats['file_count']} 个", inline=True)
                embed.add_field(
                    name="存储大小", 
                    value=FileManager.format_file_size(stats['total_size']), 
                    inline=True
                )
            else:
                embed.add_field(
                    name="❌ 备份未启用",
                    value="此位置未配置备份功能",
                    inline=False
                )
                embed.add_field(
                    name="💡 提示",
                    value="备份功能需要通过协议授权bot启用",
                    inline=False
                )
            
            await interaction.followup.send(embed=embed)
            
        except Exception as e:
            logger.error(f"查看备份状态失败: {e}")
            await interaction.followup.send("查看备份状态时发生错误", ephemeral=True)
    
    @app_commands.command(name="我的备份", description="查看我的所有备份")
    async def my_backups(self, interaction: discord.Interaction):
        """查看用户的所有备份"""
        try:
            await interaction.response.defer()
            
            # 获取用户的所有备份配置
            configs = await self.db_manager.get_user_backup_configs(interaction.user.id)
            
            if not configs:
                embed = discord.Embed(
                    title="📦 我的备份",
                    description="您目前没有任何备份配置",
                    color=discord.Color.orange()
                )
                await interaction.followup.send(embed=embed)
                return
            
            embed = discord.Embed(
                title="📦 我的备份",
                description=f"找到 {len(configs)} 个备份配置",
                color=discord.Color.blue(),
                timestamp=datetime.now(timezone.utc)
            )
            
            total_messages = 0
            total_files = 0
            total_size = 0
            
            for config in configs[:10]:  # 最多显示10个
                config_id, guild_id, channel_id, thread_id = config[:4]
                # 字段顺序: id, guild_id, channel_id, thread_id, author_id, title, enabled, created_at, last_check_time
                created_at = config[7] if len(config) > 7 else None
                
                # 获取统计信息
                stats = await self.db_manager.get_backup_stats(config_id)
                total_messages += stats['message_count']
                total_files += stats['file_count']
                total_size += stats['total_size']
                
                # 获取位置信息
                try:
                    guild = self.bot.get_guild(guild_id)
                    if guild:
                        if thread_id:
                            channel = guild.get_channel(channel_id)
                            if channel:
                                thread = channel.get_thread(thread_id)
                                location = f"#{channel.name}/{thread.name if thread else '未知帖子'}"
                            else:
                                location = "未知频道/帖子"
                        else:
                            channel = guild.get_channel(channel_id)
                            location = f"#{channel.name}" if channel else "未知频道"
                        
                        server_info = f"{guild.name}"
                    else:
                        location = "未知位置"
                        server_info = "未知服务器"
                except:
                    location = "未知位置"
                    server_info = "未知服务器"
                
                # 处理创建时间
                time_text = "未知时间"
                if created_at:
                    try:
                        if isinstance(created_at, str):
                            time_text = f"<t:{int(datetime.fromisoformat(created_at).timestamp())}:R>"
                        else:
                            time_text = f"<t:{int(created_at.timestamp())}:R>"
                    except (ValueError, AttributeError):
                        time_text = "时间格式错误"
                
                embed.add_field(
                    name=f"🏠 {server_info}",
                    value=f"位置: {location}\n"
                          f"消息: {stats['message_count']} 条 | 文件: {stats['file_count']} 个\n"
                          f"创建: {time_text}",
                    inline=False
                )
            
            if len(configs) > 10:
                embed.add_field(
                    name="⚠️ 显示限制",
                    value=f"仅显示前10个配置，总共有 {len(configs)} 个",
                    inline=False
                )
            
            # 总计信息
            embed.add_field(
                name="📊 总计统计",
                value=f"消息: {total_messages} 条\n"
                      f"文件: {total_files} 个\n"
                      f"大小: {FileManager.format_file_size(total_size)}",
                inline=True
            )
            
            await interaction.followup.send(embed=embed)
            
        except Exception as e:
            logger.error(f"查看我的备份失败: {e}")
            await interaction.followup.send("查看备份列表时发生错误", ephemeral=True)
    
    @app_commands.command(name="启用备份", description="手动启用当前位置的备份功能（备用选项）")
    async def enable_backup(self, interaction: discord.Interaction):
        """手动启用备份功能"""
        try:
            await interaction.response.defer()
            
            # 确定位置信息
            if isinstance(interaction.channel, discord.Thread):
                thread_id = interaction.channel.id
                channel_id = interaction.channel.parent.id
                location_type = "帖子"
                location_name = interaction.channel.name
            else:
                thread_id = None
                channel_id = interaction.channel.id
                location_type = "频道"
                location_name = interaction.channel.name
            
            # 检查是否已有配置
            existing_config = await self.db_manager.get_backup_config(
                interaction.guild.id, channel_id, thread_id, interaction.user.id
            )
            
            if existing_config:
                embed = discord.Embed(
                    title="⚠️ 备份已启用",
                    description=f"您在此{location_type}的备份功能已经启用",
                    color=discord.Color.orange()
                )
                await interaction.followup.send(embed=embed, ephemeral=True)
                return
            
            # 创建备份配置，使用当前名称作为标题
            config_id = await self.db_manager.create_backup_config(
                interaction.guild.id, channel_id, thread_id, interaction.user.id, location_name
            )
            
            if config_id:
                embed = discord.Embed(
                    title="✅ 备份功能已启用",
                    description=f"已为您在{location_type} #{location_name} 启用备份功能",
                    color=discord.Color.green(),
                    timestamp=datetime.now(timezone.utc)
                )
                embed.add_field(
                    name="📝 说明",
                    value="• 系统将自动备份您发布的消息和附件\n"
                          "• 推荐使用协议授权bot进行管理\n"
                          "• 可使用 `/备份状态` 查看状态",
                    inline=False
                )
                
                # 启动历史扫描
                asyncio.create_task(self.backup_ops.background_history_scan(
                    interaction.guild.id, channel_id, thread_id, interaction.user.id, config_id
                ))
                
                await interaction.followup.send(embed=embed)
            else:
                embed = discord.Embed(
                    title="❌ 启用失败",
                    description="启用备份功能时发生错误",
                    color=discord.Color.red()
                )
                await interaction.followup.send(embed=embed, ephemeral=True)
            
        except Exception as e:
            logger.error(f"启用备份失败: {e}")
            await interaction.followup.send("启用备份功能时发生错误", ephemeral=True)
    
    @app_commands.command(name="禁用备份", description="禁用当前位置的备份功能")
    async def disable_backup(self, interaction: discord.Interaction):
        """禁用备份功能"""
        try:
            await interaction.response.defer()
            
            # 确定位置信息
            if isinstance(interaction.channel, discord.Thread):
                thread_id = interaction.channel.id
                channel_id = interaction.channel.parent.id
                location_type = "帖子"
                location_name = interaction.channel.name
            else:
                thread_id = None
                channel_id = interaction.channel.id
                location_type = "频道"
                location_name = interaction.channel.name
            
            # 检查是否存在配置
            existing_config = await self.db_manager.get_backup_config(
                interaction.guild.id, channel_id, thread_id, interaction.user.id
            )
            
            if not existing_config:
                embed = discord.Embed(
                    title="⚠️ 备份未启用",
                    description=f"您在此{location_type}没有启用备份功能",
                    color=discord.Color.orange()
                )
                await interaction.followup.send(embed=embed, ephemeral=True)
                return
            
            # 禁用备份配置
            config_id = existing_config[0]
            await self.db_manager.disable_backup_config(config_id)
            
            embed = discord.Embed(
                title="✅ 备份功能已禁用",
                description=f"已禁用您在{location_type} #{location_name} 的备份功能",
                color=discord.Color.green(),
                timestamp=datetime.now(timezone.utc)
            )
            embed.add_field(
                name="📝 说明",
                value="• 已保存的备份数据不会被删除\n"
                      "• 可以使用 `/删除备份` 命令彻底删除备份数据\n"
                      "• 可以重新启用备份功能",
                inline=False
            )
            
            await interaction.followup.send(embed=embed)
            
        except Exception as e:
            logger.error(f"禁用备份失败: {e}")
            await interaction.followup.send("禁用备份功能时发生错误", ephemeral=True)
    
    @app_commands.command(name="下载备份", description="选择并下载指定的备份(信息+附件压缩包)")
    async def download_backup(self, interaction: discord.Interaction):
        """下载备份"""
        try:
            await interaction.response.defer()
            
            # 获取用户的所有备份配置
            configs = await self.db_manager.get_user_backup_configs(interaction.user.id)
            
            if not configs:
                embed = discord.Embed(
                    title="📦 下载备份",
                    description="您目前没有任何备份配置",
                    color=discord.Color.orange()
                )
                await interaction.followup.send(embed=embed, ephemeral=True)
                return
            
            embed = discord.Embed(
                title="📦 下载备份",
                description=f"找到 {len(configs)} 个备份配置\n请选择要下载的备份：",
                color=discord.Color.blue()
            )
            
            await interaction.followup.send(embed=embed, view=DownloadBackupView(self.backup_ops, configs), ephemeral=True)
            
        except Exception as e:
            logger.error(f"下载备份失败: {e}")
            await interaction.followup.send("下载备份时发生错误", ephemeral=True)
    
    @app_commands.command(name="删除备份", description="删除指定的备份配置和所有相关数据")
    async def delete_backup(self, interaction: discord.Interaction):
        """删除备份配置和数据"""
        try:
            await interaction.response.defer()
            
            # 获取用户的所有备份配置
            configs = await self.db_manager.get_user_backup_configs(interaction.user.id)
            
            if not configs:
                embed = discord.Embed(
                    title="🗑️ 删除备份",
                    description="您目前没有任何备份配置",
                    color=discord.Color.orange()
                )
                await interaction.followup.send(embed=embed, ephemeral=True)
                return
            
            embed = discord.Embed(
                title="🗑️ 删除备份",
                description=f"找到 {len(configs)} 个备份配置\n请选择要删除的备份：",
                color=discord.Color.red()
            )
            
            await interaction.followup.send(embed=embed, view=DeleteBackupSelectView(self.backup_ops, configs), ephemeral=True)
            
        except Exception as e:
            logger.error(f"删除备份失败: {e}")
            await interaction.followup.send("删除备份时发生错误", ephemeral=True)
    
    @app_commands.command(name="系统状态", description="查看系统整体状态（管理员）")
    @app_commands.default_permissions(administrator=True)
    async def system_status(self, interaction: discord.Interaction):
        """查看系统状态（管理员命令）"""
        try:
            await interaction.response.defer()
            
            # 获取全局统计
            global_stats = await self.db_manager.get_backup_stats()
            
            # 获取bot状态
            last_activity = await self.db_manager.get_last_activity_time()
            
            embed = discord.Embed(
                title="🖥️ 系统状态",
                description="PenPreserve Discord备份机器人",
                color=discord.Color.blue(),
                timestamp=datetime.now(timezone.utc)
            )
            
            # 机器人信息
            embed.add_field(
                name="🤖 机器人信息",
                value=f"服务器数: {len(self.bot.guilds)}\n"
                      f"延迟: {round(self.bot.latency * 1000)}ms\n"
                      f"状态: {'🟢 在线' if self.bot.is_ready() else '🔴 离线'}",
                inline=True
            )
            
            # 备份统计
            embed.add_field(
                name="📊 备份统计",
                value=f"配置数: {global_stats['config_count']}\n"
                      f"消息数: {global_stats['message_count']}\n"
                      f"文件数: {global_stats['file_count']}",
                inline=True
            )
            
            # 存储信息
            embed.add_field(
                name="💾 存储信息",
                value=f"总大小: {FileManager.format_file_size(global_stats['total_size'])}",
                inline=True
            )
            
            # 最后活动时间
            if last_activity:
                try:
                    last_time = datetime.fromisoformat(last_activity)
                    activity_text = f"<t:{int(last_time.timestamp())}:R>"
                except:
                    activity_text = "时间格式错误"
            else:
                activity_text = "无记录"
            
            embed.add_field(
                name="⏰ 最后活动",
                value=activity_text,
                inline=False
            )
            
            await interaction.followup.send(embed=embed)
            
        except Exception as e:
            logger.error(f"查看系统状态失败: {e}")
            await interaction.followup.send("查看系统状态时发生错误", ephemeral=True)

async def setup(bot):
    await bot.add_cog(BackupCommands(bot))