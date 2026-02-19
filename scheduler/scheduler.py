import logging
from typing import Callable
from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger

logger = logging.getLogger(__name__)


class SentinelScheduler:
    """定时调度器，支持每日/每周执行任务"""

    def __init__(self, interval: str = "daily", time_str: str = "08:00"):
        """
        interval: "daily" 或 "weekly"
        time_str: 执行时间，格式 "HH:MM"
        """
        self.interval = interval
        hour, minute = map(int, time_str.split(":"))
        self.hour = hour
        self.minute = minute
        self._scheduler = BlockingScheduler()

    def _build_trigger(self) -> CronTrigger:
        if self.interval == "weekly":
            # 每周一执行
            return CronTrigger(day_of_week="mon", hour=self.hour, minute=self.minute)
        else:
            # 默认每日执行
            return CronTrigger(hour=self.hour, minute=self.minute)

    def start(self, job: Callable):
        """注册任务并启动调度器（阻塞）"""
        trigger = self._build_trigger()
        self._scheduler.add_job(job, trigger)
        schedule_desc = f"每{'周一' if self.interval == 'weekly' else '天'} {self.hour:02d}:{self.minute:02d}"
        logger.info(f"调度器已启动，执行频率：{schedule_desc}")
        print(f"[调度器] 已启动，执行频率：{schedule_desc}（按 Ctrl+C 停止）")
        try:
            self._scheduler.start()
        except (KeyboardInterrupt, SystemExit):
            print("\n[调度器] 已停止")
