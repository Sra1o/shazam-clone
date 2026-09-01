import os
import tempfile
import spotipy
from spotipy.oauth2 import SpotifyClientCredentials
import yt_dlp
from db import SongMetadata, get_db_pool
from ingest import ingest_audio_file
import asyncio

# Set these in the environment or Render Dashboard
SPOTIPY_CLIENT_ID = os.environ.get("SPOTIPY_CLIENT_ID", "")
SPOTIPY_CLIENT_SECRET = os.environ.get("SPOTIPY_CLIENT_SECRET", "")

def get_spotify_client():
    if not SPOTIPY_CLIENT_ID or not SPOTIPY_CLIENT_SECRET:
        raise ValueError("Spotify API credentials (SPOTIPY_CLIENT_ID, SPOTIPY_CLIENT_SECRET) are not set in the environment.")
    
    # Simple Client Credentials since we are only doing single tracks (no playlists, no 401 errors!)
    auth_manager = SpotifyClientCredentials(
        client_id=SPOTIPY_CLIENT_ID, 
        client_secret=SPOTIPY_CLIENT_SECRET
    )
    return spotipy.Spotify(auth_manager=auth_manager)

async def ingest_from_spotify_url(url: str):
    """
    Given a Spotify Track URL, fetches metadata, downloads audio via YouTube/SoundCloud,
    and ingests it into our database.
    """
    if "playlist" in url:
        raise ValueError("Playlists are not supported. Please provide a single Spotify Track URL.")
        
    try:
        sp = get_spotify_client()
        track_info = sp.track(url)
        
        title = track_info['name']
        artist = track_info['artists'][0]['name']
        album = track_info['album']['name']
        duration = track_info['duration_ms'] / 1000.0
        
        # 1. Duplicate Safeguard
        pool = get_db_pool()
        async with pool.acquire() as conn:
            existing = await conn.fetchrow(
                "SELECT id FROM songs WHERE title = $1 AND artist = $2",
                title, artist
            )
            if existing:
                print(f"Skipping '{title}' by {artist}: Already exists in database.", flush=True)
                return existing['id'], 0, SongMetadata(title=title, artist=artist, album=album, duration=duration)
        
        # We search exactly what we need
        yt_query = f"{artist} - {title} audio"
        sc_query = f"{artist} {title}"
        
        ydl_opts = {
            'format': 'bestaudio/best',
            'noplaylist': True,
            'quiet': True,
            # 'ANDROID' without 'ANDROID_MUSIC' bypasses bot checks without triggering Music DRM!
            'extractor_args': {'youtube': ['client=ANDROID,IOS,WEB']},
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'wav',
            }],
        }
        
        with tempfile.TemporaryDirectory() as tmpdirname:
            ydl_opts['outtmpl'] = os.path.join(tmpdirname, 'download.%(ext)s')
            
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                try:
                    info = await asyncio.to_thread(ydl.extract_info, f"ytsearch1:{yt_query}", download=True)
                except Exception as e:
                    print(f"YouTube threw an error (Bot/DRM). Falling back to SoundCloud...", flush=True)
                    info = await asyncio.to_thread(ydl.extract_info, f"scsearch1:{sc_query}", download=True)
                
                if 'entries' in info and len(info['entries']) > 0:
                    downloaded_file = os.path.join(tmpdirname, 'download.wav')
                else:
                    raise ValueError(f"Could not find any audio on YouTube or SoundCloud for '{title}'.")
                    
            metadata = SongMetadata(title=title, artist=artist, album=album, duration=duration)
            song_id, num_hashes = await ingest_audio_file(downloaded_file, metadata)
            print(f"Successfully ingested: {title} by {artist}", flush=True)
            
            return song_id, num_hashes, metadata
            
    except Exception as e:
        print(f"Critical error in Spotify ingestion task: {e}", flush=True)
        raise e
