#!/usr/bin/env python3
"""
启动Discord bot和webhook服务器的组合脚本
"""

import sys
import asyncio
import logging
import signal
from pathlib import Path

# 添加项目根目录到Python路径
sys.path.append(str(Path(__file__).parent.parent))

from config.settings import Config
from utils.logger import setup_logging
from core.bot import DiscordBot
from server.webhook_server import WebhookServer

async def main():
    """主函数"""
    print("正在启动PenPreserve完整服务...")
    
    try:
        # 加载配置
        config = Config('config/bot_config.cfg')
        
        # 设置日志
        setup_logging(config)
        
        logger = logging.getLogger(__name__)
        logger.info("配置加载完成，开始启动服务...")
        
        # 创建任务列表
        tasks = []
        
        # 创建Discord Bot
        bot = DiscordBot(config)
        
        # Discord Bot任务
        async def run_discord_bot():
            try:
                await bot.setup_hook()
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
            # 关闭Discord Bot
            asyncio.create_task(bot.close())
        
        # 注册信号处理器
        signal.signal(signal.SIGINT, signal_handler)  # Ctrl+C
        signal.signal(signal.SIGTERM, signal_handler)  # 终止信号
        
        logger.info("所有服务已启动")
        
        # 等待所有任务完成
        try:
            await asyncio.gather(*tasks)
        except asyncio.CancelledError:
            logger.info("任务被取消，正在关闭...")
        finally:
            # 确保Bot正确关闭
            if not bot.is_closed():
                await bot.close()
        
    except FileNotFoundError as e:
        print(f"错误: {e}")
        print("请确保配置文件 config.cfg 存在")
        sys.exit(1)
    except Exception as e:
        print(f"启动失败: {e}")
        logging.error(f"启动失败: {e}")
        sys.exit(1)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n程序被用户中断")
    except Exception as e:
        print(f"程序异常退出: {e}")
        sys.exit(1)