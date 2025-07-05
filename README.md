# PenPreserve - Discord内容备份机器人

一个功能强大的Discord备份机器人，专门用于与协议授权bot联动，自动备份获得授权的作者在频道或帖子中的消息和附件。

## 功能特点

- 🔄 **智能备份**: 自动备份指定作者的消息和附件
- 📁 **多格式支持**: 支持图片、文档、JSON等多种文件类型
- 🛡️ **安全可靠**: 只备份作者自己的内容，不会备份其他人的消息
- 🔧 **易于配置**: 使用配置文件进行灵活配置
- 📊 **状态监控**: 实时查看备份状态和统计信息
- 🚀 **宕机恢复**: 自动恢复宕机期间的消息备份
- 🤝 **协议联动**: 与协议授权bot联动，自动处理备份权限
- 🎯 **差异化备份**: 支持帖子和频道子区的不同备份策略
- ⚡ **Webhook支持**: 实时接收协议授权更新
- 🔍 **历史扫描**: 自动扫描和备份历史内容

## 安装步骤

1. **克隆或下载项目**
   ```bash
   git clone <repository-url>
   cd discord-backup-bot
   ```

2. **安装依赖**
   ```bash
   pip install -r requirements.txt
   ```

3. **配置机器人**
   - 编辑 `config/bot_config.cfg` 文件
   - 替换 `token` 为你的机器人令牌
   - 根据需要调整其他配置

4. **运行机器人**
   
   - 仅运行Discord Bot:
   ```bash
   python main.py
   ```
   
   - 同时运行Discord Bot和Webhook服务器:
   ```bash
   python main.py --webhook
   ```
   
   - 使用自定义配置文件:
   ```bash
   python main.py --config path/to/config.cfg
   ```

## 配置说明

### config/bot_config.cfg 文件配置

```ini
[bot]
token=YOUR_BOT_TOKEN_HERE        # 机器人令牌
prefix=!                         # 命令前缀
description=Discord Bot Framework # 机器人描述
activity_type=playing            # 活动类型
activity_name=with Discord.py    # 活动名称

[logging]
level=INFO                       # 日志级别
format=[%(asctime)s] [%(levelname)s] %(name)s: %(message)s
file_enabled=true                # 是否启用文件日志
console_enabled=true             # 是否启用控制台日志

[database]
filename=bot_data.db             # 数据库文件名
max_scan_messages=1000           # 最大扫描消息数

[backup]
allowed_extensions=json,txt,png,jpg,jpeg,gif,pdf,doc,docx  # 允许的文件扩展名
max_file_size=10485760           # 最大文件大小(10MB)

[webhook]
host=0.0.0.0                     # Webhook服务器主机
port=8080                        # Webhook服务器端口
enabled=true                     # 是否启用Webhook服务器
```

## 使用方法

### 斜杠命令（备用管理）

1. **`/enable_backup`** - 手动为当前频道/帖子启用备份功能（备用选项）
2. **`/disable_backup`** - 禁用当前频道/帖子的备份功能
3. **`/backup_status`** - 查看当前频道/帖子的备份状态
4. **`/status`** - 查看Bot运行状态和宕机恢复信息
5. **`/force_recovery`** - 强制执行宕机恢复（测试功能）

> **注意**: 推荐使用协议授权bot联动来自动启用备份，手动命令仅用于特殊情况或管理需要。

### 协议联动功能

机器人支持与协议授权bot联动，当作者签署允许备份的协议时，协议授权bot会发送POST请求到 `/webhook/license-permission` 端点。

#### Webhook请求格式

```json
{
  "event_type": "backup_permission_update",
  "timestamp": "2025-01-04T10:30:00Z",
  "guild_id": "123456789012345678",
  "channel_id": "987654321098765432", 
  "thread_id": "456789012345678901",
  "message_id": "789012345678901234",
  "author": {
    "discord_user_id": "111222333444555666",
    "username": "用户名",
    "display_name": "显示名称"
  },
  "work_info": {
    "title": "作品标题",
    "content_preview": "作品内容预览...",
    "license_type": "custom",
    "backup_allowed": true
  },
  "urls": {
    "discord_thread": "https://discord.com/channels/server/channel/thread",
    "direct_message": "https://discord.com/channels/server/channel/message"
  }
}
```

