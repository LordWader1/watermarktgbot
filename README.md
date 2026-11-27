# 🎬 Telegram Video Watermark Bot

A high-performance, asynchronous Telegram bot built with **Pyrogram** and **FFmpeg** to seamlessly add custom watermarks to videos. Fully optimized for Heroku deployment with robust job queuing, database support, and automated disk cleanup.

[![Deploy to Heroku](https://www.herokucdn.com/deploy/button.svg)](https://heroku.com/deploy?template=https://github.com/LordWader1/watermarktgbot)

## ✨ Features

* **🗑️ Auto-Delete System (New!):** Keeps your bot and server clean. Automatically deletes the user's original video and the bot's final output message after a configurable timer. 
* **Custom Watermarking:** Burn text or image watermarks directly into videos with high quality.
* **Smart Job Queue:** Bounded async queue with per-user limits to prevent server overload and crashes.
* **Live Progress Tracking:** Dynamic, editing status messages showing real-time download, processing, and upload ETA.
* **Database Integration:** Built-in support for MongoDB (Motor) for production, or SQLite for local testing.
* **Heroku Optimized:** Immediate local file cleanup after processing to prevent `R14 (Out of Memory)` and `Disk Full` errors. Gracefully handles dyno restarts mid-job.

## ⚙️ Environment Variables

Configure these settings in your `.env` file or Heroku Config Vars. 

### Required Variables
| Variable | Description |
|---|---|
| `API_ID` | Your Telegram API ID from [my.telegram.org](https://my.telegram.org). |
| `API_HASH` | Your Telegram API Hash from [my.telegram.org](https://my.telegram.org). |
| `BOT_TOKEN` | Your Bot Token from [@BotFather](https://t.me/BotFather). |
| `OWNER_ID` | Your Telegram User ID for admin privileges. |

### Auto-Delete & Advanced Configuration (Optional)
| Variable | Default | Description |
|---|---|---|
| `AUTO_DELETE_TIME` | `600` | **Controls the Auto-Delete feature.** Set the time in seconds to wait before deleting processed videos (e.g., `600` = 10 mins, `1800` = 30 mins). Set to `0` to completely disable auto-delete. |
| `MONGO_URI` | `""` | MongoDB connection string. If left blank, the bot uses SQLite. |
| `MAX_CONCURRENT_JOBS` | `1` | Number of videos the bot will process simultaneously. |
| `MAX_FILE_SIZE` | `2147483648` | Maximum allowed file size in bytes (Default: 2GB). |
| `LOG_CHANNEL` | `0` | Chat ID of a channel/group where the bot logs completed jobs. |

## 🚀 Local Installation

1. **Clone the repository:**
   ```bash
   git clone [https://github.com/LordWader1/watermarktgbot.git](https://github.com/LordWader1/watermarktgbot.git)
   cd watermarktgbot
