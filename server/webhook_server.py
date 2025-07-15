#!/usr/bin/env python3
"""
协议授权bot webhook接收服务器
简化版 - 专注于核心业务逻辑
"""

import asyncio
import logging
from datetime import datetime
from typing import Optional
from fastapi import FastAPI, HTTPException, BackgroundTasks
from pydantic import BaseModel, validator
import uvicorn
from pathlib import Path
import sys

# 添加项目根目录到Python路径
sys.path.append(str(Path(__file__).parent.parent))

from database.models import DatabaseManager
from config.settings import Config
from utils.logger import setup_logging

logger = logging.getLogger(__name__)

# 作者信息模型
class AuthorInfo(BaseModel):
    discord_user_id: str
    username: str
    display_name: str

# 作品信息模型
class WorkInfo(BaseModel):
    title: str
    content_preview: str
    license_type: str
    backup_allowed: bool

# URL信息模型
class URLInfo(BaseModel):
    discord_thread: Optional[str] = None
    direct_message: Optional[str] = None

# 完整的Webhook数据模型
class WebhookPayload(BaseModel):
    """协议授权webhook载荷"""
    event_type: str
    timestamp: str
    guild_id: str
    channel_id: str
    thread_id: Optional[str] = None
    message_id: Optional[str] = None
    author: AuthorInfo
    work_info: WorkInfo
    urls: Optional[URLInfo] = None
    
    @validator('event_type')
    def validate_event_type(cls, v):
        if v != "backup_permission_update":
            raise ValueError("event_type must be 'backup_permission_update'")
        return v

