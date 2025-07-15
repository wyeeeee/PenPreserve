#!/usr/bin/env python3
"""
备份相关的Discord UI组件
包含Select菜单、View等交互组件
"""

import discord
from discord import ui
from discord.ext import commands
import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

class DeleteBackupView(ui.View):
    """删除备份的确认界面"""
    
    def __init__(self, backup_operations, config_id: int, config_data, location_name: str):
        super().__init__(timeout=300)
        self.backup_operations = backup_operations
        self.config_id = config_id
        self.config_data = config_data
        self.location_name = location_name
    
    @ui.button(label="确认删除", style=discord.ButtonStyle.danger, emoji="🗑️")
    async def confirm_delete(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.defer()
        
        # 调用备份操作的删除方法
        success = await self.backup_operations.delete_backup_data(self.config_id)
        
        if success:
            embed = discord.Embed(
                title="✅ 删除成功",
                description=f"备份配置和所有相关数据已删除\n位置: {self.location_name}",
                color=discord.Color.green(),
                timestamp=datetime.now(timezone.utc)
            )
        else:
            embed = discord.Embed(
                title="❌ 删除失败",
                description="删除备份数据时发生错误",
                color=discord.Color.red()
            )
        
        await interaction.edit_original_response(embed=embed, view=None)
    
    @ui.button(label="取消", style=discord.ButtonStyle.secondary, emoji="❌")
    async def cancel_delete(self, interaction: discord.Interaction, button: ui.Button):
        embed = discord.Embed(
            title="🚫 操作已取消",
            description="备份数据未被删除",
            color=discord.Color.orange()
        )
        await interaction.response.edit_message(embed=embed, view=None)

class DownloadBackupView(ui.View):
    """下载备份的选择界面"""
    
    def __init__(self, backup_operations, configs: list):
        super().__init__(timeout=300)
        self.backup_operations = backup_operations
        self.configs = configs
        
        # 生成选项
        options = []
        for config in configs[:25]:  # Discord限制最多25个选项
            config_id, guild_id, channel_id, thread_id = config[:4]
            title = config[5] if len(config) > 5 and config[5] else None
            
            # 获取位置信息
            try:
                bot = backup_operations.bot
                guild = bot.get_guild(guild_id)
                if guild:
                    if thread_id:
                        channel = guild.get_channel(channel_id)
                        if channel:
                            thread = channel.get_thread(thread_id)
                            location = f"#{channel.name}/{thread.name if thread else (title or '未知帖子')}"
                        else:
                            location = f"未知频道/{title or '未知帖子'}"
                    else:
                        channel = guild.get_channel(channel_id)
                        location = f"#{channel.name}" if channel else (title or "未知频道")
                    
                    server_info = f"{guild.name}"
                else:
                    location = title or "未知位置"
                    server_info = "未知服务器"
            except:
                location = title or "未知位置"
                server_info = "未知服务器"
            
            label = f"{server_info} - {location}"
            if len(label) > 100:  # Discord限制
                label = label[:97] + "..."
            
            # 使用异步方法获取统计信息不太方便，这里简化描述
            description = f"配置ID: {config_id}"
            if len(description) > 100:
                description = description[:97] + "..."
            
            options.append(discord.SelectOption(
                label=label,
                value=str(config_id),
                description=description
            ))
        
        if options:
            self.add_item(BackupSelectMenu(backup_operations, configs, options))

class BackupSelectMenu(ui.Select):
    """备份选择菜单"""
    
    def __init__(self, backup_operations, configs: list, options: list):
        super().__init__(placeholder="选择要下载的备份配置...", options=options)
        self.backup_operations = backup_operations
        self.configs = configs
    
    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer()
        config_id = int(self.values[0])
        
        # 获取配置信息
        selected_config = None
        for config in self.configs:
            if config[0] == config_id:
                selected_config = config
                break
        
        if not selected_config:
            embed = discord.Embed(
                title="❌ 配置未找到",
                description="选择的备份配置未找到",
                color=discord.Color.red()
            )
            await interaction.edit_original_response(embed=embed, view=None)
            return
        
        # 生成备份包
        embed = discord.Embed(
            title="📦 正在准备下载",
            description="正在生成备份压缩包，请稍等...",
            color=discord.Color.blue()
        )
        await interaction.edit_original_response(embed=embed, view=None)
        
        # 调用备份操作的处理方法
        success = await self.backup_operations.process_backup_download(
            interaction, config_id, selected_config
        )

class DeleteBackupSelectView(ui.View):
    """删除备份的选择界面"""
    
    def __init__(self, backup_operations, configs: list):
        super().__init__(timeout=300)
        self.backup_operations = backup_operations
        self.configs = configs
        
        # 生成选项
        options = []
        for config in configs[:25]:  # Discord限制最多25个选项
            config_id, guild_id, channel_id, thread_id = config[:4]
            title = config[5] if len(config) > 5 and config[5] else None
            
            # 获取位置信息
            try:
                bot = backup_operations.bot
                guild = bot.get_guild(guild_id)
                if guild:
                    if thread_id:
                        channel = guild.get_channel(channel_id)
                        if channel:
                            thread = channel.get_thread(thread_id)
                            location = f"#{channel.name}/{thread.name if thread else (title or '未知帖子')}"
                        else:
                            location = f"未知频道/{title or '未知帖子'}"
                    else:
                        channel = guild.get_channel(channel_id)
                        location = f"#{channel.name}" if channel else (title or "未知频道")
                    
                    server_info = f"{guild.name}"
                else:
                    location = title or "未知位置"
                    server_info = "未知服务器"
            except:
                location = title or "未知位置"
                server_info = "未知服务器"
            
            label = f"{server_info} - {location}"
            if len(label) > 100:  # Discord限制
                label = label[:97] + "..."
            
            description = f"配置ID: {config_id}"
            if len(description) > 100:
                description = description[:97] + "..."
            
            options.append(discord.SelectOption(
                label=label,
                value=str(config_id),
                description=description
            ))
        
        if options:
            self.add_item(DeleteBackupSelectMenu(backup_operations, configs, options))

class DeleteBackupSelectMenu(ui.Select):
    """删除备份选择菜单"""
    
    def __init__(self, backup_operations, configs: list, options: list):
        super().__init__(placeholder="选择要删除的备份配置...", options=options)
        self.backup_operations = backup_operations
        self.configs = configs
    
    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer()
        config_id = int(self.values[0])
        
        # 获取配置信息
        selected_config = None
        for config in self.configs:
            if config[0] == config_id:
                selected_config = config
                break
        
        if not selected_config:
            embed = discord.Embed(
                title="❌ 配置未找到",
                description="选择的备份配置未找到",
                color=discord.Color.red()
            )
            await interaction.edit_original_response(embed=embed, view=None)
            return
        
        # 获取位置信息用于确认界面
        config_id, guild_id, channel_id, thread_id = selected_config[:4]
        title = selected_config[5] if len(selected_config) > 5 and selected_config[5] else None
        
        try:
            bot = self.backup_operations.bot
            guild = bot.get_guild(guild_id)
            if guild:
                if thread_id:
                    channel = guild.get_channel(channel_id)
                    if channel:
                        thread = channel.get_thread(thread_id)
                        location_name = f"#{channel.name}/{thread.name if thread else (title or '未知帖子')}"
                    else:
                        location_name = f"未知频道/{title or '未知帖子'}"
                else:
                    channel = guild.get_channel(channel_id)
                    location_name = f"#{channel.name}" if channel else (title or "未知频道")
            else:
                location_name = title or "未知位置"
        except:
            location_name = title or "未知位置"
        
        # 获取统计信息
        try:
            stats = await self.backup_operations.db_manager.get_backup_stats(config_id)
            stats_text = f"消息: {stats['message_count']} 条\n文件: {stats['file_count']} 个"
        except:
            stats_text = "统计信息获取失败"
        
        # 显示确认删除界面
        embed = discord.Embed(
            title="⚠️ 确认删除备份",
            description=f"您确定要删除以下备份配置和所有相关数据吗？\n\n"
                      f"**位置**: {location_name}\n"
                      f"**统计**: {stats_text}\n\n"
                      f"⚠️ **此操作不可撤销！**",
            color=discord.Color.orange(),
            timestamp=datetime.now(timezone.utc)
        )
        
        # 创建确认删除的View
        confirm_view = DeleteBackupView(
            self.backup_operations, config_id, selected_config, location_name
        )
        
        await interaction.edit_original_response(embed=embed, view=confirm_view)