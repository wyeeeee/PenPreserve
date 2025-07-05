import asyncio
import time
import logging
from typing import Dict, Optional
from collections import defaultdict

logger = logging.getLogger(__name__)

class RateLimiter:
    """Discord API速率限制器"""
    
    def __init__(self):
        # 速率限制信息
        self.rate_limits: Dict[str, Dict] = defaultdict(dict)
        # 全局速率限制
        self.global_rate_limit_until: Optional[float] = None
        # 请求队列
        self.request_queues: Dict[str, asyncio.Queue] = defaultdict(asyncio.Queue)
        # 处理器任务
        self.processor_tasks: Dict[str, asyncio.Task] = {}
        
    async def wait_for_rate_limit(self, endpoint: str, method: str = "GET"):
        """等待速率限制"""
        route = f"{method}:{endpoint}"
        
        # 检查全局速率限制
        if self.global_rate_limit_until and time.time() < self.global_rate_limit_until:
            wait_time = self.global_rate_limit_until - time.time()
            logger.warning(f"全局速率限制，等待 {wait_time:.2f} 秒")
            await asyncio.sleep(wait_time)
            
        # 检查路由特定速率限制
        if route in self.rate_limits:
            rate_limit = self.rate_limits[route]
            if rate_limit.get('reset_at', 0) > time.time():
                if rate_limit.get('remaining', 1) <= 0:
                    wait_time = rate_limit['reset_at'] - time.time()
                    logger.warning(f"路由 {route} 速率限制，等待 {wait_time:.2f} 秒")
                    await asyncio.sleep(wait_time)
    
    def update_rate_limit(self, endpoint: str, method: str, headers: Dict[str, str]):
        """更新速率限制信息"""
        route = f"{method}:{endpoint}"
        
        # 更新全局速率限制
        if 'X-RateLimit-Global' in headers:
            retry_after = float(headers.get('Retry-After', 0))
            self.global_rate_limit_until = time.time() + retry_after
            logger.warning(f"收到全局速率限制，重试时间: {retry_after} 秒")
        
        # 更新路由特定速率限制
        if 'X-RateLimit-Limit' in headers:
            limit = int(headers['X-RateLimit-Limit'])
            remaining = int(headers.get('X-RateLimit-Remaining', 0))
            reset_after = float(headers.get('X-RateLimit-Reset-After', 0))
            
            self.rate_limits[route] = {
                'limit': limit,
                'remaining': remaining,
                'reset_at': time.time() + reset_after
            }
            
            logger.debug(f"更新速率限制 {route}: {remaining}/{limit}, 重置时间: {reset_after} 秒")
    
    async def execute_with_rate_limit(self, func, endpoint: str, method: str = "GET", *args, **kwargs):
        """在速率限制下执行函数"""
        await self.wait_for_rate_limit(endpoint, method)
        
        try:
            result = await func(*args, **kwargs)
            return result
        except Exception as e:
            # 如果是速率限制异常，更新限制信息
            if hasattr(e, 'response') and hasattr(e.response, 'headers'):
                self.update_rate_limit(endpoint, method, dict(e.response.headers))
            raise

# 全局速率限制器实例
rate_limiter = RateLimiter()

async def with_rate_limit(endpoint: str, method: str = "GET"):
    """装饰器：为函数添加速率限制"""
    def decorator(func):
        async def wrapper(*args, **kwargs):
            return await rate_limiter.execute_with_rate_limit(func, endpoint, method, *args, **kwargs)
        return wrapper
    return decorator