class WebhookServer:
    def __init__(self, config: Config):
        self.config = config
        self.db_manager = DatabaseManager(config.db_filename)
        self.app = FastAPI(title="PenPreserve Webhook Server", version="2.0")
        
        # 用于通知Discord bot的队列
        self.notification_queue = asyncio.Queue()
        
        self.setup_routes()
    
    def setup_routes(self):
        """设置路由"""
        
        @self.app.post("/webhook/license-permission")
        async def handle_license_permission(
            payload: WebhookPayload,
            background_tasks: BackgroundTasks
        ):
            """处理协议授权webhook - 简化版"""
            try:
                logger.info(f"收到webhook请求: 作者 {payload.author.discord_user_id}, 操作 {'启用' if payload.work_info.backup_allowed else '暂停'}")
                
                # 转换ID
                guild_id = int(payload.guild_id)
                channel_id = int(payload.channel_id)
                thread_id = int(payload.thread_id) if payload.thread_id else None
                author_id = int(payload.author.discord_user_id)
                
                # 从payload获取backup_allowed状态
                backup_allowed = payload.work_info.backup_allowed
                
                # 检查现有配置
                existing_config = await self.db_manager.get_backup_config(
                    guild_id, channel_id, thread_id, author_id
                )
                
                if backup_allowed:
                    # 启用备份
                    if existing_config:
                        logger.info(f"备份配置已存在: {existing_config[0]}")
                        return {
                            "status": "already_enabled",
                            "message": "Backup already enabled",
                            "config_id": existing_config[0]
                        }
                    
                    # 创建新配置，使用webhook中的标题信息
                    title = payload.work_info.title if payload.work_info else None
                    config_id = await self.db_manager.create_backup_config(
                        guild_id, channel_id, thread_id, author_id, title
                    )
                    
                    if config_id:
                        # 添加到处理队列
                        notification_data = {
                            "action": "enable",
                            "config_id": config_id,
                            "guild_id": guild_id,
                            "channel_id": channel_id,
                            "thread_id": thread_id,
                            "author_id": author_id,
                            "author_info": {
                                "username": payload.author.username,
                                "display_name": payload.author.display_name
                            },
                            "work_info": {
                                "title": payload.work_info.title,
                                "content_preview": payload.work_info.content_preview
                            }
                        }
                        await self.notification_queue.put(notification_data)
                        
                        logger.info(f"创建备份配置成功: {config_id}")
                        return {
                            "status": "enabling",
                            "message": "Backup configuration created",
                            "config_id": config_id
                        }
                    else:
                        return {
                            "status": "error",
                            "message": "Failed to create backup configuration"
                        }
                
                else:
                    # 暂停备份
                    if not existing_config:
                        return {
                            "status": "not_found",
                            "message": "No backup configuration found to disable"
                        }
                    
                    config_id = existing_config[0]
                    await self.db_manager.disable_backup_config(config_id)
                    
                    # 添加到处理队列
                    notification_data = {
                        "action": "disable",
                        "config_id": config_id,
                        "guild_id": guild_id,
                        "channel_id": channel_id,
                        "thread_id": thread_id,
                        "author_id": author_id,
                        "author_info": {
                            "username": payload.author.username,
                            "display_name": payload.author.display_name
                        }
                    }
                    await self.notification_queue.put(notification_data)
                    
                    logger.info(f"禁用备份配置成功: {config_id}")
                    return {
                        "status": "disabling",
                        "message": "Backup configuration disabled",
                        "config_id": config_id
                    }
                
            except ValueError as e:
                logger.error(f"数据验证错误: {e}")
                raise HTTPException(status_code=400, detail=str(e))
            except Exception as e:
                logger.error(f"处理webhook失败: {e}")
                raise HTTPException(status_code=500, detail=str(e))
        
        @self.app.get("/health")
        async def health_check():
            """健康检查"""
            return {
                "status": "healthy",
                "timestamp": datetime.now().isoformat(),
                "version": "2.0"
            }
        
        @self.app.get("/")
        async def root():
            """根路径"""
            return {
                "message": "PenPreserve Webhook Server v2.0",
                "status": "running",
                "endpoints": ["/webhook/license-permission", "/health"]
            }
        
        @self.app.get("/stats")
        async def get_stats():
            """获取统计信息"""
            try:
                configs = await self.db_manager.get_all_backup_configs()
                return {
                    "active_configs": len(configs),
                    "queue_size": self.notification_queue.qsize(),
                    "timestamp": datetime.now().isoformat()
                }
            except Exception as e:
                logger.error(f"获取统计信息失败: {e}")
                raise HTTPException(status_code=500, detail=str(e))
    
    async def get_notification(self) -> Optional[dict]:
        """获取待处理的通知（供Discord bot调用）"""
        try:
            return await asyncio.wait_for(self.notification_queue.get(), timeout=1.0)
        except asyncio.TimeoutError:
            return None
    
    def has_pending_notifications(self) -> bool:
        """检查是否有待处理的通知"""
        return not self.notification_queue.empty()
    
    async def start_server(self, host: str = "0.0.0.0", port: int = 8080):
        """启动服务器"""
        logger.info(f"启动Webhook服务器 v2.0 在 {host}:{port}")
        
        # 初始化数据库
        await self.db_manager.init_db()
        
        # 启动服务器
        config = uvicorn.Config(
            app=self.app,
            host=host,
            port=port,
            log_level="info",
            access_log=True
        )
        server = uvicorn.Server(config)
        await server.serve()

# 全局webhook服务器实例（供Discord bot访问）
webhook_server_instance = None

def get_webhook_server() -> Optional[WebhookServer]:
    """获取webhook服务器实例"""
    return webhook_server_instance

def set_webhook_server(server: WebhookServer):
    """设置webhook服务器实例"""
    global webhook_server_instance
    webhook_server_instance = server

async def main():
    """独立运行webhook服务器"""
    try:
        # 加载配置
        config = Config()
        
        # 设置日志
        setup_logging(config)
        
        logger.info("启动独立Webhook服务器...")
        
        # 创建并启动服务器
        webhook_server = WebhookServer(config)
        set_webhook_server(webhook_server)
        await webhook_server.start_server(config.webhook_host, config.webhook_port)
        
    except Exception as e:
        logger.error(f"启动失败: {e}")
        raise

if __name__ == "__main__":
    asyncio.run(main())