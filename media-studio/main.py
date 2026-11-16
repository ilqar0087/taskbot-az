import asyncio
import hashlib
import logging
import math
import os
import random
import struct
import subprocess
import tempfile
import textwrap
import wave
from pathlib import Path

import imageio_ffmpeg
from PIL import Image, ImageDraw, ImageFont, ImageOps
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import Application, CallbackQueryHandler, CommandHandler, ContextTypes, MessageHandler, filters

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("ai-media-studio")
SESSIONS = {}
WORK = Path(tempfile.gettempdir()) / "ai-media-studio"
WORK.mkdir(parents=True, exist_ok=True)

MENU = InlineKeyboardMarkup([
    [InlineKeyboardButton("🖼 Poster / şəkil", callback_data="poster"),
     InlineKeyboardButton("🎬 Video / klip", callback_data="video")],
    [InlineKeyboardButton("🎵 Musiqi yarat", callback_data="music"),
     InlineKeyboardButton("📢 Reklam çarxı", callback_data="ad")],
    [InlineKeyboardButton("🎧 Audio / video formatları", callback_data="audio_tools")],
    [InlineKeyboardButton("ℹ️ Kömək", callback_data="help")],
    [InlineKeyboardButton("🧪 DEMO", callback_data="media_mode_demo"),
     InlineKeyboardButton("🚀 REAL", callback_data="media_mode_real")],
])

LABELS = {
    "poster": "Poster / şəkil",
    "video": "Video / klip",
    "music": "Musiqi",
    "ad": "Reklam çarxı",
}

FORMAT_MENU = InlineKeyboardMarkup([
    [InlineKeyboardButton("MP3", callback_data="fmt_mp3"), InlineKeyboardButton("WAV", callback_data="fmt_wav")],
    [InlineKeyboardButton("FLAC", callback_data="fmt_flac"), InlineKeyboardButton("M4A", callback_data="fmt_m4a")],
    [InlineKeyboardButton("MP4", callback_data="fmt_mp4"), InlineKeyboardButton("MOV", callback_data="fmt_mov")],
])


def font(size, bold=True):
    candidates = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf",
    ]
    for path in candidates:
        if Path(path).exists():
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()


