import uuid
import json
from db import get_db, get_redis, SongMetadata
from fingerprint import fingerprint_audio

async def ingest_audio_file(file_path: str, metadata: SongMetadata):
    """
    Fingerprints an audio file, stores metadata in MongoDB, 
    and pushes hashes to Redis.
    """
    # 1. Fingerprint the audio
    # Returns list of (hash_value, offset_in_seconds)
    hashes = fingerprint_audio(file_path)
    
    if not hashes:
        raise ValueError("No hashes generated for audio file.")
        
    # 2. Store metadata in MongoDB
    db = get_db()
    if db is None:
        raise RuntimeError("Database connection not initialized")
        
    song_id = str(uuid.uuid4())
    
    song_doc = metadata.model_dump()
    song_doc["_id"] = song_id
    
    await db.songs.insert_one(song_doc)
    
    # 3. Push hashes to Redis efficiently
    redis_client = get_redis()
    if redis_client is None:
        raise RuntimeError("Redis connection not initialized")
        
    # We use a pipeline to batch the redis commands
    pipeline = redis_client.pipeline()
    
    # We use Redis Lists. For each hash, we push the match object.
    # We serialize it compactly to save memory.
    for h, offset in hashes:
        match_obj = json.dumps({"s": song_id, "o": round(offset, 3)})
        pipeline.rpush(h, match_obj)
        
    await pipeline.execute()
    
    return song_id, len(hashes)
