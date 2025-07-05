import aiosqlite
import logging
from datetime import datetime
from pathlib import Path

class DatabaseManager:
    def __init__(self, db_path):
        self.db_path = db_path
        self.logger = logging.getLogger(__name__)
    
    async def init_db(self):
        """初始化数据库"""
        # 确保数据库目录存在
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        
        async with aiosqlite.connect(self.db_path) as db:
            # 创建备份配置表
            await db.execute('''
                CREATE TABLE IF NOT EXISTS backup_configs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    guild_id INTEGER NOT NULL,
                    channel_id INTEGER NOT NULL,
                    thread_id INTEGER DEFAULT NULL,
                    author_id INTEGER NOT NULL,
                    enabled BOOLEAN DEFAULT TRUE,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    last_scan_time TIMESTAMP DEFAULT NULL,
                    UNIQUE(guild_id, channel_id, thread_id, author_id)
                )
            ''')
            
            # 创建消息备份表
            await db.execute('''
                CREATE TABLE IF NOT EXISTS message_backups (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    config_id INTEGER NOT NULL,
                    message_id INTEGER NOT NULL UNIQUE,
                    author_id INTEGER NOT NULL,
                    content TEXT,
                    created_at TIMESTAMP NOT NULL,
                    backed_up_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (config_id) REFERENCES backup_configs (id)
                )
            ''')
            
            # 创建文件备份表
            await db.execute('''
                CREATE TABLE IF NOT EXISTS file_backups (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    message_backup_id INTEGER NOT NULL,
                    filename TEXT NOT NULL,
                    file_size INTEGER NOT NULL,
                    file_url TEXT NOT NULL,
                    file_data BLOB,
                    backed_up_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (message_backup_id) REFERENCES message_backups (id)
                )
            ''')
            
            # 创建Bot状态表
            await db.execute('''
                CREATE TABLE IF NOT EXISTS bot_status (
                    id INTEGER PRIMARY KEY,
                    last_shutdown_time TIMESTAMP,
                    last_startup_time TIMESTAMP
                )
            ''')
            
            # 创建作者信息表
            await db.execute('''
                CREATE TABLE IF NOT EXISTS authors (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    discord_user_id INTEGER NOT NULL UNIQUE,
                    username TEXT NOT NULL,
                    display_name TEXT,
                    license_type TEXT,
                    backup_allowed BOOLEAN DEFAULT FALSE,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # 创建扫描任务表
            await db.execute('''
                CREATE TABLE IF NOT EXISTS scan_tasks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    config_id INTEGER NOT NULL,
                    guild_id INTEGER NOT NULL,
                    channel_id INTEGER NOT NULL,
                    thread_id INTEGER DEFAULT NULL,
                    author_id INTEGER NOT NULL,
                    work_title TEXT,
                    content_preview TEXT,
                    license_type TEXT,
                    status TEXT DEFAULT 'pending',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    started_at TIMESTAMP DEFAULT NULL,
                    completed_at TIMESTAMP DEFAULT NULL,
                    error_message TEXT DEFAULT NULL,
                    FOREIGN KEY (config_id) REFERENCES backup_configs (id),
                    FOREIGN KEY (author_id) REFERENCES authors (discord_user_id)
                )
            ''')
            
            # 创建内容类型表（区分帖子和频道子区）
            await db.execute('''
                CREATE TABLE IF NOT EXISTS content_types (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    config_id INTEGER NOT NULL,
                    content_type TEXT NOT NULL,
                    backup_rules TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (config_id) REFERENCES backup_configs (id)
                )
            ''')
            
            # 创建索引
            await db.execute('CREATE INDEX IF NOT EXISTS idx_backup_configs_channel ON backup_configs(guild_id, channel_id)')
            await db.execute('CREATE INDEX IF NOT EXISTS idx_message_backups_message ON message_backups(message_id)')
            await db.execute('CREATE INDEX IF NOT EXISTS idx_message_backups_author ON message_backups(author_id)')
            await db.execute('CREATE INDEX IF NOT EXISTS idx_authors_discord_id ON authors(discord_user_id)')
            await db.execute('CREATE INDEX IF NOT EXISTS idx_scan_tasks_status ON scan_tasks(status)')
            await db.execute('CREATE INDEX IF NOT EXISTS idx_scan_tasks_config ON scan_tasks(config_id)')
            
            await db.commit()
            self.logger.info("数据库初始化完成")
    
    async def create_backup_config(self, guild_id, channel_id, thread_id, author_id):
        """创建备份配置"""
        async with aiosqlite.connect(self.db_path) as db:
            try:
                await db.execute('''
                    INSERT INTO backup_configs (guild_id, channel_id, thread_id, author_id)
                    VALUES (?, ?, ?, ?)
                ''', (guild_id, channel_id, thread_id, author_id))
                await db.commit()
                
                # 获取创建的配置ID
                cursor = await db.execute('SELECT last_insert_rowid()')
                config_id = (await cursor.fetchone())[0]
                
                self.logger.info(f"创建备份配置 ID: {config_id}, 频道: {channel_id}, 作者: {author_id}")
                return config_id
            except aiosqlite.IntegrityError:
                self.logger.warning(f"备份配置已存在: 频道 {channel_id}, 作者 {author_id}")
                return None
    
    async def get_backup_config(self, guild_id, channel_id, thread_id, author_id):
        """获取备份配置"""
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute('''
                SELECT * FROM backup_configs 
                WHERE guild_id = ? AND channel_id = ? AND 
                      (thread_id = ? OR (thread_id IS NULL AND ? IS NULL)) AND 
                      author_id = ? AND enabled = TRUE
            ''', (guild_id, channel_id, thread_id, thread_id, author_id))
            result = await cursor.fetchone()
            
            # 添加调试日志
            self.logger.info(f"查询备份配置 - 服务器: {guild_id}, 频道: {channel_id}, 帖子: {thread_id}, 作者: {author_id}, 结果: {'找到' if result else '未找到'}")
            
            return result
    
    async def get_all_backup_configs(self):
        """获取所有启用的备份配置"""
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute('SELECT * FROM backup_configs WHERE enabled = TRUE')
            return await cursor.fetchall()
    
    async def backup_message(self, config_id, message_id, author_id, content, created_at):
        """备份消息"""
        async with aiosqlite.connect(self.db_path) as db:
            try:
                await db.execute('''
                    INSERT INTO message_backups (config_id, message_id, author_id, content, created_at)
                    VALUES (?, ?, ?, ?, ?)
                ''', (config_id, message_id, author_id, content, created_at))
                await db.commit()
                
                # 获取备份消息ID
                cursor = await db.execute('SELECT last_insert_rowid()')
                backup_id = (await cursor.fetchone())[0]
                
                self.logger.info(f"备份消息 ID: {message_id}, 作者: {author_id}")
                return backup_id
            except aiosqlite.IntegrityError:
                self.logger.warning(f"消息已备份: {message_id}")
                return None
    
    async def backup_file(self, message_backup_id, filename, file_size, file_url, file_data=None):
        """备份文件"""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute('''
                INSERT INTO file_backups (message_backup_id, filename, file_size, file_url, file_data)
                VALUES (?, ?, ?, ?, ?)
            ''', (message_backup_id, filename, file_size, file_url, file_data))
            await db.commit()
            self.logger.info(f"备份文件: {filename}, 大小: {file_size}")
    
    async def update_last_scan_time(self, config_id):
        """更新最后扫描时间"""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute('''
                UPDATE backup_configs 
                SET last_scan_time = CURRENT_TIMESTAMP 
                WHERE id = ?
            ''', (config_id,))
            await db.commit()
    
    async def get_latest_message_time(self, config_id):
        """获取最新消息时间"""
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute('''
                SELECT MAX(created_at) FROM message_backups 
                WHERE config_id = ?
            ''', (config_id,))
            result = await cursor.fetchone()
            return result[0] if result and result[0] else None
    
    async def disable_backup_config(self, config_id):
        """禁用备份配置"""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute('UPDATE backup_configs SET enabled = FALSE WHERE id = ?', (config_id,))
            await db.commit()
            self.logger.info(f"禁用备份配置 ID: {config_id}")
    
    async def save_shutdown_time(self, shutdown_time):
        """保存关闭时间"""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute('''
                INSERT OR REPLACE INTO bot_status (id, last_shutdown_time) 
                VALUES (1, ?)
            ''', (shutdown_time,))
            await db.commit()
            self.logger.info(f"保存关闭时间: {shutdown_time}")
    
    async def save_startup_time(self, startup_time):
        """保存启动时间"""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute('''
                INSERT OR REPLACE INTO bot_status (id, last_startup_time) 
                VALUES (1, ?)
            ''', (startup_time,))
            await db.commit()
            self.logger.info(f"保存启动时间: {startup_time}")
    
    async def get_last_shutdown_time(self):
        """获取最后关闭时间"""
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute('SELECT last_shutdown_time FROM bot_status WHERE id = 1')
            result = await cursor.fetchone()
            return result[0] if result and result[0] else None
    
    async def get_last_startup_time(self):
        """获取最后启动时间"""
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute('SELECT last_startup_time FROM bot_status WHERE id = 1')
            result = await cursor.fetchone()
            return result[0] if result and result[0] else None
    
    async def save_or_update_author(self, discord_user_id, username, display_name, license_type, backup_allowed):
        """保存或更新作者信息"""
        async with aiosqlite.connect(self.db_path) as db:
            try:
                await db.execute('''
                    INSERT OR REPLACE INTO authors 
                    (discord_user_id, username, display_name, license_type, backup_allowed, updated_at)
                    VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                ''', (discord_user_id, username, display_name, license_type, backup_allowed))
                await db.commit()
                self.logger.info(f"保存作者信息: {username} (ID: {discord_user_id})")
            except Exception as e:
                self.logger.error(f"保存作者信息失败: {e}")
                raise
    
    async def get_author_by_discord_id(self, discord_user_id):
        """通过Discord用户ID获取作者信息"""
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute('''
                SELECT * FROM authors WHERE discord_user_id = ?
            ''', (discord_user_id,))
            return await cursor.fetchone()
    
    async def create_scan_task(self, config_id, guild_id, channel_id, thread_id, author_id, 
                              work_title, content_preview, license_type):
        """创建扫描任务"""
        async with aiosqlite.connect(self.db_path) as db:
            try:
                await db.execute('''
                    INSERT INTO scan_tasks 
                    (config_id, guild_id, channel_id, thread_id, author_id, 
                     work_title, content_preview, license_type)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ''', (config_id, guild_id, channel_id, thread_id, author_id, 
                      work_title, content_preview, license_type))
                await db.commit()
                
                cursor = await db.execute('SELECT last_insert_rowid()')
                task_id = (await cursor.fetchone())[0]
                
                self.logger.info(f"创建扫描任务 ID: {task_id}")
                return task_id
            except Exception as e:
                self.logger.error(f"创建扫描任务失败: {e}")
                raise
    
    async def get_pending_scan_tasks(self):
        """获取待处理的扫描任务"""
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute('''
                SELECT * FROM scan_tasks WHERE status = 'pending' ORDER BY created_at ASC
            ''')
            return await cursor.fetchall()
    
    async def update_scan_task_status(self, task_id, status, error_message=None):
        """更新扫描任务状态"""
        async with aiosqlite.connect(self.db_path) as db:
            if status == 'in_progress':
                await db.execute('''
                    UPDATE scan_tasks SET status = ?, started_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                ''', (status, task_id))
            elif status == 'completed':
                await db.execute('''
                    UPDATE scan_tasks SET status = ?, completed_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                ''', (status, task_id))
            elif status == 'failed':
                await db.execute('''
                    UPDATE scan_tasks SET status = ?, error_message = ?, completed_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                ''', (status, error_message, task_id))
            await db.commit()
            self.logger.info(f"更新扫描任务 {task_id} 状态: {status}")
    
    async def save_content_type(self, config_id, content_type, backup_rules):
        """保存内容类型和备份规则"""
        async with aiosqlite.connect(self.db_path) as db:
            try:
                await db.execute('''
                    INSERT INTO content_types (config_id, content_type, backup_rules)
                    VALUES (?, ?, ?)
                ''', (config_id, content_type, backup_rules))
                await db.commit()
                self.logger.info(f"保存内容类型: {content_type}")
            except Exception as e:
                self.logger.error(f"保存内容类型失败: {e}")
                raise
    
    async def get_content_type_by_config(self, config_id):
        """通过配置ID获取内容类型"""
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute('''
                SELECT * FROM content_types WHERE config_id = ?
            ''', (config_id,))
            return await cursor.fetchone() 