def make_poster(chat_id, prompt, photo_path=None):
    out = WORK / f"{chat_id}-poster.jpg"
    width, height = 1080, 1350
    if photo_path and Path(photo_path).exists():
        base = Image.open(photo_path).convert("RGB")
        base = ImageOps.fit(base, (width, height), method=Image.Resampling.LANCZOS)
        overlay = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        od = ImageDraw.Draw(overlay)
        for y in range(height):
            alpha = int(20 + 190 * (y / height) ** 1.8)
            od.line((0, y, width, y), fill=(0, 0, 0, alpha))
        base = Image.alpha_composite(base.convert("RGBA"), overlay)
    else:
        base = Image.new("RGB", (width, height))
        px = base.load()
        seed = int(hashlib.sha256(prompt.encode("utf-8")).hexdigest()[:8], 16)
        rng = random.Random(seed)
        c1 = [rng.randint(25, 90), rng.randint(35, 100), rng.randint(70, 150)]
        c2 = [rng.randint(5, 30), rng.randint(5, 35), rng.randint(20, 80)]
        for y in range(height):
            t = y / height
            color = tuple(int(c1[i] * (1-t) + c2[i] * t) for i in range(3))
            for x in range(width):
                px[x, y] = color
        base = base.convert("RGBA")
        draw_bg = ImageDraw.Draw(base)
        for _ in range(8):
            x, y = rng.randint(-100, width), rng.randint(-100, height)
            r = rng.randint(60, 220)
            draw_bg.ellipse((x-r, y-r, x+r, y+r), outline=(180, 190, 255, 45), width=5)
    draw = ImageDraw.Draw(base)
    title = prompt.strip()[:160] or "Yeni layihə"
    lines = textwrap.wrap(title, width=22)[:5]
    title_font = font(74)
    y = int(height * 0.58)
    for line in lines:
        bbox = draw.textbbox((0, 0), line, font=title_font, stroke_width=2)
        tw = bbox[2] - bbox[0]
        draw.text(((width-tw)//2, y), line, font=title_font, fill="white",
                  stroke_width=3, stroke_fill=(0, 0, 0, 180))
        y += 96
    draw.rounded_rectangle((65, height-150, width-65, height-75), radius=28, fill=(12, 16, 28, 190))
    brand_font = font(30, False)
    brand = "AI MEDIA STUDIO"
    bb = draw.textbbox((0, 0), brand, font=brand_font)
    draw.text(((width-(bb[2]-bb[0]))//2, height-128), brand, font=brand_font, fill=(235, 238, 255))
    base.convert("RGB").save(out, quality=92)
    return out


def make_music(chat_id, prompt, seconds=18):
    out = WORK / f"{chat_id}-music.wav"
    sample_rate = 22050
    seed = int(hashlib.sha256(prompt.encode("utf-8")).hexdigest()[:8], 16)
    rng = random.Random(seed)
    moods = {
        "sakit": [261.63, 329.63, 392.00, 440.00],
        "enerjili": [293.66, 369.99, 440.00, 587.33],
        "kədərli": [220.00, 261.63, 329.63, 392.00],
        "romantik": [246.94, 311.13, 369.99, 493.88],
    }
    mood = next((key for key in moods if key in prompt.lower()), "sakit")
    roots = moods[mood]
    notes = [roots[i % len(roots)] * (2 if i % 7 == 6 else 1) for i in range(seconds)]
    frames = bytearray()
    total = sample_rate * seconds
    for n in range(total):
        t = n / sample_rate
        beat = int(t * 2) % len(notes)
        freq = notes[beat]
        local = (t * 2) % 1
        attack = min(1.0, local * 8)
        release = min(1.0, (1-local) * 5)
        env = min(attack, release)
        tone = math.sin(2*math.pi*freq*t) * 0.22
        overtone = math.sin(2*math.pi*freq*2*t) * 0.06
        pad = math.sin(2*math.pi*roots[(beat+2) % len(roots)]*t) * 0.08
        sample = max(-1.0, min(1.0, (tone+overtone+pad)*env))
        frames.extend(struct.pack("<h", int(sample * 32767)))
    with wave.open(str(out), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        wav.writeframes(frames)
    return out


def make_video(chat_id, poster_path, audio_path):
    out = WORK / f"{chat_id}-video.mp4"
    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    cmd = [
        ffmpeg, "-y", "-loop", "1", "-i", str(poster_path), "-i", str(audio_path),
        "-t", "18", "-vf",
        "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,format=yuv420p,fade=t=in:st=0:d=0.5,fade=t=out:st=16:d=2",
        "-r", "25", "-c:v", "libx264", "-preset", "veryfast", "-tune", "stillimage",
        "-c:a", "aac", "-b:a", "128k", "-shortest", str(out)
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    if result.returncode != 0:
        raise RuntimeError((result.stderr or "FFmpeg video export failed")[-1200:])
    return out


def convert_media(chat_id, source_path, target_format):
    """Convert an uploaded audio/video file with FFmpeg; no AI enhancement is implied."""
    source = Path(source_path)
    out = WORK / f"{chat_id}-converted.{target_format}"
    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    cmd = [ffmpeg, "-y", "-i", str(source)]
    if target_format in ("mp3", "m4a", "flac", "wav"):
        cmd += ["-vn"]
        if target_format == "mp3":
            cmd += ["-codec:a", "libmp3lame", "-q:a", "2"]
        elif target_format == "m4a":
            cmd += ["-codec:a", "aac", "-b:a", "256k"]
        elif target_format == "flac":
            cmd += ["-codec:a", "flac"]
        else:
            cmd += ["-codec:a", "pcm_s16le"]
    elif target_format in ("mp4", "mov"):
        cmd += ["-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p",
                "-c:a", "aac", "-b:a", "192k"]
        if target_format == "mp4":
            cmd += ["-movflags", "+faststart"]
    else:
        raise ValueError("Bu format dəstəklənmir.")
    cmd += [str(out)]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    if result.returncode != 0 or not out.exists() or out.stat().st_size == 0:
        detail = (result.stderr or "FFmpeg çevirmə xətası")[-900:]
        raise RuntimeError(detail)
    return out


async def media_file_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.effective_message
    chat_id = update.effective_chat.id
    media = msg.audio or msg.voice or msg.video or msg.document or msg.animation
    if not media:
        return
    file_name = getattr(media, "file_name", None) or (
        "voice.ogg" if msg.voice else "video.mp4" if msg.video else "upload.bin"
    )
    suffix = Path(file_name).suffix.lower() or (".ogg" if msg.voice else ".bin")
    if suffix not in {".mp3", ".wav", ".flac", ".m4a", ".aac", ".ogg", ".opus",
                       ".mp4", ".mov", ".mkv", ".webm", ".avi", ".mpeg", ".mpg"}:
        await msg.reply_text("Bu fayl formatını tanımadım. Audio: MP3/WAV/FLAC/M4A/OGG; video: MP4/MOV/MKV/WEBM göndər.")
        return
    if media.file_size and media.file_size > 45 * 1024 * 1024:
        await msg.reply_text("Fayl 45 MB-dan böyükdür. Zəhmət olmasa daha kiçik fayl göndər.")
        return
    tg_file = await context.bot.get_file(media.file_id)
    source = WORK / f"{chat_id}-source{suffix}"
    await tg_file.download_to_drive(custom_path=str(source))
    SESSIONS[chat_id] = {"mode": "convert", "source": str(source), "source_name": file_name,
                         "run_mode": context.user_data.get("media_mode", "demo")}
    await msg.reply_text(
        f"✅ Fayl qəbul edildi: {file_name}\nHansı formata çevirim?",
        reply_markup=FORMAT_MENU
    )


async def begin(update, context, mode):
    chat_id = update.effective_chat.id
    SESSIONS[chat_id] = {"mode": mode, "photo": None, "run_mode": context.user_data.get("media_mode", "demo")}
    await update.effective_message.reply_text(
        f"✅ {LABELS[mode]} seçildi.\n"
        "Mövzunu, reklam mətnini və istədiyin üslubu yaz. İstəsən, əvvəlcə şəkil də göndərə bilərsən."
    )


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    mode = context.user_data.get("media_mode", "demo")
    await update.message.reply_text(
        "Salam! 👋 AI Media Studio\n"
        f"Rejim: {'DEMO' if mode == 'demo' else 'REAL fayl hazırlama'}\n"
        "Poster, qısa video, instrumental fon musiqisi, reklam maketi və audio/video format çevirmə.\n"
        "Qeyd: hazırkı generator lokal şablonlardan istifadə edir; xarici peşəkar AI modeli hələ qoşulmayıb.\n\n"
        "Xidməti və rejimi seç:",
        reply_markup=MENU
    )


async def help_cmd(update, context):
    await update.message.reply_text(
        "1) Xidmət seç. 2) İdeyanı yaz. 3) İstəsən foto göndər. "
        "Bot poster, qısa video və sadə instrumental fon musiqisi hazırlayır.\n\n"
        "Qeyd: bu ilkin versiya şablon və lokal generasiya ilə işləyir; peşəkar AI şəkil/video/musiqi modelləri qoşulmayıb."
    )


async def callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if q.data == "media_mode_demo":
        context.user_data["media_mode"] = "demo"
        await q.message.reply_text("🧪 DEMO rejimi seçildi. Nümunə media faylları hazırlaya bilərsən.")
        return
    if q.data == "media_mode_real":
        context.user_data["media_mode"] = "real"
        await q.message.reply_text(
            "🚀 REAL rejimi seçildi. Bot göndərilə bilən şəkil/video/audio faylları yaradır. "
            "Qeyd: hələ xarici peşəkar AI generasiya API-si qoşulmayıb; lokal şablon generatoru işləyir."
        )
        return
    if q.data == "audio_tools":
        await q.message.reply_text("Audio və ya video faylını göndər. Sonra çıxış formatını seçəcəksən: MP3, WAV, FLAC, M4A, MP4 və ya MOV.")
        return
    if q.data.startswith("fmt_"):
        chat_id = q.message.chat_id
        session = SESSIONS.get(chat_id, {})
        if session.get("mode") != "convert":
            await q.message.reply_text("Əvvəl audio/video faylını göndər.")
            return
        fmt = q.data[4:]
        await q.message.reply_text(f"⏳ Fayl {fmt.upper()} formatına çevrilir...")
        try:
            converted = await asyncio.to_thread(convert_media, chat_id, session["source"], fmt)
            with open(converted, "rb") as stream:
                if fmt in ("mp4", "mov"):
                    await q.message.reply_video(video=stream, caption=f"Hazır video: {fmt.upper()}")
                else:
                    await q.message.reply_document(document=stream, filename=converted.name, caption=f"Hazır audio: {fmt.upper()}")
            SESSIONS.pop(chat_id, None)
            await q.message.reply_text("Başqa fayl çevirmək üçün yenə fayl göndər və ya menyudan xidmət seç.", reply_markup=MENU)
        except Exception as exc:
            log.exception("Media conversion failed")
            await q.message.reply_text(f"Çevirmə alınmadı: {str(exc)[:300]}")
        return
    if q.data == "help":
        await q.message.reply_text(
            "Xidməti seç, ideyanı yaz; foto göndərmək də olar. Hazırda şablon əsaslı poster, video və sadə instrumental audio yaradıram."
        )
        return
    if q.data in LABELS:
        await begin(update, context, q.data)


async def photo_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if chat_id not in SESSIONS:
        await update.message.reply_text("Əvvəl /start yaz və xidmət seç.", reply_markup=MENU)
        return
    photo = update.message.photo[-1]
    file = await context.bot.get_file(photo.file_id)
    path = WORK / f"{chat_id}-input.jpg"
    await file.download_to_drive(custom_path=str(path))
    SESSIONS[chat_id]["photo"] = str(path)
    await update.message.reply_text("Şəkil qəbul edildi. İndi üzərinə yazılacaq mətn və dizayn ideyasını göndər.")


async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    session = SESSIONS.get(chat_id)
    if not session:
        await update.message.reply_text("Əvvəl /start yaz və xidmət seç.", reply_markup=MENU)
        return
    prompt = (update.message.text or "").strip()
    if not prompt:
        return
    mode = session["mode"]
    photo = session.get("photo")
    await update.message.reply_text("⏳ Hazırlayıram, bir az gözlə...")
    try:
        if mode == "music":
            audio = await asyncio.to_thread(make_music, chat_id, prompt)
            with open(audio, "rb") as f:
                await update.message.reply_audio(audio=f, title="AI Media Studio — original instrumental")
        else:
            poster = await asyncio.to_thread(make_poster, chat_id, prompt, photo)
            with open(poster, "rb") as f:
                await update.message.reply_photo(photo=f, caption="Hazır poster / şəkil")
            if mode in ("video", "ad"):
                audio = await asyncio.to_thread(make_music, chat_id, prompt + " sakit")
                video = await asyncio.to_thread(make_video, chat_id, poster, audio)
                with open(video, "rb") as f:
                    await update.message.reply_video(video=f, caption="Hazır qısa video / reklam maketi")
        run_mode = session.get("run_mode", "demo")
        await update.message.reply_text(
            f"İş tamamlandı ({'DEMO' if run_mode == 'demo' else 'REAL fayl rejimi'}). Yeni iş üçün xidməti seç:",
            reply_markup=MENU
        )
        SESSIONS.pop(chat_id, None)
    except Exception as exc:
        log.exception("Media generation failed")
        await update.message.reply_text(f"Yaratma zamanı xəta: {str(exc)[:350]}. Başqa mətnlə yenidən yoxla.")


def main():
    if not TOKEN:
        raise RuntimeError("TELEGRAM_BOT_TOKEN təyin edilməyib")
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CallbackQueryHandler(callback))
    app.add_handler(MessageHandler(filters.PHOTO, photo_handler))
    app.add_handler(MessageHandler(filters.AUDIO | filters.VOICE | filters.VIDEO | filters.Document.ALL | filters.ANIMATION, media_file_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))
    log.info("AI Media Studio started")
    app.run_polling()


if __name__ == "__main__":
    main()
