import os
from motor.motor_asyncio import AsyncIOMotorClient
import redis.asyncio as redis
from pydantic import BaseModel, Field
from typing import Optional

# Environment variables or defaults
MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")
REDIS_URI = os.getenv("REDIS_URI", "redis://localhost:6379")

# Global clients
mongo_client = None
db = None
redis_client = None

# --- MongoDB Schemas (Metadata) ---

class SongMetadata(BaseModel):
    """
    Schema for storing song metadata in MongoDB.
    """
    title: str
    artist: str
    album: Optional[str] = None
    duration: float  # Duration in seconds

class SongInDB(SongMetadata):
    """
    Schema representing a song document as stored in MongoDB.
    """
    id: str = Field(alias="_id")


# --- Database Connection Management ---

async def init_db():
    """
    Initialize connections to MongoDB and Redis.
    Should be called on application startup.
    """
    global mongo_client, db, redis_client
    
    # 1. Initialize MongoDB connection (Motor)
    mongo_client = AsyncIOMotorClient(MONGO_URI)
    db = mongo_client.shazam_clone
    
    # Optional: Create indexes (e.g., on title/artist if we want to search later)
    # await db.songs.create_index([("title", 1), ("artist", 1)])
    
    # 2. Initialize Redis connection pool
    # decode_responses=True ensures we get strings back instead of bytes
    redis_client = redis.from_url(REDIS_URI, decode_responses=True)

async def close_db():
    """
    Close database connections gracefully.
    Should be called on application shutdown.
    """
    if mongo_client:
        mongo_client.close()
    if redis_client:
        await redis_client.aclose()

def get_redis():
    """
    Dependency to get the Redis client.
    """
    return redis_client

def get_db():
    """
    Dependency to get the MongoDB database instance.
    """
    return db
