# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

PenPreserve is a Discord backup bot designed to work with protocol authorization bots. It automatically backs up messages and attachments from authorized authors in channels or threads.

## Development Commands

### Running the Bot
```bash
# Start with default config
python main.py

# Start with custom config file
python main.py --config path/to/config.cfg

# Using provided scripts
scripts/start.sh    # Linux/Mac
scripts/start.bat   # Windows
```

### Dependencies Management
```bash
# Install dependencies
pip install -r requirements.txt
```

### Testing
```bash
# Test webhook functionality
python scripts/test_webhook.py

# 可以使用 /启用备份 和 /禁用备份 命令手动管理备份功能
```

## Architecture Overview

### Core Components

**Main Entry Point** (`main.py`):
- Handles startup, signal management, and coordinates Bot + Webhook server
- Supports both standalone and integrated webhook operation based on config

**Bot Core** (`core/bot.py`):
- Discord bot implementation using discord.py
- Manages slash commands, message events, and reconnection logic
- Integrates with database, message handler, and webhook server

**Webhook Server** (`server/webhook_server.py`):
- FastAPI-based HTTP server for receiving protocol authorization updates
- Simplified payload model focusing on core control data
- Runs concurrently with Discord bot when enabled

**Database Layer** (`database/models.py`):
- SQLite-based storage using aiosqlite
- Key tables: backup_configs, message_backups, file_backups, authors, scan_tasks
- Handles backup configuration, message tracking, and recovery state

**Message Processing** (`events/message_handler.py`):
- Handles Discord message events and attachment processing
- Manages backup logic for both threads and channels
- Integrates with file manager for attachment downloads

### Configuration System

**Settings** (`config/settings.py`):
- ConfigParser-based configuration management
- Key settings: bot token, webhook settings, backup limits, logging, WebDAV storage
- Configuration file: `config/bot_config.cfg` (INI format)

**Required Config Sections**:
- `[bot]`: Discord token, prefix, activity settings
- `[webhook]`: Host, port, enabled flag
- `[database]`: SQLite filename, scan limits
- `[backup]`: File extensions, size limits
- `[logging]`: Log levels, file/console output
- `[webdav]`: WebDAV server URL, credentials, timeout settings
- `[network]`: Retry settings, timeouts

### Key Features

**Dual Operation Mode**:
- Bot + Webhook server run concurrently when webhook.enabled=true
- Webhook handles protocol authorization updates via POST to `/webhook/license-permission`
- Bot handles Discord interactions and message monitoring

**Recovery System**:
- Automatic crash recovery scanning based on last_check_time per config
- Intelligent scanning frequency (1s when active, 10s when idle)
- Duplicate message detection to prevent re-backup

**Rate Limiting** (`utils/rate_limiter.py`):
- Discord API rate limit handling with queue management
- Per-endpoint and global rate limit tracking

**File Management** (`utils/file_manager.py`):
- Attachment download and WebDAV upload
- File size and extension validation
- WebDAV client integration for remote storage

**WebDAV Storage** (`utils/webdav_client.py`):
- WebDAV client for remote file storage
- Automatic directory creation and file organization
- File structure: `guild_id/author_id/thread_id/timestamp_filename`
- Retry logic and connection testing

## Important Notes

- The bot only backs up content from authorized authors (not all channel messages)
- Webhook integration requires protocol authorization bot to send enhanced payloads with work info
- File attachments are stored in WebDAV with paths recorded in SQLite database
- Rate limiting is automatically handled for Discord API calls
- Recovery operations are performed per backup configuration, not globally
- Thread scanning is limited to 10,000 messages to prevent performance issues
- Notification messages are automatically deleted after 3 minutes

## Enhanced Features

- **Auto-deletion notifications**: Bot sends temporary notifications that self-delete
- **Historical scanning**: Automatic scanning of past messages when backup is enabled
- **WebDAV integration**: Remote file storage with organized directory structure
- **Crash recovery**: Intelligent recovery of missed content during downtime
- **User management**: Slash commands for users to view and manage their backups
- **Thread content analysis**: Extraction of thread titles and first post content

## Configuration File Location

The default configuration file is `config/bot_config.cfg`. Always verify this file exists and contains valid Discord bot token before running.