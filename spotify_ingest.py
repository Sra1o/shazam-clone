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
    auth_manager = SpotifyClientCredentials(
        client_id=SPOTIPY_CLIENT_ID, 
        client_secret=SPOTIPY_CLIENT_SECRET
    )
    return spotipy.Spotify(auth_manager=auth_manager)

async def process_single_track(sp, track_info):
    """Processes a single Spotify track dictionary."""
    try:
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
                return
        
        yt_query = f"{artist} - {title} official audio"
        sc_query = f"{artist} {title}" # SoundCloud search works better without "official audio"
        
        ydl_opts = {
            'format': 'bestaudio/best',
            'noplaylist': True,
            'quiet': True,
            'extractor_args': {'youtube': ['client=ANDROID_MUSIC,ANDROID,WEB_CREATOR']}, # Bypasses most YouTube bot checks
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
                    print(f"YouTube block detected. Trying YouTube Music...", flush=True)
                    try:
                        info = await asyncio.to_thread(ydl.extract_info, f"ytmsearch1:{yt_query}", download=True)
                    except Exception as e2:
                        print(f"YouTube Music blocked. Falling back to SoundCloud...", flush=True)
                        info = await asyncio.to_thread(ydl.extract_info, f"scsearch1:{sc_query}", download=True)
                
                if 'entries' in info and len(info['entries']) > 0:
                    downloaded_file = os.path.join(tmpdirname, 'download.wav')
                else:
                    print(f"Skipping '{title}': Could not find any audio on YouTube or SoundCloud.", flush=True)
                    return
                    
            metadata = SongMetadata(title=title, artist=artist, album=album, duration=duration)
            await ingest_audio_file(downloaded_file, metadata)
            print(f"Successfully ingested: {title} by {artist}", flush=True)
            
    except Exception as e:
        print(f"Error processing track {track_info.get('name', 'Unknown')}: {e}", flush=True)

async def ingest_from_spotify_url(url: str):
    """
    Given a Spotify Track or Playlist URL, fetches metadata, downloads audio via YouTube,
    and ingests it into our database. Designed to be run as a background task.
    """
    try:
        sp = get_spotify_client()
        
        if "playlist" in url:
            # It's a playlist
            results = sp.playlist_tracks(url)
            tracks = results['items']
            
            # Fetch all pages if playlist is longer than 100 songs
            while results['next']:
                results = sp.next(results)
                tracks.extend(results['items'])
                
            print(f"Starting ingestion of {len(tracks)} tracks from playlist...", flush=True)
            
            for item in tracks:
                track_info = item['track']
                if track_info:
                    await process_single_track(sp, track_info)
                    
        elif "track" in url:
            # It's a single track
            track_info = sp.track(url)
            await process_single_track(sp, track_info)
            
        else:
            print("Invalid URL format. Must be a Spotify track or playlist link.", flush=True)
            
    except Exception as e:
        print(f"Critical error in Spotify ingestion task: {e}", flush=True)
