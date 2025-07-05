#!/usr/bin/env python3
"""
PenPreserve启动脚本 - 带网络诊断
"""

import sys
import asyncio
import logging
from pathlib import Path

# 添加项目根目录到Python路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from utils.network_utils import NetworkDiagnostics
from config.settings import Config
from utils.logger import setup_logging

async def pre_startup_diagnostics():
    """启动前网络诊断"""
    print("=" * 50)
    print("🔍 启动前网络诊断")
    print("=" * 50)
    
    # 基本网络连通性检查
    print("检查基本网络连通性...")
    internet_ok = await NetworkDiagnostics.check_internet_connectivity()
    if not internet_ok:
        print("❌ 网络连通性检查失败")
        print("建议:")
        print("1. 检查网络连接")
        print("2. 检查防火墙设置")
        print("3. 尝试重启网络适配器")
        
        choice = input("\n是否继续启动? (y/N): ").lower()
        if choice != 'y':
            return False
    else:
        print("✅ 网络连通性正常")
    
    # Discord连通性检查
    print("\n检查Discord服务连通性...")
    discord_ok = await NetworkDiagnostics.check_discord_connectivity()
    if not discord_ok:
        print("❌ Discord连通性检查失败")
        print("建议:")
        print("1. 检查Discord服务状态")
        print("2. 尝试使用VPN")
        print("3. 稍后重试")
        
        choice = input("\n是否继续启动? (y/N): ").lower()
        if choice != 'y':
            return False
    else:
        print("✅ Discord连通性正常")
    
    print("\n✅ 网络诊断完成，准备启动服务...")
    return True

async def main():
    """主函数"""
    try:
        # 启动前诊断
        if not await pre_startup_diagnostics():
            print("用户取消启动")
            return
        
        print("\n" + "=" * 50)
        print("🚀 启动PenPreserve...")
        print("=" * 50)
        
        # 加载配置
        config = Config()
        
        # 设置日志
        setup_logging(config)
        
        # 导入并运行主程序
        from main import run_with_webhook
        await run_with_webhook(config)
        
    except KeyboardInterrupt:
        print("\n程序被用户中断")
    except Exception as e:
        print(f"启动失败: {e}")
        logging.error(f"启动失败: {e}")
        
        # 提供错误建议
        from utils.network_utils import get_network_error_advice
        advice = get_network_error_advice(e)
        print(f"\n错误建议:\n{advice}")

if __name__ == "__main__":
    # 在Windows上设置事件循环策略
    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    
    asyncio.run(main())