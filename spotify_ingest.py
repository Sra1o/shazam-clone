import os
import tempfile
import spotipy
from spotipy.oauth2 import SpotifyClientCredentials
import yt_dlp
from db import SongMetadata
from ingest import ingest_audio_file

# Set these in the environment or Render Dashboard
SPOTIPY_CLIENT_ID = os.environ.get("SPOTIPY_CLIENT_ID", "")
SPOTIPY_CLIENT_SECRET = os.environ.get("SPOTIPY_CLIENT_SECRET", "")

async def ingest_from_spotify(url: str):
    """
    Given a Spotify Track URL, fetches metadata, downloads audio via YouTube,
    and ingests it into our database.
    """
    if not SPOTIPY_CLIENT_ID or not SPOTIPY_CLIENT_SECRET:
        raise ValueError("Spotify API credentials (SPOTIPY_CLIENT_ID, SPOTIPY_CLIENT_SECRET) are not set in the environment.")
        
    # 1. Fetch metadata from Spotify
    auth_manager = SpotifyClientCredentials(
        client_id=SPOTIPY_CLIENT_ID, 
        client_secret=SPOTIPY_CLIENT_SECRET
    )
    sp = spotipy.Spotify(auth_manager=auth_manager)
    
    try:
        track_info = sp.track(url)
    except Exception as e:
        raise ValueError(f"Failed to fetch Spotify track: {str(e)}")
        
    title = track_info['name']
    artist = track_info['artists'][0]['name']
    album = track_info['album']['name']
    duration = track_info['duration_ms'] / 1000.0
    
    # We create a specific search query to find the cleanest audio on YouTube
    search_query = f"{artist} - {title} official audio"
    
    # 2. Download audio using yt-dlp
    ydl_opts = {
        'format': 'bestaudio/best',
        'noplaylist': True,
        'quiet': True,
        # yt-dlp will automatically extract audio if we have ffmpeg (which we installed in Docker)
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'wav',
        }],
    }
    
    song_id = None
    num_hashes = 0
    
    with tempfile.TemporaryDirectory() as tmpdirname:
        # Save output inside the temp directory
        ydl_opts['outtmpl'] = os.path.join(tmpdirname, 'download.%(ext)s')
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            # Tell yt-dlp to search YouTube and grab the first result
            info = ydl.extract_info(f"ytsearch1:{search_query}", download=True)
            
            if 'entries' in info and len(info['entries']) > 0:
                # Get the actual filename that was downloaded and post-processed
                # Using standard outtmpl with .wav because of the postprocessor
                downloaded_file = os.path.join(tmpdirname, 'download.wav')
            else:
                raise ValueError("Could not find a matching audio track on YouTube.")
                
        # 3. Ingest into database using our existing async Postgres engine
        metadata = SongMetadata(title=title, artist=artist, album=album, duration=duration)
        song_id, num_hashes = await ingest_audio_file(downloaded_file, metadata)
        
    return song_id, num_hashes, metadata
