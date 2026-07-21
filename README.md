# 🎵 Spotify-scrapper

A personal pipeline to pull the exact tracklist of a Spotify album via Spotify's own web API, fetch the audio from YouTube in the best available quality, and run it through an AI-assisted audio-mastering pass (EQ, vocal/instrumental balance, loudness normalization, noise reduction, optional source separation with Demucs).

## How it works

1. **`descargar.sh`** — queries Spotify's internal `api-partner.spotify.com` GraphQL endpoint for the exact tracklist of a set of album IDs, then downloads each track from YouTube with `yt-dlp` in the best available format (Opus > M4A > MP3 320K), organized into one folder per album.
2. **`instalar_dependencias.sh`** — installs the Python audio stack (`numpy`, `librosa`, `soundfile`, `scipy`, optionally `demucs`).
3. **`procesar_audio.sh` / `procesar_audio_ia.py`** — runs each downloaded track through an audio-processing chain: automatic EQ, vocal/instrumental balance, dynamic compression, LUFS loudness normalization, noise reduction, and (optionally) Demucs source separation. Originals are kept untouched; processed versions go to `Ecualizadas/`.
4. **`convertir_a_mp3.sh`** — converts the processed files to 320kbps MP3, mirroring the album folder structure into `Ecualizadas MP3/`.

## Requirements

**Download**
- [`yt-dlp`](https://github.com/yt-dlp/yt-dlp) — `pipx install yt-dlp`
- `jq` — `brew install jq`
- `ffmpeg`

**Audio processing**
- Python 3.8+
- `numpy`, `librosa`, `soundfile`, `scipy`
- [Demucs](https://github.com/facebookresearch/demucs) (optional, for source separation)

## Setup

Spotify's web API requires a short-lived session token — there's no public API key for this.

1. Copy `.env.example` to `.env`
2. Open [open.spotify.com](https://open.spotify.com) logged in, open DevTools → Network, and grab the `authorization: Bearer ...` and `client-token: ...` headers from a request to `api-partner.spotify.com`
3. Paste them into `.env` (they expire after a while — repeat this step when `descargar.sh` starts failing)
4. Edit the `ALBUMES_IDS` / `ALBUMES_NAMES` arrays in `descargar.sh` with the albums you want

## Usage

```bash
./descargar.sh                 # 1. download
./instalar_dependencias.sh     # 2. one-time setup for the audio pipeline
./procesar_audio.sh            # 3. AI-assisted mastering pass
./convertir_a_mp3.sh           # 4. convert to 320kbps MP3
```

Each step keeps the previous output intact, so you can compare original vs. processed vs. final MP3 at every stage.

## Why I built this

I wanted the exact tracklist metadata straight from Spotify (rather than guessing search terms on YouTube), and I was curious how far a fully open-source, local audio-mastering chain (librosa + scipy + Demucs, no paid SaaS) could go for cleaning up compressed YouTube rips.
