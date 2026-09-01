import os
import tempfile
from contextlib import asynccontextmanager
from fastapi import FastAPI, UploadFile, File, Form, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from db import init_db, close_db, SongMetadata
from ingest import ingest_audio_file
from matcher import match_audio_snippet
from spotify_ingest import ingest_from_spotify_url
from pydantic import BaseModel

class SpotifyRequest(BaseModel):
    url: str

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    await init_db()
    yield
    # Shutdown
    await close_db()

app = FastAPI(title="Shazam Clone API", lifespan=lifespan)

# Add CORS middleware for the React frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # In production, replace with specific frontend URL
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
async def root():
    return {"status": "ok", "message": "Shazam Clone API is running"}

@app.post("/ingest")
async def ingest_endpoint(
    file: UploadFile = File(...),
    title: str = Form(...),
    artist: str = Form(...),
    album: str = Form(None),
    duration: float = Form(...)
):
    """
    Endpoint to ingest a new song into the database.
    """
    # Save uploaded file temporarily
    with tempfile.NamedTemporaryFile(delete=False) as temp_file:
        content = await file.read()
        temp_file.write(content)
        temp_path = temp_file.name
        
    metadata = SongMetadata(title=title, artist=artist, album=album, duration=duration)
    
    try:
        song_id, num_hashes = await ingest_audio_file(temp_path, metadata)
    except Exception as e:
        os.remove(temp_path)
        raise HTTPException(status_code=500, detail=str(e))
        
    os.remove(temp_path)
    
    return {
        "status": "success",
        "song_id": song_id,
        "hashes_generated": num_hashes,
        "message": f"Successfully ingested '{title}' by {artist}"
    }

@app.post("/ingest/spotify", status_code=202)
async def ingest_spotify_endpoint(request: SpotifyRequest, background_tasks: BackgroundTasks):
    """
    Endpoint to automatically ingest a song or playlist using a Spotify URL.
    Downloads the audio from YouTube in the background.
    """
    if "spotify.com" not in request.url:
        raise HTTPException(status_code=400, detail="Must provide a valid Spotify URL")
        
    # Kick off the ingestion process in the background
    background_tasks.add_task(ingest_from_spotify_url, request.url)
        
    return {
        "status": "accepted",
        "message": "Spotify ingestion started in the background. You can safely close this window or add more links!"
    }

@app.post("/identify")
async def identify_endpoint(file: UploadFile = File(...)):
    """
    Endpoint to identify a recorded audio snippet.
    """
    # Save uploaded file temporarily. 
    # Note: librosa can read many formats out-of-the-box, but ffmpeg might be required for some (like webm).
    # Providing the .webm suffix helps ffmpeg/soundfile identify the format correctly.
    with tempfile.NamedTemporaryFile(delete=False, suffix=".webm") as temp_file:
        content = await file.read()
        temp_file.write(content)
        temp_path = temp_file.name
        
    try:
        match_result = await match_audio_snippet(temp_path)
    except Exception as e:
        os.remove(temp_path)
        raise HTTPException(status_code=500, detail=str(e))
        
    os.remove(temp_path)
    
    if match_result:
        return {
            "status": "success",
            "match": match_result
        }
    else:
        return {
            "status": "not_found",
            "message": "No matching song found."
        }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
