import asyncio
import logging
from datetime import datetime, timezone
import aiohttp
from discord.errors import ConnectionClosed, GatewayNotFound
from .network_utils import NetworkDiagnostics, get_network_error_advice

logger = logging.getLogger(__name__)

class ReconnectManager:
    """Discord Bot重连管理器"""
    
    def __init__(self, bot):
        self.bot = bot
        self.max_retries = bot.config.max_retries
        self.base_delay = bot.config.base_retry_delay
        self.enable_diagnostics = bot.config.enable_diagnostics
        self.current_retries = 0
        self.is_reconnecting = False
    
    async def run_with_reconnect(self):
        """带重连机制运行Bot"""
        while True:
            try:
                logger.info("启动Discord Bot...")
                await self.bot.start(self.bot.config.token)
                break  # 正常退出时跳出循环
                
            except ConnectionClosed as e:
                logger.warning(f"Discord连接被关闭: {e}")
                await self._handle_reconnect("连接被关闭", e)
                
            except GatewayNotFound as e:
                logger.error(f"Discord网关未找到: {e}")
                await self._handle_reconnect("网关未找到", e)
                
            except aiohttp.ClientConnectorError as e:
                if "信号灯超时" in str(e) or "Cannot connect to host" in str(e):
                    logger.warning(f"网络连接超时: {e}")
                    await self._handle_reconnect("网络连接超时", e)
                else:
                    logger.error(f"客户端连接错误: {e}")
                    await self._handle_reconnect("客户端连接错误", e)
                    
            except OSError as e:
                if hasattr(e, 'winerror') and e.winerror == 121:  # Windows信号灯超时错误
                    logger.warning(f"Windows网络超时: {e}")
                    await self._handle_reconnect("Windows网络超时", e)
                else:
                    logger.error(f"系统错误: {e}")
                    await self._handle_reconnect("系统错误", e)
                    
            except Exception as e:
                logger.error(f"未知错误: {e}")
                await self._handle_reconnect("未知错误", e)
    
    async def _handle_reconnect(self, reason, original_error=None):
        """处理重连逻辑"""
        self.current_retries += 1
        
        if self.current_retries > self.max_retries:
            logger.error(f"重连次数超过限制 ({self.max_retries})，停止重连")
            if original_error:
                logger.error(f"错误建议: {get_network_error_advice(original_error)}")
            raise Exception("重连失败次数过多")
        
        # 计算延迟时间（指数退避）
        delay = min(self.base_delay * (2 ** (self.current_retries - 1)), 300)  # 最大5分钟
        
        logger.info(f"第 {self.current_retries} 次重连尝试 - 原因: {reason}")
        
        # 提供错误建议
        if original_error:
            advice = get_network_error_advice(original_error)
            logger.info(f"错误建议: {advice}")
        
        # 在第3次重连时进行网络诊断（如果启用）
        if self.current_retries == 3 and self.enable_diagnostics:
            logger.info("执行网络诊断...")
            network_ok = await NetworkDiagnostics.diagnose_network_issues()
            if not network_ok:
                logger.warning("网络诊断失败，但将继续尝试重连")
        
        logger.info(f"等待 {delay} 秒后重连...")
        
        # 清理现有连接
        if not self.bot.is_closed():
            try:
                await self.bot.close()
            except Exception as e:
                logger.debug(f"关闭连接时出错: {e}")
        
        # 等待重连
        await asyncio.sleep(delay)
        
        # 记录重连时间
        logger.info(f"{datetime.now(timezone.utc)} - 开始重连")
    
    def reset_retry_count(self):
        """重置重试计数（成功连接后调用）"""
        if self.current_retries > 0:
            logger.info(f"重连成功，重置重试计数 (之前: {self.current_retries})")
            self.current_retries = 0