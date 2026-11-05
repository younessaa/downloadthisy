"""DownloadThisYouTube - mirror YouTube URLs and download videos with yt-dlp.

https://www.youtube.com/watch?v=ID  ->  https://www.downloadthisyoutube.com/watch?v=ID
"""
import os
import re
import shutil
import tempfile
import time
from urllib.parse import urlparse, parse_qs

from flask import Flask, render_template, request, redirect, url_for, send_file, abort
import yt_dlp

try:
    import imageio_ffmpeg
    FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()
except Exception:
    FFMPEG = shutil.which("ffmpeg")

app = Flask(__name__)

VIDEO_ID_RE = re.compile(r"^[A-Za-z0-9_-]{11}$")
TMP_ROOT = os.path.join(tempfile.gettempdir(), "downloadthisy")
TMP_MAX_AGE = 60 * 60  # seconds
os.makedirs(TMP_ROOT, exist_ok=True)

INFO_CACHE = {}
INFO_TTL = 10 * 60  # seconds


# ---------------------------------------------------------------- helpers

def extract_video_id(text):
    """Return the 11-char video id from any YouTube link (or a bare id)."""
    text = (text or "").strip()
    if VIDEO_ID_RE.match(text):
        return text
    if not re.match(r"^https?://", text):
        text = "https://" + text
    try:
        u = urlparse(text)
    except ValueError:
        return None
    host = (u.hostname or "").lower().removeprefix("www.").removeprefix("m.")
    path = u.path.strip("/").split("/")

    candidate = None
    if host == "youtu.be":
        candidate = path[0] if path else None
    elif host.endswith("youtube.com") or host.endswith("youtube-nocookie.com") or host.startswith("downloadthis"):
        if path and path[0] == "watch":
            candidate = parse_qs(u.query).get("v", [None])[0]
        elif len(path) >= 2 and path[0] in ("shorts", "embed", "live", "v"):
            candidate = path[1]
    if candidate and VIDEO_ID_RE.match(candidate):
        return candidate
    return None


def human_size(num):
    if not num:
        return None
    for unit in ("B", "KB", "MB", "GB"):
        if num < 1024:
            return f"{num:.1f} {unit}"
        num /= 1024
    return f"{num:.1f} TB"


def human_duration(seconds):
    if not seconds:
        return "Live"
    seconds = int(seconds)
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def get_info(video_id):
    cached = INFO_CACHE.get(video_id)
    if cached and time.time() - cached[0] < INFO_TTL:
        return cached[1]
    opts = {"quiet": True, "no_warnings": True, "skip_download": True, "noplaylist": True}
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(f"https://www.youtube.com/watch?v={video_id}", download=False)
    INFO_CACHE[video_id] = (time.time(), info)
    return info


def build_options(info):
    """Turn yt-dlp formats into the download choices shown on the page."""
    formats = info.get("formats") or []
    duration = info.get("duration") or 0

    def est_size(f):
        return f.get("filesize") or f.get("filesize_approx") or (
            f.get("tbr") and duration and f["tbr"] * 1000 / 8 * duration)

    best_audio = max(
        (f for f in formats if f.get("vcodec") == "none" and f.get("acodec") not in (None, "none")),
        key=lambda f: f.get("abr") or 0, default=None)

    video = {}
    for f in formats:
        h = f.get("height")
        if not h or f.get("vcodec") in (None, "none"):
            continue
        has_audio = f.get("acodec") not in (None, "none")
        if not has_audio and not FFMPEG:
            continue  # cannot merge video-only streams without ffmpeg
        size = est_size(f) or 0
        if not has_audio and best_audio:
            size += est_size(best_audio) or 0
        if h not in video or (size and size < (video[h]["size"] or 1e18)):
            video[h] = {"height": h, "fps": f.get("fps"), "size": size}

    video_opts = [
        {"key": f"v{h}", "label": f"{h}p", "badge": badge_for(h), "fps": v["fps"],
         "size": human_size(v["size"]), "ext": "mp4"}
        for h, v in sorted(video.items(), reverse=True) if h >= 144
    ]
    audio_opts = [{"key": "m4a", "label": "Audio M4A", "size": human_size(best_audio and est_size(best_audio)), "ext": "m4a"}]
    if FFMPEG:
        audio_opts.insert(0, {"key": "mp3", "label": "Audio MP3", "size": None, "ext": "mp3"})
    return video_opts, audio_opts


def badge_for(height):
    if height >= 2160:
        return "4K"
    if height >= 1440:
        return "2K"
    if height >= 720:
        return "HD"
    return None


