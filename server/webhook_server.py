#!/usr/bin/env python3
"""
协议授权bot webhook接收服务器
"""

import asyncio
import logging
import json
from datetime import datetime
from typing import Dict, Any, Optional
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

# 配置日志
logger = logging.getLogger(__name__)

# 数据模型
class Author(BaseModel):
    discord_user_id: str
    username: str
    display_name: str

class WorkInfo(BaseModel):
    title: str
    content_preview: str
    license_type: str
    backup_allowed: bool

class URLs(BaseModel):
    discord_thread: str
    direct_message: str

class WebhookPayload(BaseModel):
    event_type: str
    timestamp: str
    guild_id: str
    channel_id: str
    thread_id: str
    message_id: str
    author: Author
    work_info: WorkInfo
    urls: URLs
    
    @validator('event_type')
    def validate_event_type(cls, v):
        if v != "backup_permission_update":
            raise ValueError("event_type must be 'backup_permission_update'")
        return v
    
    @validator('timestamp')
    def validate_timestamp(cls, v):
        try:
            datetime.fromisoformat(v.replace('Z', '+00:00'))
        except ValueError:
            raise ValueError("timestamp must be in ISO 8601 format")
        return v

class WebhookServer:
    def __init__(self, config: Config):
        self.config = config
        self.db_manager = DatabaseManager(config.db_filename)
        self.app = FastAPI(title="PenPreserve Webhook Server")
        self.setup_routes()
        
    def setup_routes(self):
        """设置路由"""
        
        @self.app.post("/webhook/license-permission")
        async def handle_license_permission(
            payload: WebhookPayload,
            background_tasks: BackgroundTasks
        ):
            """处理协议授权webhook"""
            try:
                logger.info(f"收到协议授权webhook: {payload.event_type}")
                logger.info(f"作者: {payload.author.username}, 允许备份: {payload.work_info.backup_allowed}")
                
                # 只处理允许备份的请求
                if not payload.work_info.backup_allowed:
                    logger.info("作者不允许备份，跳过处理")
                    return {"status": "skipped", "message": "Backup not allowed"}
                
                # 后台处理备份权限更新
                background_tasks.add_task(
                    self.process_backup_permission,
                    payload
                )
                
                return {"status": "accepted", "message": "Backup permission update accepted"}
                
            except Exception as e:
                logger.error(f"处理webhook失败: {e}")
                raise HTTPException(status_code=500, detail=str(e))
        
        @self.app.get("/health")
        async def health_check():
            """健康检查"""
            return {"status": "healthy", "timestamp": datetime.now().isoformat()}
        
        @self.app.get("/")
        async def root():
            """根路径"""
            return {"message": "PenPreserve Webhook Server", "status": "running"}
    
    async def process_backup_permission(self, payload: WebhookPayload):
        """处理备份权限更新"""
        try:
            # 转换ID为整数
            guild_id = int(payload.guild_id)
            channel_id = int(payload.channel_id)
            thread_id = int(payload.thread_id) if payload.thread_id != payload.channel_id else None
            author_id = int(payload.author.discord_user_id)
            
            logger.info(f"处理备份权限更新:")
            logger.info(f"  服务器ID: {guild_id}")
            logger.info(f"  频道ID: {channel_id}")
            logger.info(f"  帖子ID: {thread_id}")
            logger.info(f"  作者ID: {author_id}")
            logger.info(f"  作品标题: {payload.work_info.title}")
            
            # 保存作者信息
            await self.db_manager.save_or_update_author(
                author_id,
                payload.author.username,
                payload.author.display_name,
                payload.work_info.license_type,
                payload.work_info.backup_allowed
            )
            
            # 创建备份配置
            config_id = await self.db_manager.create_backup_config(
                guild_id, channel_id, thread_id, author_id
            )
            
            if config_id:
                logger.info(f"成功创建备份配置 ID: {config_id}")
                
                # 确定内容类型和备份规则
                content_type = "thread" if thread_id else "channel"
                backup_rules = self.get_backup_rules(content_type)
                
                # 保存内容类型
                await self.db_manager.save_content_type(config_id, content_type, backup_rules)
                
                # 触发历史内容扫描
                await self.trigger_history_scan(
                    guild_id, channel_id, thread_id, author_id, config_id, payload
                )
                
            else:
                logger.warning("备份配置已存在或创建失败")
                
        except Exception as e:
            logger.error(f"处理备份权限更新失败: {e}")
    
    def get_backup_rules(self, content_type: str) -> str:
        """获取备份规则JSON"""
        if content_type == "thread":
            rules = {
                "backup_thread_title": True,
                "backup_first_post": True,
                "backup_author_posts_only": True,
                "backup_attachments": True,
                "skip_other_users": True
            }
        else:  # channel
            rules = {
                "backup_channel_name": True,
                "backup_author_messages_only": True,
                "backup_attachments": True,
                "skip_other_users": True
            }
        return json.dumps(rules)
    
    async def trigger_history_scan(self, guild_id: int, channel_id: int, thread_id: Optional[int], 
                                 author_id: int, config_id: int, payload: WebhookPayload):
        """触发历史内容扫描"""
        try:
            # 这里需要与Discord bot通信来触发历史扫描
            # 由于webhook服务器独立运行，我们需要通过数据库或其他方式通知bot
            
            # 创建扫描任务记录
            scan_task = {
                "config_id": config_id,
                "guild_id": guild_id,
                "channel_id": channel_id,
                "thread_id": thread_id,
                "author_id": author_id,
                "work_title": payload.work_info.title,
                "content_preview": payload.work_info.content_preview,
                "license_type": payload.work_info.license_type,
                "created_at": datetime.now().isoformat(),
                "status": "pending"
            }
            
            # 将扫描任务保存到数据库
            await self.save_scan_task(scan_task)
            
            logger.info(f"已创建历史扫描任务 - 配置ID: {config_id}")
            
        except Exception as e:
            logger.error(f"触发历史扫描失败: {e}")
    
    async def save_scan_task(self, scan_task: Dict[str, Any]):
        """保存扫描任务到数据库"""
        try:
            # 创建扫描任务
            task_id = await self.db_manager.create_scan_task(
                scan_task["config_id"],
                scan_task["guild_id"],
                scan_task["channel_id"],
                scan_task["thread_id"],
                scan_task["author_id"],
                scan_task["work_title"],
                scan_task["content_preview"],
                scan_task["license_type"]
            )
            
            logger.info(f"已保存扫描任务 ID: {task_id}")
            
        except Exception as e:
            logger.error(f"保存扫描任务失败: {e}")
    
    async def start_server(self, host: str = "0.0.0.0", port: int = 8080):
        """启动服务器"""
        logger.info(f"启动webhook服务器 {host}:{port}")
        
        # 初始化数据库
        await self.db_manager.init_db()
        
        # 启动服务器
        config = uvicorn.Config(
            app=self.app,
            host=host,
            port=port,
            log_level="info"
        )
        server = uvicorn.Server(config)
        await server.serve()

async def main():
    """主函数"""
    try:
        # 加载配置
        config = Config()
        
        # 设置日志
        setup_logging(config)
        
        logger.info("启动webhook服务器...")
        
        # 创建并启动服务器
        webhook_server = WebhookServer(config)
        await webhook_server.start_server()
        
    except Exception as e:
        logger.error(f"启动失败: {e}")
        raise

if __name__ == "__main__":
    asyncio.run(main())