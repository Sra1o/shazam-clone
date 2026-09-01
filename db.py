import os
import asyncpg
from pydantic import BaseModel
from typing import Optional

# Environment variables or defaults
DATABASE_URL = os.environ.get("DATABASE_URL") or os.environ.get("POSTGRES_URL") or "postgresql://postgres:postgres@localhost:5432/shazam"

# Global pool
pool = None

# Pydantic Schemas for API
class SongMetadata(BaseModel):
    title: str
    artist: str
    album: Optional[str] = None
    duration: float

async def init_db():
    global pool
    pool = await asyncpg.create_pool(DATABASE_URL)
    
    # Initialize schema
    async with pool.acquire() as conn:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS songs (
                id UUID PRIMARY KEY,
                title VARCHAR(255) NOT NULL,
                artist VARCHAR(255) NOT NULL,
                album VARCHAR(255),
                duration REAL NOT NULL
            );
            
            CREATE TABLE IF NOT EXISTS hashes (
                hash_value VARCHAR(8) NOT NULL,
                song_id UUID NOT NULL REFERENCES songs(id) ON DELETE CASCADE,
                time_offset REAL NOT NULL
            );
            
            -- Create a B-Tree index on hash_value for extremely fast matching
            CREATE INDEX IF NOT EXISTS idx_hashes_hash_value ON hashes (hash_value);
            
            -- Optional: Index on song_id for fast deletion/management
            CREATE INDEX IF NOT EXISTS idx_hashes_song_id ON hashes (song_id);
        """)

async def close_db():
    if pool:
        await pool.close()

def get_db_pool():
    if pool is None:
        raise RuntimeError("Database pool not initialized")
    return pool
