import asyncio
import asyncpg
import os
import sys

# Ensure this script is run with the same environment variables as the main app
DATABASE_URL = os.environ.get("DATABASE_URL") or os.environ.get("POSTGRES_URL") or "postgresql://postgres:postgres@localhost:5432/shazam"

async def clean_duplicates():
    """Remove duplicate songs, keeping the first ingested id for each (title, artist)."""
    print(f"Connecting to {DATABASE_URL}...")
    conn = await asyncpg.connect(DATABASE_URL)
    
    # Delete duplicates, keeping the first ingested id for each (title, artist)
    print("Removing duplicates...")
    result = await conn.execute("""
        DELETE FROM songs a USING (
            SELECT MIN(id) as id, title, artist
            FROM songs 
            GROUP BY title, artist HAVING COUNT(*) > 1
        ) b
        WHERE a.title = b.title 
        AND a.artist = b.artist 
        AND a.id <> b.id;
    """)
    print(f"Done. {result}")
    
    # Add a UNIQUE constraint (if not already there)
    print("Ensuring UNIQUE constraint on (title, artist)...")
    try:
        await conn.execute("""
            ALTER TABLE songs ADD CONSTRAINT uq_title_artist UNIQUE (title, artist);
        """)
        print("UNIQUE constraint added.")
    except Exception as e:
        if 'already exists' in str(e):
            print("Constraint already exists.")
        else:
            print(f"Notice: {e}")
            
    await conn.close()
    print("Database cleaned and secured.")

async def wipe_for_reingestion():
    """Wipe all songs and hashes so you can re-ingest with the new fingerprint algorithm."""
    print(f"Connecting to {DATABASE_URL}...")
    conn = await asyncpg.connect(DATABASE_URL)
    
    hash_count = await conn.fetchval("SELECT COUNT(*) FROM hashes")
    song_count = await conn.fetchval("SELECT COUNT(*) FROM songs")
    print(f"Found {song_count} songs and {hash_count} hashes.")
    
    confirm = input(f"This will DELETE all {song_count} songs and {hash_count} hashes. Type 'yes' to confirm: ")
    if confirm.strip().lower() != 'yes':
        print("Aborted.")
        await conn.close()
        return
    
    # Hashes have ON DELETE CASCADE, so deleting songs wipes hashes too
    await conn.execute("DELETE FROM hashes;")
    await conn.execute("DELETE FROM songs;")
    
    print("All songs and hashes deleted. You can now re-ingest with the improved algorithm.")
    await conn.close()

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--wipe":
        asyncio.run(wipe_for_reingestion())
    else:
        asyncio.run(clean_duplicates())
        print("\nTip: Run with --wipe to delete ALL songs and hashes for a fresh re-ingestion.")
