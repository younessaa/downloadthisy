# DownloadThisYouTube

Download YouTube videos (MP4) and audio (MP3 / M4A). Built with Flask, yt-dlp and Bootstrap 5.

## The URL trick

Add `downloadthis` before `youtube.com`:

```
https://www.youtube.com/watch?v=gIu5iVuxehE
https://www.downloadthisyoutube.com/watch?v=gIu5iVuxehE
```

`/shorts/<id>`, `/embed/<id>` and `/live/<id>` work too. You can also paste any YouTube link (including `youtu.be/...`) on the home page.

## Run locally

```powershell
python -m venv .venv
.\.venv\Scripts\pip install -r requirements.txt
.\.venv\Scripts\python app.py
```

Open http://127.0.0.1:5000/watch?v=gIu5iVuxehE

`imageio-ffmpeg` bundles an ffmpeg binary. The app uses it to merge HD video with audio (720p and above) and to convert to MP3.

## Run locally with Docker (always on)

```powershell
docker compose up -d --build
```

The container restarts automatically whenever Docker Desktop starts (`restart: unless-stopped`).
To stop it: `docker compose down`. After changing the code: `docker compose up -d --build`.

To use the domain on this computer, open Notepad **as Administrator**, edit
`C:\Windows\System32\drivers\etc\hosts` and add:

```
127.0.0.1 downloadthisyoutube.com
127.0.0.1 www.downloadthisyoutube.com
```

Then open http://www.downloadthisyoutube.com/watch?v=gIu5iVuxehE (use `http://`, not `https://`).

## Production

```bash
pip install gunicorn
gunicorn -w 4 --timeout 600 -b 0.0.0.0:8000 app:app
```

Put Nginx in front, point the `downloadthisyoutube.com` and `www.downloadthisyoutube.com` DNS records at the server, and add HTTPS (for example with Let's Encrypt).
Update yt-dlp regularly (`pip install -U yt-dlp`), because YouTube changes often.

## Routes

| Route | Purpose |
|---|---|
| `/` | Home page with the link form |
| `/go?url=...` | Accepts any YouTube link and redirects to `/watch?v=ID` |
| `/watch?v=ID` | Video info and download options |
| `/download?v=ID&f=KEY` | Builds the file and sends it. `KEY` is `v1080`, `v720`, …, `mp3` or `m4a` |

Only download content you own or have permission to download.
