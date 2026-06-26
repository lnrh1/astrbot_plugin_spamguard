"""
防刷屏核心处理模块 - 优化版 v2
"""
import asyncio
import time
from collections import defaultdict, deque
from astrbot.api import logger


class SpamHandler:
    """刷屏检测和拦截处理器"""
    
    def __init__(self, config, db):
        self.cfg = config
        self.db = db
        
        # 消息记录：group_id -> user_id -> deque of (timestamp, message_id)
        self.msg_timestamps: dict[str, dict[str, deque]] = defaultdict(
            lambda: defaultdict(lambda: deque())
        )
        
        # 用户上次被禁言的时间，防止短时间内重复禁言
        self.last_ban_time: dict[str, dict[str, float]] = defaultdict(
            lambda: defaultdict(float)
        )
        
        # 并发锁：防止同一用户同时被多个任务处理
        self._user_locks: dict[str, dict[str, asyncio.Lock]] = defaultdict(
            lambda: defaultdict(asyncio.Lock)
        )
    
    async def check_and_handle_spam(self, event):
        """
        检查并处理刷屏行为
        
        Args:
            event: 消息事件对象
            
        Returns:
            bool: 是否检测为刷屏并进行了处理
        """
        group_id = str(event.get_group_id())
        sender_id = str(event.get_sender_id())
        
        # 获取本群配置
        group_config = await self.db.get_group_config(int(group_id))
        
        # 排除管理员和 Bot 自己
        if sender_id == str(event.get_self_id()):
            return False
        if self.cfg.is_admin(sender_id):
            return False
        
        # 读取配置
        ban_time = group_config.get("spamming_ban_time", 60)
        spam_count = group_config.get("spamming_count", 5)
        window_seconds = group_config.get("spamming_window_seconds", 10)
        delete_msg = group_config.get("delete_message_on_spam", True)
        recall_wait = self.cfg.recall_wait_seconds
        recall_window = self.cfg.recall_time_window_seconds
        
        now = time.time()
        current_msg_id = event.message_obj.message_id
        
        # 检查是否在冷却期内（避免短时间内重复禁言）
        last_ban = self.last_ban_time[group_id].get(sender_id, 0)
        if ban_time > 0 and now - last_ban < ban_time:
            return False
        
        # 记录当前消息时间戳和消息ID
        self.msg_timestamps[group_id][sender_id].append((now, current_msg_id))
        
        # 过滤出时间窗口内的消息
        cutoff_time = now - window_seconds
        recent_records = [
            (ts, msg_id) 
            for ts, msg_id in self.msg_timestamps[group_id][sender_id] 
            if ts >= cutoff_time
        ]
        
        # 更新记录只保留窗口内的
        self.msg_timestamps[group_id][sender_id] = deque(recent_records)
        
        # 判断是否达到刷屏阈值
        if len(recent_records) < spam_count:
            return False
        
        # 获取用户锁，防止并发重复处理
        user_lock = self._user_locks[group_id][sender_id]
        if user_lock.locked():
            return False
        
        async with user_lock:
            # 二次校验，防止等待锁期间状态变化
            if self.last_ban_time[group_id].get(sender_id, 0) != last_ban:
                return False
            
            # 标记已禁言
            self.last_ban_time[group_id][sender_id] = now
            
            try:
                # 第一步：执行禁言
                if ban_time > 0:
                    await event.bot.set_group_ban(
                        group_id=int(group_id),
                        user_id=int(sender_id),
                        duration=ban_time
                    )
                    logger.info(f"[SpamGuard] 用户 {sender_id} 被禁言 {ban_time}秒")
                
                # 第二步：等待一小段时间，确保所有消息都已记录
                if recall_wait > 0:
                    await asyncio.sleep(recall_wait)
                
                # 第三步：撤回消息（包括最后一条）
                if delete_msg:
                    # 获取当前所有记录的消息
                    final_records = list(self.msg_timestamps[group_id][sender_id])
                    
                    # 过滤出撤回时间窗口内的消息
                    recall_cutoff = now - recall_window
                    records_to_recall = [
                        (ts, msg_id) 
                        for ts, msg_id in final_records 
                        if ts >= recall_cutoff
                    ]
                    
                    # 撤回所有消息（包括最后一条，不保留）
                    msg_ids_to_delete = [
                        msg_id for ts, msg_id in records_to_recall if msg_id
                    ]
                    
                    logger.info(f"[SpamGuard] 撤回 {len(msg_ids_to_delete)} 条消息 ({recall_window}秒内全部)")
                    
                    deleted_count = 0
                    for msg_id in msg_ids_to_delete:
                        try:
                            await event.bot.delete_msg(message_id=int(msg_id))
                            deleted_count += 1
                            await asyncio.sleep(0.1)
                        except Exception as e:
                            logger.warning(f"[SpamGuard] 撤回失败 {msg_id}: {e}")
                    
                    logger.info(f"[SpamGuard] 成功撤回 {deleted_count}/{len(msg_ids_to_delete)} 条")
                
                # 第四步：发送通知
                nickname = await self._get_nickname(event, sender_id)
                if ban_time > 0:
                    await event.send(
                        event.plain_result(
                            f"检测到 {nickname} 刷屏，已撤回 {recall_window}秒内所有消息并禁言 {ban_time}秒"
                        )
                    )
                else:
                    await event.send(
                        event.plain_result(
                            f"检测到 {nickname} 刷屏，已撤回 {recall_window}秒内所有消息"
                        )
                    )
                
                # 第五步：清空该用户的记录
                self.msg_timestamps[group_id][sender_id].clear()
                
                return True
                
            except Exception as e:
                logger.error(f"[SpamGuard] 禁言操作失败：{e}")
                return False
    
    async def _get_nickname(self, event, user_id: str) -> str:
        """获取用户昵称"""
        try:
            info = await event.bot.get_group_member_info(
                group_id=int(event.get_group_id()),
                user_id=int(user_id),
                no_cache=False
            )
            return info.get("nickname", f"用户{user_id}")
        except Exception:
            return f"用户{user_id}"
    
    async def get_user_stats(self, group_id: str, user_id: str) -> dict:
        """获取用户刷屏统计数据"""
        records = list(self.msg_timestamps.get(group_id, {}).get(user_id, []))
        return {
            "recent_messages": len(records),
            "timestamps": [ts for ts, msg_id in records]
        }
    
    def clear_user_record(self, group_id: str, user_id: str):
        """清除用户记录（用于管理命令重置）"""
        if group_id in self.msg_timestamps and user_id in self.msg_timestamps[group_id]:
            self.msg_timestamps[group_id][user_id].clear()
            del self.msg_timestamps[group_id][user_id]