def ydl_opts_for(key, outdir):
    opts = {
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,
        "noplaylist": True,
        "outtmpl": os.path.join(outdir, "%(title).150B [%(id)s].%(ext)s"),
        "restrictfilenames": False,
        "windowsfilenames": True,
    }
    if FFMPEG:
        opts["ffmpeg_location"] = FFMPEG

    if key == "m4a":
        opts["format"] = "ba[ext=m4a]/ba"
    elif key == "mp3":
        opts["format"] = "ba/b"
        opts["postprocessors"] = [{"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": "192"}]
    else:
        m = re.fullmatch(r"v(\d{2,4})", key)
        if not m:
            return None
        h = int(m.group(1))
        if FFMPEG:
            opts["format"] = (f"bv*[height<={h}][ext=mp4]+ba[ext=m4a]/"
                              f"bv*[height<={h}]+ba/b[height<={h}]")
            opts["merge_output_format"] = "mp4"
        else:
            opts["format"] = f"b[height<={h}][ext=mp4]/b[height<={h}]"
    return opts


def cleanup_old_tmp():
    now = time.time()
    for name in os.listdir(TMP_ROOT):
        path = os.path.join(TMP_ROOT, name)
        try:
            if now - os.path.getmtime(path) > TMP_MAX_AGE:
                shutil.rmtree(path, ignore_errors=True)
        except OSError:
            pass


# ---------------------------------------------------------------- routes

@app.route("/")
def index():
    return render_template("index.html", error=request.args.get("error"))


@app.route("/go")
def go():
    """Handle the form: accept any YouTube link and redirect to /watch?v=ID."""
    video_id = extract_video_id(request.args.get("url", ""))
    if not video_id:
        return redirect(url_for("index", error="That doesn't look like a valid YouTube link."))
    return redirect(url_for("watch", v=video_id))


@app.route("/watch")
def watch():
    video_id = request.args.get("v", "")
    if not VIDEO_ID_RE.match(video_id):
        return redirect(url_for("index", error="Missing or invalid video id."))
    try:
        info = get_info(video_id)
    except yt_dlp.utils.DownloadError as e:
        msg = re.sub(r"\x1b\[[0-9;]*m", "", str(e)).replace("ERROR: ", "")
        return render_template("index.html", error=f"Could not load this video: {msg}"), 404

    video_opts, audio_opts = build_options(info)
    return render_template(
        "watch.html",
        video_id=video_id,
        title=info.get("title"),
        channel=info.get("uploader") or info.get("channel"),
        thumbnail=info.get("thumbnail") or f"https://i.ytimg.com/vi/{video_id}/hqdefault.jpg",
        duration=human_duration(info.get("duration")),
        views=info.get("view_count"),
        video_opts=video_opts,
        audio_opts=audio_opts,
        has_ffmpeg=bool(FFMPEG),
    )


# youtube.com/shorts/ID, /embed/ID, /live/ID  ->  /watch?v=ID
@app.route("/shorts/<video_id>")
@app.route("/embed/<video_id>")
@app.route("/live/<video_id>")
def alt_paths(video_id):
    return redirect(url_for("watch", v=video_id))


@app.route("/download")
def download():
    video_id = request.args.get("v", "")
    key = request.args.get("f", "")
    token = request.args.get("token", "")
    if not VIDEO_ID_RE.match(video_id):
        abort(400)
    cleanup_old_tmp()
    outdir = tempfile.mkdtemp(dir=TMP_ROOT)
    opts = ydl_opts_for(key, outdir)
    if opts is None:
        abort(400)
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            ydl.download([f"https://www.youtube.com/watch?v={video_id}"])
    except yt_dlp.utils.DownloadError:
        shutil.rmtree(outdir, ignore_errors=True)
        return redirect(url_for("watch", v=video_id, error="Download failed, please try another format."))

    files = [f for f in os.listdir(outdir) if not f.endswith((".part", ".ytdl"))]
    if not files:
        shutil.rmtree(outdir, ignore_errors=True)
        abort(500)
    path = os.path.join(outdir, max(files, key=lambda f: os.path.getsize(os.path.join(outdir, f))))

    response = send_file(path, as_attachment=True, download_name=os.path.basename(path))
    if re.fullmatch(r"[A-Za-z0-9]{1,32}", token):
        # lets the page know the file is ready so it can hide the spinner
        response.set_cookie("dl_token", token, max_age=60)
    response.call_on_close(lambda: shutil.rmtree(outdir, ignore_errors=True))
    return response


@app.template_filter("thousands")
def thousands(n):
    return f"{n:,}" if isinstance(n, int) else n


if __name__ == "__main__":
    app.run(debug=True, port=int(os.environ.get("PORT", 5000)))
