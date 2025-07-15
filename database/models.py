#!/usr/bin/env python3
"""
增强的数据库模型
支持消息备份、WebDAV文件存储、扩展的用户管理功能
"""

import aiosqlite
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, List, Tuple

class DatabaseManager:
    def __init__(self, db_path):
        self.db_path = db_path
        self.logger = logging.getLogger(__name__)
    
    async def init_db(self):
        """初始化数据库"""
        # 确保数据库目录存在
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        
        async with aiosqlite.connect(self.db_path) as db:
            # 备份配置表
            await db.execute('''
                CREATE TABLE IF NOT EXISTS backup_configs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    guild_id INTEGER NOT NULL,
                    channel_id INTEGER NOT NULL,
                    thread_id INTEGER DEFAULT NULL,
                    author_id INTEGER NOT NULL,
                    title TEXT DEFAULT NULL,
                    enabled BOOLEAN DEFAULT TRUE,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    last_check_time TIMESTAMP DEFAULT NULL,
                    UNIQUE(guild_id, channel_id, thread_id, author_id)
                )
            ''')
            
            # 检查并添加 title 字段到 backup_configs 表
            try:
                # 先检查字段是否存在
                cursor = await db.execute("PRAGMA table_info(backup_configs)")
                columns = await cursor.fetchall()
                column_names = [column[1] for column in columns]
                
                if 'title' not in column_names:
                    self.logger.info("添加 title 字段到 backup_configs 表")
                    await db.execute('ALTER TABLE backup_configs ADD COLUMN title TEXT DEFAULT NULL')
                    await db.commit()
            except Exception as e:
                self.logger.debug(f"检查/添加title字段时的错误（可能是表不存在）: {e}")
            
            # 检查并添加 last_activity_time 字段到 bot_status 表
            try:
                # 先检查字段是否存在
                cursor = await db.execute("PRAGMA table_info(bot_status)")
                columns = await cursor.fetchall()
                column_names = [column[1] for column in columns]
                
                if 'last_activity_time' not in column_names:
                    self.logger.info("添加 last_activity_time 字段到 bot_status 表")
                    await db.execute('ALTER TABLE bot_status ADD COLUMN last_activity_time TIMESTAMP')
                    await db.commit()
            except Exception as e:
                self.logger.debug(f"检查/添加字段时的错误（可能是表不存在）: {e}")
            
            # 消息备份表
            await db.execute('''
                CREATE TABLE IF NOT EXISTS message_backups (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    config_id INTEGER NOT NULL,
                    message_id INTEGER NOT NULL UNIQUE,
                    content TEXT DEFAULT '',
                    created_at TIMESTAMP NOT NULL,
                    backup_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    content_type TEXT NOT NULL DEFAULT 'channel',
                    FOREIGN KEY (config_id) REFERENCES backup_configs (id)
                )
            ''')
            
            # 文件备份表（支持WebDAV）
            await db.execute('''
                CREATE TABLE IF NOT EXISTS file_backups (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    message_backup_id INTEGER NOT NULL,
                    original_filename TEXT NOT NULL,
                    stored_filename TEXT NOT NULL,
                    file_size INTEGER NOT NULL,
                    file_url TEXT,
                    webdav_path TEXT,
                    backup_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (message_backup_id) REFERENCES message_backups (id)
                )
            ''')
            
            # Bot状态表（仅保留活动时间）
            await db.execute('''
                CREATE TABLE IF NOT EXISTS bot_status (
                    id INTEGER PRIMARY KEY,
                    last_activity_time TIMESTAMP
                )
            ''')
            
            # 创建索引
            await db.execute('CREATE INDEX IF NOT EXISTS idx_backup_configs_location ON backup_configs(guild_id, channel_id, thread_id)')
            await db.execute('CREATE INDEX IF NOT EXISTS idx_backup_configs_author ON backup_configs(author_id)')
            await db.execute('CREATE INDEX IF NOT EXISTS idx_message_backups_config ON message_backups(config_id)')
            await db.execute('CREATE INDEX IF NOT EXISTS idx_message_backups_message ON message_backups(message_id)')
            await db.execute('CREATE INDEX IF NOT EXISTS idx_file_backups_message ON file_backups(message_backup_id)')
            
            await db.commit()
            self.logger.info("数据库初始化完成")
    
    # ========== 备份配置管理 ==========
    
    async def create_backup_config(self, guild_id: int, channel_id: int, thread_id: Optional[int], author_id: int, title: str = None) -> Optional[int]:
        """创建备份配置"""
        async with aiosqlite.connect(self.db_path) as db:
            try:
                # 检查是否已存在配置
                cursor = await db.execute('''
                    SELECT id, enabled FROM backup_configs 
                    WHERE guild_id = ? AND channel_id = ? AND 
                          (thread_id = ? OR (thread_id IS NULL AND ? IS NULL)) AND 
                          author_id = ?
                ''', (guild_id, channel_id, thread_id, thread_id, author_id))
                existing = await cursor.fetchone()
                
                if existing:
                    config_id, enabled = existing
                    if enabled:
                        self.logger.warning(f"备份配置已存在且启用: ID {config_id}")
                        return config_id
                    else:
                        # 重新启用已禁用的配置，同时更新标题
                        await db.execute('''
                            UPDATE backup_configs SET enabled = TRUE, created_at = CURRENT_TIMESTAMP, title = ?
                            WHERE id = ?
                        ''', (title, config_id))
                        await db.commit()
                        self.logger.info(f"重新启用备份配置: ID {config_id}")
                        return config_id
                else:
                    # 创建新配置
                    await db.execute('''
                        INSERT INTO backup_configs (guild_id, channel_id, thread_id, author_id, title)
                        VALUES (?, ?, ?, ?, ?)
                    ''', (guild_id, channel_id, thread_id, author_id, title))
                    await db.commit()
                    
                    cursor = await db.execute('SELECT last_insert_rowid()')
                    config_id = (await cursor.fetchone())[0]
                    self.logger.info(f"创建新备份配置: ID {config_id}, 标题: {title}")
                    return config_id
                    
            except Exception as e:
                self.logger.error(f"创建备份配置失败: {e}")
                return None
    
    async def disable_backup_config(self, config_id: int):
        """禁用备份配置"""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute('UPDATE backup_configs SET enabled = FALSE WHERE id = ?', (config_id,))
            await db.commit()
            self.logger.info(f"禁用备份配置: ID {config_id}")
    
    async def get_backup_config(self, guild_id: int, channel_id: int, thread_id: Optional[int], author_id: int) -> Optional[Tuple]:
        """获取备份配置"""
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute('''
                SELECT * FROM backup_configs 
                WHERE guild_id = ? AND channel_id = ? AND 
                      (thread_id = ? OR (thread_id IS NULL AND ? IS NULL)) AND 
                      author_id = ? AND enabled = TRUE
            ''', (guild_id, channel_id, thread_id, thread_id, author_id))
            return await cursor.fetchone()
    
    async def get_all_backup_configs(self) -> List[Tuple]:
        """获取所有启用的备份配置"""
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute('SELECT * FROM backup_configs WHERE enabled = TRUE')
            return await cursor.fetchall()
    
    async def get_user_backup_configs(self, author_id: int) -> List[Tuple]:
        """获取用户的所有备份配置"""
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute('''
                SELECT * FROM backup_configs WHERE author_id = ? AND enabled = TRUE
            ''', (author_id,))
            return await cursor.fetchall()
    
    async def update_backup_config_check_time(self, config_id: int):
        """更新配置的最后检查时间"""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute('''
                UPDATE backup_configs SET last_check_time = CURRENT_TIMESTAMP WHERE id = ?
            ''', (config_id,))
            await db.commit()
    
    async def update_backup_config_title(self, config_id: int, title: str):
        """更新备份配置的标题"""
        async with aiosqlite.connect(self.db_path) as db:
            try:
                await db.execute('''
                    UPDATE backup_configs SET title = ? WHERE id = ?
                ''', (title, config_id))
                await db.commit()
                self.logger.debug(f"更新配置标题: {config_id} -> {title}")
            except Exception as e:
                self.logger.error(f"更新配置标题失败: {e}")
    
    async def get_backup_config_by_location(self, guild_id: int, channel_id: int, thread_id: Optional[int]) -> List[Tuple]:
        """根据位置获取所有备份配置（用于标题更新）"""
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute('''
                SELECT * FROM backup_configs 
                WHERE guild_id = ? AND channel_id = ? AND 
                      (thread_id = ? OR (thread_id IS NULL AND ? IS NULL)) AND enabled = TRUE
            ''', (guild_id, channel_id, thread_id, thread_id))
            return await cursor.fetchall()
    
    # ========== 消息备份管理 ==========
    
    async def save_message_backup(self, config_id: int, message_id: int, content: str, 
                                created_at: datetime, content_type: str = 'channel') -> Optional[int]:
        """保存消息备份"""
        async with aiosqlite.connect(self.db_path) as db:
            try:
                await db.execute('''
                    INSERT INTO message_backups 
                    (config_id, message_id, content, created_at, content_type)
                    VALUES (?, ?, ?, ?, ?)
                ''', (config_id, message_id, content, created_at.isoformat(), content_type))
                await db.commit()
                
                cursor = await db.execute('SELECT last_insert_rowid()')
                backup_id = (await cursor.fetchone())[0]
                return backup_id
                
            except Exception as e:
                self.logger.error(f"保存消息备份失败: {e}")
                return None
    
    async def get_message_backup_by_message_id(self, message_id: int) -> Optional[Tuple]:
        """根据消息ID获取消息备份"""
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute('''
                SELECT * FROM message_backups WHERE message_id = ?
            ''', (message_id,))
            return await cursor.fetchone()
    
    async def get_latest_message_time(self, config_id: int) -> Optional[str]:
        """获取配置的最新消息时间"""
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute('''
                SELECT MAX(created_at) FROM message_backups WHERE config_id = ?
            ''', (config_id,))
            result = await cursor.fetchone()
            return result[0] if result and result[0] else None
    
    # ========== 文件备份管理 ==========
    
    async def save_file_backup(self, message_backup_id: int, original_filename: str, 
                             stored_filename: str, file_size: int, file_url: str, 
                             webdav_path: str) -> Optional[int]:
        """保存文件备份记录"""
        async with aiosqlite.connect(self.db_path) as db:
            try:
                await db.execute('''
                    INSERT INTO file_backups 
                    (message_backup_id, original_filename, stored_filename, file_size, file_url, webdav_path)
                    VALUES (?, ?, ?, ?, ?, ?)
                ''', (message_backup_id, original_filename, stored_filename, file_size, file_url, webdav_path))
                await db.commit()
                
                cursor = await db.execute('SELECT last_insert_rowid()')
                backup_id = (await cursor.fetchone())[0]
                return backup_id
                
            except Exception as e:
                self.logger.error(f"保存文件备份失败: {e}")
                return None
    
    async def get_files_by_config(self, config_id: int) -> List[Tuple]:
        """获取配置的所有文件"""
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute('''
                SELECT fb.* FROM file_backups fb
                JOIN message_backups mb ON fb.message_backup_id = mb.id
                WHERE mb.config_id = ?
                ORDER BY fb.backup_time DESC
            ''', (config_id,))
            return await cursor.fetchall()
    
    
    # ========== Bot状态管理 ==========
    
    
    async def update_last_activity_time(self, activity_time: datetime):
        """更新最后活动时间（每次处理消息时调用）"""
        async with aiosqlite.connect(self.db_path) as db:
            try:
                await db.execute('''
                    INSERT OR REPLACE INTO bot_status (id, last_activity_time)
                    VALUES (1, ?)
                ''', (activity_time.isoformat(),))
                await db.commit()
            except Exception as e:
                self.logger.warning(f"更新最后活动时间失败: {e}")
                # 如果字段不存在，尝试添加字段后重试
                try:
                    await db.execute('ALTER TABLE bot_status ADD COLUMN last_activity_time TIMESTAMP')
                    await db.execute('''
                        INSERT OR REPLACE INTO bot_status (id, last_activity_time)
                        VALUES (1, ?)
                    ''', (activity_time.isoformat(),))
                    await db.commit()
                    self.logger.info("成功添加字段并更新活动时间")
                except Exception as e2:
                    self.logger.error(f"重试更新活动时间失败: {e2}")
    
    async def get_last_activity_time(self) -> Optional[str]:
        """获取最后活动时间"""
        async with aiosqlite.connect(self.db_path) as db:
            try:
                cursor = await db.execute('SELECT last_activity_time FROM bot_status WHERE id = 1')
                result = await cursor.fetchone()
                return result[0] if result and result[0] else None
            except Exception as e:
                self.logger.warning(f"获取最后活动时间失败: {e}")
                return None
    
    
    # ========== 统计信息 ==========
    
    async def get_backup_stats(self, config_id: Optional[int] = None) -> dict:
        """获取备份统计信息"""
        async with aiosqlite.connect(self.db_path) as db:
            if config_id:
                # 特定配置的统计
                cursor = await db.execute('''
                    SELECT COUNT(*) FROM message_backups WHERE config_id = ?
                ''', (config_id,))
                message_count = (await cursor.fetchone())[0]
                
                cursor = await db.execute('''
                    SELECT COUNT(*), COALESCE(SUM(fb.file_size), 0) 
                    FROM file_backups fb
                    JOIN message_backups mb ON fb.message_backup_id = mb.id
                    WHERE mb.config_id = ?
                ''', (config_id,))
                file_count, total_size = await cursor.fetchone()
                
                return {
                    'message_count': message_count,
                    'file_count': file_count or 0,
                    'total_size': total_size or 0
                }
            else:
                # 全局统计
                cursor = await db.execute('SELECT COUNT(*) FROM message_backups')
                message_count = (await cursor.fetchone())[0]
                
                cursor = await db.execute('SELECT COUNT(*), COALESCE(SUM(file_size), 0) FROM file_backups')
                file_count, total_size = await cursor.fetchone()
                
                cursor = await db.execute('SELECT COUNT(*) FROM backup_configs WHERE enabled = TRUE')
                config_count = (await cursor.fetchone())[0]
                
                return {
                    'config_count': config_count,
                    'message_count': message_count,
                    'file_count': file_count or 0,
                    'total_size': total_size or 0
                }