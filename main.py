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
from server.webhook_server import WebhookServer
from utils.logger import setup_logging

async def run_bot_only(config):
    """仅运行Discord Bot"""
    logger = logging.getLogger(__name__)
    logger.info("启动Discord Bot...")
    
    bot = DiscordBot(config)
    
    # 设置信号处理
    def signal_handler(signum, frame):
        logger.info(f"收到信号 {signum}，正在优雅关闭...")
        asyncio.create_task(bot.close())
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    try:
        await bot.start(config.token)
    except Exception as e:
        logger.error(f"Discord Bot运行失败: {e}")
        raise
    finally:
        if not bot.is_closed():
            await bot.close()

async def run_with_webhook(config):
    """同时运行Discord Bot和Webhook服务器"""
    logger = logging.getLogger(__name__)
    logger.info("启动完整服务（Bot + Webhook）...")
    
    # 创建任务列表
    tasks = []
    
    # 创建Discord Bot
    bot = DiscordBot(config)
    
    # Discord Bot任务
    async def run_discord_bot():
        try:
            await bot.start(config.token)
        except Exception as e:
            logger.error(f"Discord Bot运行失败: {e}")
            raise
    
    tasks.append(asyncio.create_task(run_discord_bot()))
    
    # 如果启用了webhook，创建webhook服务器
    if config.webhook_enabled:
        webhook_server = WebhookServer(config)
        
        # Webhook服务器任务
        async def run_webhook_server():
            try:
                await webhook_server.start_server(config.webhook_host, config.webhook_port)
            except Exception as e:
                logger.error(f"Webhook服务器运行失败: {e}")
                raise
        
        tasks.append(asyncio.create_task(run_webhook_server()))
        logger.info(f"Webhook服务器将在 {config.webhook_host}:{config.webhook_port} 启动")
    else:
        logger.info("Webhook服务器已禁用")
    
    # 设置信号处理
    def signal_handler(signum, frame):
        logger.info(f"收到信号 {signum}，正在优雅关闭...")
        for task in tasks:
            task.cancel()
        asyncio.create_task(bot.close())
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # 等待所有任务完成
    try:
        await asyncio.gather(*tasks)
    except asyncio.CancelledError:
        logger.info("任务被取消，正在关闭...")
    finally:
        if not bot.is_closed():
            await bot.close()

def main():
    """主函数"""
    parser = argparse.ArgumentParser(description='PenPreserve Discord备份机器人')
    parser.add_argument('--webhook', action='store_true', help='同时启动Webhook服务器')
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
        
        # 根据参数选择运行模式
        if args.webhook:
            asyncio.run(run_with_webhook(config))
        else:
            asyncio.run(run_bot_only(config))
        
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