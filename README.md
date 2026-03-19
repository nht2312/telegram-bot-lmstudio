# Telegram Bot - LM Studio

<details>
<summary>🇻🇳 Tiếng Việt</summary>

Telegram Bot tích hợp với LM Studio để trò chuyện với AI models local, hỗ trợ streaming, quản lý conversations, thống kê và nhiều tính năng khác.

## Tính năng

### Chat
- Gửi tin nhắn và nhận phản hồi từ AI
- Hỗ trợ **streaming** (nhận phản hồi từng phần realtime)
- Hủy streaming bằng `/cancel` hoặc nút Cancel inline
- Tự động tóm tắt context khi vượt ngưỡng token

### Quản lý Conversations
- Tạo nhiều threads/conversations
- Chuyển đổi giữa các conversations
- Đặt system prompt riêng cho từng conversation
- Xóa context hiện tại

### Model Management
- Chọn model từ LM Studio
- Xem danh sách models đang load
- Cài đặt model riêng cho mỗi conversation

### Tham số Generation
- Điều chỉnh `max_tokens`, `temperature`, `top_p`, `top_k`, `stop`, `presence_penalty`, `frequency_penalty`, `repeat_penalty`, `seed`
- Xem tham số hiện tại với `/show_params`

### API Endpoints
- `/completion` - Text completion
- `/embedding` - Tạo embeddings

### Thống Kê
- **User stats**: Conversations, messages, tokens, response time, top model
- **Global stats**: Tổng users, conversations, messages, model usage, top users
- **Thread stats**: Chi tiết từng conversation

## Cài đặt

### Yêu cầu
- Python 3.8+
- LM Studio đang chạy local
- Telegram Bot Token (từ BotFather)

### Bước 1: Cài dependencies
```bash
pip install -r requirements.txt
```

### Bước 2: Cấu hình
Sao chép `.env.example` thành `.env` và cập nhật giá trị:

```bash
cp .env.example .env
```

Các biến môi trường:

| Biến | Mô tả | Mặc định |
|------|---------|-----------|
| `BOT_TOKEN` | Telegram Bot Token | **Bắt buộc** |
| `LMSTUDIO_BASE_URL` | URL base của LM Studio API | `http://localhost:1234/v1` |
| `DEFAULT_MODEL` | Model mặc định | `qwen3.5-2b` |
| `TOKEN_THRESHOLD` | Ngưỡng token để tự động summarize | `7975` |
| `LOADING_MESSAGE_ENABLED` | Bật loading message | `true` |
| `LOADING_SUMMARIZE_ENABLED` | Bật loading khi summarize | `true` |
| `LOADING_UPDATE_INTERVAL` | Interval cập nhật loading (giây) | `5` |
| `LOADING_TIMEOUT` | Timeout cho request (giây) | `300` |
| `STREAMING_ENABLED` | Bật streaming mode | `true` |
| `STREAM_UPDATE_INTERVAL` | Interval cập nhật stream (giây) | `3.0` |
| `STREAM_MIN_CHARS` | Ký tự tối thiểu trước khi cập nhật | `20` |
| `STREAM_CANCEL_TIMEOUT` | Timeout hủy stream (giây) | `300` |

### Bước 3: Chạy bot
```bash
python main.py
```

## Danh sách Commands

| Command | Mô tả |
|---------|---------|
| `/set <param> <value>` | Đặt tham số generation |
| `/show_params` | Xem tham số hiện tại |
| `/clear_context` | Xóa context conversation |
| `/new_thread [name]` | Tạo conversation mới |
| `/list_threads` | Xem danh sách conversations |
| `/switch_thread <id>` | Chuyển conversation |
| `/set_model <model>` | Đặt model cho conversation |
| `/set_system_prompt <text>` | Đặt system prompt |
| `/show_system_prompt` | Xem system prompt |
| `/list_models` | Xem models có sẵn |
| `/completion <prompt>` | Text completion |
| `/embedding <text>` | Tạo embedding |
| `/summarize_thread [id]` | Tóm tắt conversation |
| `/stats` | Xem thống kê cá nhân |
| `/stats_global` | Xem thống kê toàn cục |
| `/stats_thread` | Xem thống kê conversation |
| `/cancel` | Hủy streaming |

## Cấu trúc dự án

```
telegram-bot-lmstudio/
├── main.py                    # Entry point
├── requirements.txt           # Dependencies
├── .env.example               # Template cấu hình
├── src/
│   ├── config/
│   │   ├── settings.py        # Cấu hình & biến môi trường
│   │   └── logging_config.py  # Logging setup
│   ├── api/
│   │   └── lm_studio.py       # LM Studio API client
│   ├── database/
│   │   └── models.py          # SQLite database operations
│   └── handlers/
│       ├── commands.py         # Command handlers
│       └── messages.py         # Message & streaming handlers
└── conversations.db           # SQLite database (auto-generated)
```

## Database Schema

| Bảng | Mô tả |
|------|--------|
| `users` | Thông tin người dùng Telegram |
| `user_settings` | Settings cá nhân (default model, active conversation) |
| `user_conversations` | Các conversations của user |
| `messages` | Tin nhắn trong conversations |
| `conversation_summary` | Tóm tắt conversations |
| `usage_log` | Log sử dụng API (tokens, response time) |

## Dependencies

