import os
import tempfile
from contextlib import asynccontextmanager
from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from db import init_db, close_db, SongMetadata
from ingest import ingest_audio_file
from matcher import match_audio_snippet

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

@app.post("/identify")
async def identify_endpoint(file: UploadFile = File(...)):
    """
    Endpoint to identify a recorded audio snippet.
    """
    # Save uploaded file temporarily. 
    # Note: librosa can read many formats out-of-the-box, but ffmpeg might be required for some (like webm).
    with tempfile.NamedTemporaryFile(delete=False) as temp_file:
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
