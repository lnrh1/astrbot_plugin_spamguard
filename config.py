"""
防刷屏插件配置处理模块
"""
from pathlib import Path
from astrbot.core.config.astrbot_config import AstrBotConfig


class SpamGuardConfig:
    """防刷屏插件配置类"""
    
    def __init__(self, config: AstrBotConfig):
        self.config = config
        
        # 从配置中读取参数，使用默认值作为回退
        self.spamming_count = config.get("spamming_count", 5)
        self.spamming_window_seconds = config.get("spamming_window_seconds", 10)
        self.spamming_ban_time = config.get("spamming_ban_time", 60)
        self.delete_message_on_spam = config.get("delete_message_on_spam", True)
        self.recall_wait_seconds = config.get("recall_wait_seconds", 0.5)
        self.recall_time_window_seconds = config.get("recall_time_window_seconds", 5)
        
        # 解析管理员 QQ 列表
        admin_ids_str = config.get("admin_ids", "")
        self.admin_ids = self._parse_admin_ids(admin_ids_str)
        
    def _parse_admin_ids(self, admin_ids_str: str) -> set:
        """解析管理员 QQ 列表"""
        if not admin_ids_str:
            return set()
        
        ids = set()
        for item in admin_ids_str.split():
            item = item.strip()
            if item.isdigit():
                ids.add(item)
        return ids
    
    def is_admin(self, user_id: str) -> bool:
        """检查用户是否为管理员"""
        return user_id in self.admin_ids
    
    def update_from_config(self):
        """从主配置更新运行时配置"""
        self.spamming_count = self.config.get("spamming_count", 5)
        self.spamming_window_seconds = self.config.get("spamming_window_seconds", 10)
        self.spamming_ban_time = self.config.get("spamming_ban_time", 60)
        self.delete_message_on_spam = self.config.get("delete_message_on_spam", True)
        self.recall_wait_seconds = self.config.get("recall_wait_seconds", 0.5)
        self.recall_time_window_seconds = self.config.get("recall_time_window_seconds", 5)
        
        admin_ids_str = self.config.get("admin_ids", "")
        self.admin_ids = self._parse_admin_ids(admin_ids_str)