#### 备份策略

- **帖子备份**: 备份帖子标题、顶楼内容、所有楼主发布的附件
- **频道子区备份**: 备份子区名称、作者发布的所有附件

### 自动功能

- **协议联动**: 与协议授权bot联动，自动处理备份权限（主要方式）
- **消息监听**: 持续监听已启用备份的频道/帖子中的新消息
- **宕机恢复**: 机器人重启后自动扫描宕机期间的消息
- **历史扫描**: 接收到备份权限后，自动扫描历史内容
- **速率限制**: 智能处理Discord API速率限制

## 项目结构

```
PenPreserve/
├── main.py                     # 主启动文件
├── requirements.txt            # 依赖包列表
├── README.md                   # 项目说明
├── config/                     # 配置目录
│   ├── __init__.py
│   ├── bot_config.cfg         # 机器人配置文件
│   └── settings.py            # 配置管理模块
├── core/                       # 核心功能
│   ├── __init__.py
│   └── bot.py                 # Discord机器人主类
├── server/                     # 服务器相关
│   ├── __init__.py
│   └── webhook_server.py      # Webhook服务器
├── database/                   # 数据库相关
│   ├── __init__.py
│   └── models.py              # 数据库模型
├── events/                     # 事件处理
│   ├── __init__.py
│   └── message_handler.py     # 消息事件处理
├── commands/                   # 命令模块
│   ├── __init__.py
│   └── backup_commands.py     # 备份命令
├── utils/                      # 工具模块
│   ├── __init__.py
│   ├── logger.py              # 日志工具
│   ├── helpers.py             # 辅助函数
│   └── rate_limiter.py        # API速率限制器
├── scripts/                    # 脚本文件
│   ├── __init__.py
│   ├── test_webhook.py        # Webhook测试脚本
│   └── start_with_webhook.py  # 旧版启动脚本（已弃用）
├── data/                       # 数据存储
│   └── bot_data.db            # SQLite数据库文件
└── logs/                       # 日志文件
    └── bot.log               # 机器人日志
```

## 数据库结构

机器人使用SQLite数据库存储备份数据：

- **backup_configs**: 备份配置表
- **message_backups**: 消息备份表  
- **file_backups**: 文件备份表
- **authors**: 作者信息表（新增）
- **scan_tasks**: 扫描任务表（新增）
- **content_types**: 内容类型表（新增）

## 注意事项

1. **Token安全**: 请妥善保管机器人令牌，不要泄露给他人
2. **权限配置**: 确保机器人有足够的权限读取消息和发送消息
3. **API限制**: 机器人会自动处理Discord API的速率限制
4. **存储空间**: 备份文件会占用磁盘空间，请定期清理
5. **隐私保护**: 机器人只会备份作者自己的内容

## 常见问题

**Q: 机器人无法启动怎么办？**
A: 检查配置文件是否正确，Token是否有效，依赖是否正确安装。

**Q: 机器人没有响应斜杠命令怎么办？**
A: 确保机器人有足够的权限，并且已正确邀请到服务器。

**Q: 备份的文件在哪里？**
A: 备份的文件存储在SQLite数据库中，可以通过数据库查看工具访问。

**Q: 如何查看日志？**
A: 日志文件位于 `logs/bot.log`，也可以在控制台查看实时日志。

**Q: 如何测试Webhook功能？**
A: 运行 `python scripts/test_webhook.py` 来测试Webhook功能是否正常。

**Q: 备份策略如何工作？**
A: 帖子和频道子区使用不同的备份策略，详见上方"备份策略"部分。

## 支持与贡献

如果你遇到问题或有建议，欢迎提交Issue或Pull Request。

## 许可证

本项目采用MIT许可证，详情请查看LICENSE文件。 