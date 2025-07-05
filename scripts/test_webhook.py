#\!/usr/bin/env python3
"""
测试webhook功能的脚本
"""

import asyncio
import aiohttp
import json
import sys
from datetime import datetime
from pathlib import Path

# 添加项目根目录到Python路径
sys.path.append(str(Path(__file__).parent.parent))

async def test_webhook():
    """测试webhook功能"""
    
    # 测试数据
    test_payload = {
        "event_type": "backup_permission_update",
        "timestamp": datetime.now().isoformat() + "Z",
        "guild_id": "123456789012345678",
        "channel_id": "987654321098765432",
        "thread_id": "456789012345678901",
        "message_id": "789012345678901234",
        "author": {
            "discord_user_id": "111222333444555666",
            "username": "测试用户",
            "display_name": "测试显示名称"
        },
        "work_info": {
            "title": "测试作品标题",
            "content_preview": "这是一个测试作品的内容预览，用于验证备份功能是否正常工作...",
            "license_type": "custom",
            "backup_allowed": True
        },
        "urls": {
            "discord_thread": "https://discord.com/channels/123456789012345678/987654321098765432/456789012345678901",
            "direct_message": "https://discord.com/channels/123456789012345678/987654321098765432/789012345678901234"
        }
    }
    
    print("开始测试webhook...")
    
    try:
        async with aiohttp.ClientSession() as session:
            # 测试健康检查
            print("\n1. 测试健康检查...")
            async with session.get("http://localhost:8080/health") as response:
                if response.status == 200:
                    result = await response.json()
                    print(f"✓ 健康检查成功: {result}")
                else:
                    print(f"✗ 健康检查失败: {response.status}")
                    return
            
            # 测试webhook端点
            print("\n2. 测试webhook端点...")
            headers = {"Content-Type": "application/json"}
            async with session.post(
                "http://localhost:8080/webhook/license-permission",
                json=test_payload,
                headers=headers
            ) as response:
                if response.status == 200:
                    result = await response.json()
                    print(f"✓ Webhook测试成功: {result}")
                else:
                    text = await response.text()
                    print(f"✗ Webhook测试失败: {response.status} - {text}")
    
    except aiohttp.ClientConnectorError:
        print("✗ 无法连接到webhook服务器，请确保服务器正在运行")
    except Exception as e:
        print(f"✗ 测试过程中出现错误: {e}")

if __name__ == "__main__":
    asyncio.run(test_webhook())
EOF < /dev/null
