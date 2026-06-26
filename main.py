"""
防刷屏卫士插件 - 主入口
独立防刷屏插件，检测群友刷屏行为并自动撤回消息和禁言
所有配置请通过 WebUI 进行
"""
import asyncio
from pathlib import Path
from astrbot.api.event import filter
from astrbot.api.star import Context, Star
from astrbot.core import AstrBotConfig
from astrbot.core.platform.sources.aiocqhttp.aiocqhttp_message_event import (
    AiocqhttpMessageEvent,
)
from astrbot.api import logger

from .config import SpamGuardConfig
from .data import SpamGuardDB
from .core.spam_handler import SpamHandler


class SpamGuardPlugin(Star):
    """防刷屏卫士插件类"""
    
    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self.context = context
        self.cfg = SpamGuardConfig(config)
        
        # 使用正确的数据目录路径
        try:
            # 尝试从 context 获取数据目录
            data_path = context.get_config().get("data_path", "/AstrBot/data")
        except Exception:
            data_path = "/AstrBot/data"
        
        spamguard_data_dir = Path(data_path) / "plugins" / "astrbot_plugin_spamguard"
        spamguard_data_dir.mkdir(parents=True, exist_ok=True)
        
        self.db = SpamGuardDB(spamguard_data_dir)
        self.spam_handler = SpamHandler(self.cfg, self.db)
        
    async def initialize(self):
        """插件初始化"""
        await self.db.init()
        logger.info("[SpamGuard] 防刷屏卫士插件已加载")
        logger.info("[SpamGuard] 请通过 WebUI 配置插件参数")
        
    @filter.platform_adapter_type(filter.PlatformAdapterType.AIOCQHTTP)
    @filter.event_message_type(filter.EventMessageType.GROUP_MESSAGE)
    async def on_group_message(self, event: AiocqhttpMessageEvent):
        """监听群消息，检测刷屏"""
        await self.spam_handler.check_and_handle_spam(event)
            
    async def terminate(self):
        """插件卸载时的清理工作"""
        await self.db.close()
        logger.info("[SpamGuard] 防刷屏卫士插件已卸载")
