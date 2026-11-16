# AI Media Studio

Telegram bot that creates poster images, short vertical MP4 clips, simple original instrumental WAV tracks, and combined advertising mockups using local templates and FFmpeg.

## Required Railway variable
- `TELEGRAM_BOT_TOKEN`

## Commands
- `/start` — menu
- `/help` — instructions

Choose Poster, Video, Music, or Ad, then send a prompt. You may send a photo first to use it as the visual background.

## Current scope
- Poster generation: Pillow-based layout, gradients, text, and optional user-provided photo.
- Video generation: vertical 18-second MP4 with poster frame and original synthesized instrumental background.
- Music: simple procedurally synthesized instrumental WAV, not vocals or studio-quality AI composition.
- Ad: poster plus short video mockup.

This version uses local templates and does not require a separate AI-provider API key. It is not yet connected to advanced generative image/video/music models. No media is published to social networks automatically; the user reviews and posts it.
