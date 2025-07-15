#!/usr/bin/env python3
"""
PenPreserve - Discord内容备份机器人
主启动文件
"""

import sys
import asyncio
import logging
import signal
import argparse
from pathlib import Path

# 添加项目根目录到Python路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from config.settings import Config
from core.bot import DiscordBot
from server.webhook_server import WebhookServer, set_webhook_server
from utils.logger import setup_logging

async def run_with_webhook(config):
    """同时运行Discord Bot和Webhook服务器"""
    logger = logging.getLogger(__name__)
    logger.info("启动PenPreserve v2.0...")
    
    # 创建任务列表
    tasks = []
    
    # 创建Discord Bot
    bot = DiscordBot(config)
    
    # 如果启用了webhook，先创建并设置webhook服务器
    webhook_server = None
    if config.webhook_enabled:
        webhook_server = WebhookServer(config)
        set_webhook_server(webhook_server)  # 设置全局实例
        logger.info(f"Webhook服务器将在 {config.webhook_host}:{config.webhook_port} 启动")
        
        # Webhook服务器任务
        async def run_webhook_server():
            try:
                await webhook_server.start_server(config.webhook_host, config.webhook_port)
            except Exception as e:
                logger.error(f"Webhook服务器运行失败: {e}")
                raise
        
        tasks.append(asyncio.create_task(run_webhook_server()))
    else:
        logger.info("Webhook服务器已禁用")
    
    # Discord Bot任务（使用重连管理器）
    async def run_discord_bot():
        try:
            await bot.reconnect_manager.run_with_reconnect()
        except Exception as e:
            logger.error(f"Discord Bot运行失败: {e}")
            raise
    
    tasks.append(asyncio.create_task(run_discord_bot()))
    
    # 设置信号处理
    shutdown_event = asyncio.Event()
    
    def signal_handler(signum, frame):
        logger.info(f"收到信号 {signum}，正在优雅关闭...")
        shutdown_event.set()
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # 创建监控关闭信号的任务
    async def monitor_shutdown():
        await shutdown_event.wait()
        logger.info("开始关闭流程...")
        for task in tasks:
            if not task.done():
                task.cancel()
        # 等待Bot正确关闭
        if not bot.is_closed():
            await bot.close()
    
    tasks.append(asyncio.create_task(monitor_shutdown()))
    
    # 等待所有任务完成
    try:
        await asyncio.gather(*tasks, return_exceptions=True)
    except asyncio.CancelledError:
        logger.info("任务被取消，正在关闭...")
    except Exception as e:
        logger.error(f"任务执行异常: {e}")
    finally:
        # 确保Bot已关闭
        if not bot.is_closed():
            logger.info("确保Bot完全关闭...")
            await bot.close()

def main():
    """主函数"""
    parser = argparse.ArgumentParser(description='PenPreserve Discord备份机器人')
    parser.add_argument('--config', default='config/bot_config.cfg', help='配置文件路径')
    
    args = parser.parse_args()
    
    print("正在启动PenPreserve...")
    
    try:
        # 加载配置
        config = Config(args.config)
        
        # 设置日志
        setup_logging(config)
        
        logger = logging.getLogger(__name__)
        logger.info("配置加载完成，开始启动服务...")
        
        # 直接运行完整服务（Bot + Webhook根据配置决定）
        asyncio.run(run_with_webhook(config))
        
    except FileNotFoundError as e:
        print(f"错误: {e}")
        print(f"请确保配置文件 {args.config} 存在")
        sys.exit(1)
    except KeyboardInterrupt:
        print("\n程序被用户中断")
    except Exception as e:
        print(f"启动失败: {e}")
        logging.error(f"启动失败: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()