- `python-dotenv` - Đọc biến môi trường
- `python_telegram_bot==21.9` - Telegram Bot API
- `requests` - HTTP client cho LM Studio API
- `markdown2` - Convert Markdown (optional)

## Lưu ý

- LM Studio phải đang chạy trước khi start bot
- Database SQLite tự động tạo khi chạy lần đầu
- Streaming mode mặc định bật, tắt bằng `STREAMING_ENABLED=false`
- Token threshold điều chỉnh tần suất auto-summarize

</details>

<details open>
<summary>🇬🇧 English</summary>

Telegram Bot integrated with LM Studio for chatting with local AI models, supporting streaming, conversation management, statistics, and more.

## Features

### Chat
- Send messages and receive AI responses
- **Streaming** support (real-time partial responses)
- Cancel streaming via `/cancel` or inline Cancel button
- Auto-summarize context when token threshold is exceeded

### Conversation Management
- Create multiple threads/conversations
- Switch between conversations
- Set custom system prompt per conversation
- Clear current context

### Model Management
- Select model from LM Studio
- View loaded models list
- Set model per conversation

### Generation Parameters
- Adjust `max_tokens`, `temperature`, `top_p`, `top_k`, `stop`, `presence_penalty`, `frequency_penalty`, `repeat_penalty`, `seed`
- View current parameters with `/show_params`

### API Endpoints
- `/completion` - Text completion
- `/embedding` - Generate embeddings

### Statistics
- **User stats**: Conversations, messages, tokens, response time, top model
- **Global stats**: Total users, conversations, messages, model usage, top users
- **Thread stats**: Details per conversation

## Setup

### Requirements
- Python 3.8+
- LM Studio running locally
- Telegram Bot Token (from BotFather)

### Step 1: Install dependencies
```bash
pip install -r requirements.txt
```

### Step 2: Configuration
Copy `.env.example` to `.env` and update values:

```bash
cp .env.example .env
```

Environment variables:

| Variable | Description | Default |
|----------|-------------|---------|
| `BOT_TOKEN` | Telegram Bot Token | **Required** |
| `LMSTUDIO_BASE_URL` | LM Studio API base URL | `http://localhost:1234/v1` |
| `DEFAULT_MODEL` | Default model | `qwen3.5-2b` |
| `TOKEN_THRESHOLD` | Token threshold for auto-summarize | `7975` |
| `LOADING_MESSAGE_ENABLED` | Enable loading message | `true` |
| `LOADING_SUMMARIZE_ENABLED` | Enable loading during summarize | `true` |
| `LOADING_UPDATE_INTERVAL` | Loading update interval (seconds) | `5` |
| `LOADING_TIMEOUT` | Request timeout (seconds) | `300` |
| `STREAMING_ENABLED` | Enable streaming mode | `true` |
| `STREAM_UPDATE_INTERVAL` | Stream update interval (seconds) | `3.0` |
| `STREAM_MIN_CHARS` | Minimum chars before update | `20` |
| `STREAM_CANCEL_TIMEOUT` | Stream cancel timeout (seconds) | `300` |

### Step 3: Run the bot
```bash
python main.py
```

## Commands List

| Command | Description |
|---------|-------------|
| `/set <param> <value>` | Set generation parameter |
| `/show_params` | View current parameters |
| `/clear_context` | Clear conversation context |
| `/new_thread [name]` | Create new conversation |
| `/list_threads` | List conversations |
| `/switch_thread <id>` | Switch conversation |
| `/set_model <model>` | Set model for conversation |
| `/set_system_prompt <text>` | Set system prompt |
| `/show_system_prompt` | View system prompt |
| `/list_models` | List available models |
| `/completion <prompt>` | Text completion |
| `/embedding <text>` | Generate embedding |
| `/summarize_thread [id]` | Summarize conversation |
| `/stats` | View personal stats |
| `/stats_global` | View global stats |
| `/stats_thread` | View conversation stats |
| `/cancel` | Cancel streaming |

## Project Structure

```
telegram-bot-lmstudio/
├── main.py                    # Entry point
├── requirements.txt           # Dependencies
├── .env.example               # Configuration template
├── src/
│   ├── config/
│   │   ├── settings.py        # Configuration & environment variables
│   │   └── logging_config.py  # Logging setup
│   ├── api/
│   │   └── lm_studio.py       # LM Studio API client
│   ├── database/
│   │   └── models.py          # SQLite database operations
│   └── handlers/
│       ├── commands.py         # Command handlers
│       └── messages.py         # Message & streaming handlers
└── conversations.db           # SQLite database (auto-generated)
```

## Database Schema

| Table | Description |
|-------|-------------|
| `users` | Telegram user information |
| `user_settings` | Personal settings (default model, active conversation) |
| `user_conversations` | User conversations |
| `messages` | Messages in conversations |
| `conversation_summary` | Conversation summaries |
| `usage_log` | API usage log (tokens, response time) |

## Dependencies

- `python-dotenv` - Environment variable loader
- `python_telegram_bot==21.9` - Telegram Bot API
- `requests` - HTTP client for LM Studio API
- `markdown2` - Markdown conversion (optional)

## Notes

- LM Studio must be running before starting the bot
- SQLite database is auto-created on first run
- Streaming mode is enabled by default, disable with `STREAMING_ENABLED=false`
- Token threshold controls auto-summarize frequency

</details>
