import os
import json
import tempfile
import urllib.request
import urllib.parse
import spotipy
from spotipy.oauth2 import SpotifyClientCredentials
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
        preview_url = track_info.get('preview_url')
        
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
        
        with tempfile.TemporaryDirectory() as tmpdirname:
            
            if preview_url:
                print(f"Found Spotify preview URL! Downloading directly from Spotify servers...", flush=True)
                downloaded_file = os.path.join(tmpdirname, 'preview.mp3')
                await asyncio.to_thread(urllib.request.urlretrieve, preview_url, downloaded_file)
                
            else:
                print(f"No Spotify preview available. Bypassing DRM by fetching audio from Apple iTunes...", flush=True)
                
                # We search iTunes for the exact artist and title to get a 100% DRM-free high quality preview
                itunes_query = urllib.parse.quote(f"{artist} {title}")
                itunes_url = f"https://itunes.apple.com/search?term={itunes_query}&media=music&limit=1"
                
                def fetch_itunes_preview():
                    req = urllib.request.Request(itunes_url, headers={'User-Agent': 'Mozilla/5.0'})
                    with urllib.request.urlopen(req) as response:
                        data = json.loads(response.read().decode())
                        if data['resultCount'] > 0 and 'previewUrl' in data['results'][0]:
                            return data['results'][0]['previewUrl']
                        return None
                        
                itunes_preview_url = await asyncio.to_thread(fetch_itunes_preview)
                
                if itunes_preview_url:
                    print(f"Successfully found DRM-free audio on iTunes!", flush=True)
                    downloaded_file = os.path.join(tmpdirname, 'preview.m4a')
                    await asyncio.to_thread(urllib.request.urlretrieve, itunes_preview_url, downloaded_file)
                else:
                    raise ValueError(f"Could not find any DRM-free audio preview for '{title}'.")
                    
            metadata = SongMetadata(title=title, artist=artist, album=album, duration=duration)
            song_id, num_hashes = await ingest_audio_file(downloaded_file, metadata)
            print(f"Successfully ingested: {title} by {artist}", flush=True)
            
            return song_id, num_hashes, metadata
            
    except Exception as e:
        print(f"Critical error in Spotify ingestion task for {url}: {e}", flush=True)
        # Avoid raising the exception so we don't crash the background task worker
        return None
