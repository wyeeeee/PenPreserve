import asyncio
import aiohttp
import logging
from typing import Optional

logger = logging.getLogger(__name__)

class NetworkDiagnostics:
    """网络诊断工具"""
    
    @staticmethod
    async def check_discord_connectivity() -> bool:
        """检查Discord连通性"""
        try:
            timeout = aiohttp.ClientTimeout(total=10)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get('https://discord.com/api/v10/gateway') as response:
                    if response.status == 200:
                        logger.info("Discord API连通性正常")
                        return True
                    else:
                        logger.warning(f"Discord API响应异常: {response.status}")
                        return False
        except Exception as e:
            logger.error(f"Discord连通性检查失败: {e}")
            return False
    
    @staticmethod
    async def check_internet_connectivity() -> bool:
        """检查基本网络连通性"""
        test_urls = [
            'https://www.google.com',
            'https://www.baidu.com',
            'https://1.1.1.1'  # Cloudflare DNS
        ]
        
        for url in test_urls:
            try:
                timeout = aiohttp.ClientTimeout(total=5)
                async with aiohttp.ClientSession(timeout=timeout) as session:
                    async with session.get(url) as response:
                        if response.status < 400:
                            logger.info(f"网络连通性正常 (测试URL: {url})")
                            return True
            except Exception as e:
                logger.debug(f"测试URL {url} 失败: {e}")
                continue
        
        logger.error("所有网络连通性测试都失败")
        return False
    
    @staticmethod
    async def diagnose_network_issues():
        """网络问题诊断"""
        logger.info("开始网络诊断...")
        
        # 检查基本网络连通性
        internet_ok = await NetworkDiagnostics.check_internet_connectivity()
        if not internet_ok:
            logger.error("❌ 网络连通性异常 - 请检查网络连接")
            return False
        
        # 检查Discord连通性
        discord_ok = await NetworkDiagnostics.check_discord_connectivity()
        if not discord_ok:
            logger.error("❌ Discord连通性异常 - 可能需要代理或等待")
            return False
        
        logger.info("✅ 网络诊断通过")
        return True

def get_network_error_advice(error: Exception) -> str:
    """根据错误类型提供网络错误建议"""
    error_str = str(error).lower()
    
    if "信号灯超时" in error_str or "winerror 121" in error_str:
        return (
            "Windows网络超时错误建议:\n"
            "1. 检查防火墙设置\n"
            "2. 暂时关闭VPN或代理\n"
            "3. 重启网络适配器\n"
            "4. 检查DNS设置(建议使用8.8.8.8或1.1.1.1)"
        )
    
    elif "cannot connect to host" in error_str:
        return (
            "连接主机失败建议:\n"
            "1. 检查网络连接\n"
            "2. 确认Discord服务正常\n"
            "3. 尝试使用VPN或更换网络\n"
            "4. 检查系统时间是否正确"
        )
    
    elif "ssl" in error_str:
        return (
            "SSL连接错误建议:\n"
            "1. 检查系统时间\n"
            "2. 更新证书存储\n"
            "3. 检查防病毒软件SSL扫描设置"
        )
    
    else:
        return (
            "通用网络错误建议:\n"
            "1. 重启应用程序\n"
            "2. 检查网络连接\n"
            "3. 稍后重试"
        )