import uuid
import asyncio
from db import get_db_pool, SongMetadata
from fingerprint import fingerprint_audio

async def ingest_audio_file(file_path: str, metadata: SongMetadata):
    """
    Fingerprints an audio file and stores metadata and hashes in PostgreSQL.
    Uses ON CONFLICT to gracefully handle race conditions where two concurrent
    requests try to insert the same song.
    """
    # 1. Fingerprint the audio (CPU heavy, run in thread pool)
    hashes = await asyncio.to_thread(fingerprint_audio, file_path)
    
    if not hashes:
        raise ValueError("No hashes generated for audio file.")
        
    pool = get_db_pool()
    song_id = str(uuid.uuid4())
    
    async with pool.acquire() as conn:
        async with conn.transaction():
            # 2. Insert metadata — ON CONFLICT skips if (title, artist) already exists
            row = await conn.fetchrow(
                """
                INSERT INTO songs (id, title, artist, album, duration, cover_art_url)
                VALUES ($1::uuid, $2, $3, $4, $5, $6)
                ON CONFLICT (title, artist) DO NOTHING
                RETURNING id
                """,
                song_id, metadata.title, metadata.artist, metadata.album, metadata.duration, metadata.cover_art_url
            )
            
            if row is None:
                # Song was already inserted by a concurrent request — look up its id
                existing = await conn.fetchrow(
                    "SELECT id FROM songs WHERE title = $1 AND artist = $2",
                    metadata.title, metadata.artist
                )
                print(f"Song '{metadata.title}' by {metadata.artist} already exists (race condition avoided).", flush=True)
                return str(existing['id']), 0
            
            # 3. Bulk insert hashes (only for newly inserted songs)
            hash_records = [(h, song_id, round(offset, 3)) for h, offset in hashes]
            
            await conn.executemany(
                """
                INSERT INTO hashes (hash_value, song_id, time_offset)
                VALUES ($1, $2::uuid, $3)
                """,
                hash_records
            )
            
    return song_id, len(hashes)
