"""
防刷屏插件数据库操作模块
"""
import sqlite3
import asyncio
from pathlib import Path
from astrbot.api import logger


class SpamGuardDB:
    """防刷屏插件数据库类"""
    
    def __init__(self, data_dir):
        # 确保 data_dir 是 Path 对象
        from pathlib import Path
        if not isinstance(data_dir, Path):
            data_dir = Path(data_dir)
        
        # 创建数据目录（如果不存在）
        data_dir.mkdir(parents=True, exist_ok=True)
        
        self.db_path = data_dir / "spamguard_data.db"
        self.lock = asyncio.Lock()
        
    async def init(self):
        """初始化数据库表"""
        async with self.lock:
            conn = sqlite3.connect(str(self.db_path))
            cursor = conn.cursor()
            
            # 创建群配置表
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS group_config (
                    group_id INTEGER PRIMARY KEY,
                    spamming_count INTEGER DEFAULT 5,
                    spamming_window_seconds INTEGER DEFAULT 10,
                    spamming_ban_time INTEGER DEFAULT 60,
                    delete_message_on_spam INTEGER DEFAULT 1
                )
            """)
            
            # 创建用户刷屏记录表（用于持久化）
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS spam_records (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    group_id INTEGER NOT NULL,
                    user_id INTEGER NOT NULL,
                    timestamp REAL NOT NULL,
                    message_count INTEGER DEFAULT 1,
                    FOREIGN KEY (group_id) REFERENCES group_config(group_id)
                )
            """)
            
            # 创建索引加速查询
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_spam_records_group_user 
                ON spam_records(group_id, user_id)
            """)
            
            conn.commit()
            conn.close()
            logger.info("[SpamGuard] 数据库初始化完成")
            
    async def get_group_config(self, group_id: int) -> dict:
        """获取群组配置，不存在则返回默认值"""
        async with self.lock:
            conn = sqlite3.connect(str(self.db_path))
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT spamming_count, spamming_window_seconds, 
                       spamming_ban_time, delete_message_on_spam
                FROM group_config WHERE group_id = ?
            """, (group_id,))
            
            row = cursor.fetchone()
            conn.close()
            
            if row:
                return {
                    "spamming_count": row[0],
                    "spamming_window_seconds": row[1],
                    "spamming_ban_time": row[2],
                    "delete_message_on_spam": bool(row[3])
                }
            else:
                # 插入默认配置
                await self._insert_default_config(group_id)
                return {
                    "spamming_count": 5,
                    "spamming_window_seconds": 10,
                    "spamming_ban_time": 60,
                    "delete_message_on_spam": True
                }
    
    async def _insert_default_config(self, group_id: int):
        """插入默认群配置"""
        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO group_config (group_id, spamming_count, spamming_window_seconds, 
                                      spamming_ban_time, delete_message_on_spam)
            VALUES (?, ?, ?, ?, ?)
        """, (group_id, 5, 10, 60, 1))
        conn.commit()
        conn.close()
    
    async def set_group_config(self, group_id: int, key: str, value):
        """设置群组配置项"""
        async with self.lock:
            conn = sqlite3.connect(str(self.db_path))
            cursor = conn.cursor()
            
            # 确保配置存在
            cursor.execute("SELECT 1 FROM group_config WHERE group_id = ?", (group_id,))
            if not cursor.fetchone():
                await self._insert_default_config(group_id)
            
            column_map = {
                "spamming_count": "spamming_count",
                "spamming_window_seconds": "spamming_window_seconds",
                "spamming_ban_time": "spamming_ban_time",
                "delete_message_on_spam": "delete_message_on_spam"
            }
            
            if key in column_map:
                column = column_map[key]
                cursor.execute(f"UPDATE group_config SET {column} = ? WHERE group_id = ?", 
                             (value, group_id))
                conn.commit()
            
            conn.close()
    
    async def close(self):
        """关闭数据库连接（如有需要可实现连接池）"""
        pass