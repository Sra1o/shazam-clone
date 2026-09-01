import uuid
from db import get_db_pool, SongMetadata
from fingerprint import fingerprint_audio

async def ingest_audio_file(file_path: str, metadata: SongMetadata):
    """
    Fingerprints an audio file and stores metadata and hashes in PostgreSQL.
    """
    # 1. Fingerprint the audio
    hashes = fingerprint_audio(file_path)
    
    if not hashes:
        raise ValueError("No hashes generated for audio file.")
        
    pool = get_db_pool()
    # UUIDs in asyncpg can be provided as strings if casted in the query, 
    # but it's safer to let asyncpg parse the UUID natively or just cast it in SQL.
    song_id = str(uuid.uuid4())
    
    async with pool.acquire() as conn:
        async with conn.transaction():
            # 2. Insert metadata
            await conn.execute(
                """
                INSERT INTO songs (id, title, artist, album, duration)
                VALUES ($1::uuid, $2, $3, $4, $5)
                """,
                song_id, metadata.title, metadata.artist, metadata.album, metadata.duration
            )
            
            # 3. Bulk insert hashes
            # hashes is a list of (hash_value, offset_in_seconds)
            hash_records = [(h, song_id, round(offset, 3)) for h, offset in hashes]
            
            await conn.executemany(
                """
                INSERT INTO hashes (hash_value, song_id, time_offset)
                VALUES ($1, $2::uuid, $3)
                """,
                hash_records
            )
            
    return song_id, len(hashes)
