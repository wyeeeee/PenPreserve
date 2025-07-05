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
            # 备份配置表 - 核心配置信息
            await db.execute('''
                CREATE TABLE IF NOT EXISTS backup_configs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    guild_id INTEGER NOT NULL,
                    channel_id INTEGER NOT NULL,
                    thread_id INTEGER DEFAULT NULL,
                    author_id INTEGER NOT NULL,
                    enabled BOOLEAN DEFAULT TRUE,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    last_check_time TIMESTAMP DEFAULT NULL,
                    UNIQUE(guild_id, channel_id, thread_id, author_id)
                )
            ''')
            
            # 内容记录表 - 记录帖子/频道的基本信息
            await db.execute('''
                CREATE TABLE IF NOT EXISTS content_records (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    config_id INTEGER NOT NULL,
                    content_type TEXT NOT NULL, -- 'thread' 或 'channel'
                    title TEXT,
                    first_post_content TEXT,
                    author_name TEXT NOT NULL,
                    author_display_name TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (config_id) REFERENCES backup_configs (id)
                )
            ''')
            
            # 文件下载记录表 - 记录所有下载的附件
            await db.execute('''
                CREATE TABLE IF NOT EXISTS file_downloads (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    config_id INTEGER NOT NULL,
                    message_id INTEGER NOT NULL,
                    original_filename TEXT NOT NULL,
                    saved_filename TEXT NOT NULL,
                    file_path TEXT NOT NULL,
                    file_size INTEGER NOT NULL,
                    download_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (config_id) REFERENCES backup_configs (id)
                )
            ''')
            
            # Bot状态表 - 记录启动关闭时间用于宕机恢复
            await db.execute('''
                CREATE TABLE IF NOT EXISTS bot_status (
                    id INTEGER PRIMARY KEY,
                    last_shutdown_time TIMESTAMP,
                    last_startup_time TIMESTAMP
                )
            ''')
            
            # 创建索引
            await db.execute('CREATE INDEX IF NOT EXISTS idx_backup_configs_location ON backup_configs(guild_id, channel_id, thread_id)')
            await db.execute('CREATE INDEX IF NOT EXISTS idx_backup_configs_author ON backup_configs(author_id)')
            await db.execute('CREATE INDEX IF NOT EXISTS idx_file_downloads_config ON file_downloads(config_id)')
            await db.execute('CREATE INDEX IF NOT EXISTS idx_file_downloads_message ON file_downloads(message_id)')
            
            await db.commit()
            self.logger.info("数据库初始化完成")
    
    # ========== 备份配置管理 ==========
    
    async def create_backup_config(self, guild_id: int, channel_id: int, thread_id: Optional[int], author_id: int) -> Optional[int]:
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
                        return None
                    else:
                        # 重新启用已禁用的配置
                        await db.execute('''
                            UPDATE backup_configs SET enabled = TRUE, created_at = CURRENT_TIMESTAMP 
                            WHERE id = ?
                        ''', (config_id,))
                        await db.commit()
                        self.logger.info(f"重新启用备份配置: ID {config_id}")
                        return config_id
                else:
                    # 创建新配置
                    await db.execute('''
                        INSERT INTO backup_configs (guild_id, channel_id, thread_id, author_id)
                        VALUES (?, ?, ?, ?)
                    ''', (guild_id, channel_id, thread_id, author_id))
                    await db.commit()
                    
                    cursor = await db.execute('SELECT last_insert_rowid()')
                    config_id = (await cursor.fetchone())[0]
                    self.logger.info(f"创建新备份配置: ID {config_id}")
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
    
    async def update_config_check_time(self, config_id: int):
        """更新配置的最后检查时间"""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute('''
                UPDATE backup_configs SET last_check_time = CURRENT_TIMESTAMP WHERE id = ?
            ''', (config_id,))
            await db.commit()
    
    # ========== 内容记录管理 ==========
    
    async def save_content_record(self, config_id: int, content_type: str, title: str, 
                                first_post_content: Optional[str], author_name: str, 
                                author_display_name: str) -> int:
        """保存内容记录"""
        async with aiosqlite.connect(self.db_path) as db:
            # 先删除已存在的记录
            await db.execute('DELETE FROM content_records WHERE config_id = ?', (config_id,))
            
            # 插入新记录
            await db.execute('''
                INSERT INTO content_records 
                (config_id, content_type, title, first_post_content, author_name, author_display_name)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (config_id, content_type, title, first_post_content, author_name, author_display_name))
            await db.commit()
            
            cursor = await db.execute('SELECT last_insert_rowid()')
            record_id = (await cursor.fetchone())[0]
            self.logger.info(f"保存内容记录: ID {record_id}, 类型 {content_type}, 标题 {title}")
            return record_id
    
    async def get_content_record(self, config_id: int) -> Optional[Tuple]:
        """获取内容记录"""
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute('SELECT * FROM content_records WHERE config_id = ?', (config_id,))
            return await cursor.fetchone()
    
    # ========== 文件下载管理 ==========
    
    async def record_file_download(self, config_id: int, message_id: int, original_filename: str,
                                 saved_filename: str, file_path: str, file_size: int) -> int:
        """记录文件下载"""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute('''
                INSERT INTO file_downloads 
                (config_id, message_id, original_filename, saved_filename, file_path, file_size)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (config_id, message_id, original_filename, saved_filename, file_path, file_size))
            await db.commit()
            
            cursor = await db.execute('SELECT last_insert_rowid()')
            download_id = (await cursor.fetchone())[0]
            self.logger.debug(f"记录文件下载: {saved_filename} ({file_size} bytes)")
            return download_id
    
    async def get_downloaded_files(self, config_id: int) -> List[Tuple]:
        """获取已下载的文件列表"""
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute('''
                SELECT * FROM file_downloads WHERE config_id = ? ORDER BY download_time DESC
            ''', (config_id,))
            return await cursor.fetchall()
    
    async def is_file_downloaded(self, message_id: int, original_filename: str) -> bool:
        """检查文件是否已下载"""
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute('''
                SELECT id FROM file_downloads 
                WHERE message_id = ? AND original_filename = ?
            ''', (message_id, original_filename))
            result = await cursor.fetchone()
            return result is not None
    
    # ========== 宕机恢复相关 ==========
    
    async def get_latest_message_time(self, config_id: int) -> Optional[str]:
        """获取配置的最后检查时间（用于宕机恢复）"""
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute('''
                SELECT last_check_time FROM backup_configs WHERE id = ?
            ''', (config_id,))
            result = await cursor.fetchone()
            return result[0] if result and result[0] else None
    
    async def save_startup_time(self, startup_time: datetime):
        """保存启动时间"""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute('''
                INSERT OR REPLACE INTO bot_status (id, last_startup_time) 
                VALUES (1, ?)
            ''', (startup_time,))
            await db.commit()
            self.logger.info(f"保存启动时间: {startup_time}")
    
    async def save_shutdown_time(self, shutdown_time: datetime):
        """保存关闭时间"""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute('''
                INSERT OR REPLACE INTO bot_status (id, last_shutdown_time) 
                VALUES (1, ?)
            ''', (shutdown_time,))
            await db.commit()
            self.logger.info(f"保存关闭时间: {shutdown_time}")
    
    async def get_last_shutdown_time(self) -> Optional[str]:
        """获取最后关闭时间"""
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute('SELECT last_shutdown_time FROM bot_status WHERE id = 1')
            result = await cursor.fetchone()
            return result[0] if result and result[0] else None
    
    # ========== 统计查询 ==========
    
    async def get_backup_stats(self, config_id: int) -> dict:
        """获取备份统计信息"""
        async with aiosqlite.connect(self.db_path) as db:
            # 文件数量
            cursor = await db.execute('''
                SELECT COUNT(*) FROM file_downloads WHERE config_id = ?
            ''', (config_id,))
            file_count = (await cursor.fetchone())[0]
            
            # 总文件大小
            cursor = await db.execute('''
                SELECT SUM(file_size) FROM file_downloads WHERE config_id = ?
            ''', (config_id,))
            total_size = (await cursor.fetchone())[0] or 0
            
            return {
                'file_count': file_count,
                'total_size': total_size
            }
    
    # ========== 新增管理命令支持方法 ==========
    
    async def get_total_file_count(self) -> int:
        """获取总文件数量"""
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute('SELECT COUNT(*) FROM file_downloads')
            return (await cursor.fetchone())[0]
    
    async def get_config_file_count(self, config_id: int) -> int:
        """获取指定配置的文件数量"""
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute('''
                SELECT COUNT(*) FROM file_downloads WHERE config_id = ?
            ''', (config_id,))
            return (await cursor.fetchone())[0]
    
    async def get_user_backup_configs(self, author_id: int) -> List[Tuple]:
        """获取用户的所有备份配置"""
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute('''
                SELECT * FROM backup_configs WHERE author_id = ? AND enabled = TRUE
                ORDER BY created_at DESC
            ''', (author_id,))
            return await cursor.fetchall()
    
    async def get_total_config_count(self) -> int:
        """获取总配置数量"""
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute('SELECT COUNT(*) FROM backup_configs WHERE enabled = TRUE')
            return (await cursor.fetchone())[0]
    
    async def get_total_record_count(self) -> int:
        """获取总内容记录数量"""
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute('SELECT COUNT(*) FROM content_records')
            return (await cursor.fetchone())[0]
    
    async def get_recent_active_configs(self, limit: int = 5) -> List[Tuple]:
        """获取最近活跃的配置"""
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute('''
                SELECT * FROM backup_configs 
                WHERE enabled = TRUE AND last_check_time IS NOT NULL
                ORDER BY last_check_time DESC 
                LIMIT ?
            ''', (limit,))
            return await cursor.fetchall()