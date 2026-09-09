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

async def delete_song(title: str):
    """Delete a specific song and all its hashes by title."""
    print(f"Connecting to {DATABASE_URL}...")
    conn = await asyncpg.connect(DATABASE_URL)
    
    # Check if the song exists
    songs = await conn.fetch("SELECT id, title, artist FROM songs WHERE title ILIKE $1", f"%{title}%")
    if not songs:
        print(f"No song found matching title '{title}'.")
        await conn.close()
        return
        
    print(f"Found {len(songs)} song(s) matching '{title}':")
    for s in songs:
        print(f" - {s['title']} by {s['artist']} (ID: {s['id']})")
        
    confirm = input(f"Type 'yes' to delete these songs and all their hashes: ")
    if confirm.strip().lower() != 'yes':
        print("Aborted.")
        await conn.close()
        return
        
    for s in songs:
        await conn.execute("DELETE FROM songs WHERE id = $1", s['id'])
        print(f"Deleted '{s['title']}'. (Hashes deleted automatically via CASCADE).")
        
    await conn.close()

if __name__ == "__main__":
    if len(sys.argv) > 1:
        if sys.argv[1] == "--wipe":
            asyncio.run(wipe_for_reingestion())
        elif sys.argv[1] == "--delete" and len(sys.argv) > 2:
            asyncio.run(delete_song(sys.argv[2]))
        else:
            print("Usage: python clean_db.py [--wipe] [--delete \"song title\"]")
    else:
        asyncio.run(clean_duplicates())
        print("\nTip: Run with --wipe to delete ALL songs and hashes for a fresh re-ingestion.")
        print("Tip: Run with --delete \"song title\" to delete a specific song.")
