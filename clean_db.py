import asyncio
import asyncpg
import os

# Ensure this script is run with the same environment variables as the main app
DATABASE_URL = os.environ.get("DATABASE_URL") or os.environ.get("POSTGRES_URL") or "postgresql://postgres:postgres@localhost:5432/shazam"

async def clean_database():
    print(f"Connecting to {DATABASE_URL}...")
    try:
        conn = await asyncpg.connect(DATABASE_URL)
        
        # 1. Delete duplicates, keeping the first ingested id for each (title, artist)
        print("Removing duplicates...")
        await conn.execute("""
            DELETE FROM songs a USING (
                SELECT MIN(id) as id, title, artist
                FROM songs 
                GROUP BY title, artist HAVING COUNT(*) > 1
            ) b
            WHERE a.title = b.title 
            AND a.artist = b.artist 
            AND a.id <> b.id;
        """)
        print("Duplicates removed successfully.")
        
        # 2. Add a UNIQUE constraint (if not already there)
        print("Ensuring UNIQUE constraint on title and artist exists...")
        try:
            await conn.execute("""
                ALTER TABLE songs ADD CONSTRAINT uq_title_artist UNIQUE (title, artist);
            """)
            print("UNIQUE constraint added successfully.")
        except asyncpg.exceptions.DuplicateTableError: 
            # Could also be DuplicateObjectError depending on postgres version
            print("Constraint already exists.")
        except asyncpg.exceptions.InvalidTableDefinitionError:
             print("UNIQUE constraint might already exist, or check syntax.")
        except Exception as e:
            if 'already exists' in str(e):
                print("Constraint already exists.")
            else:
                print(f"Notice: {e}")
                
        await conn.close()
        print("Database cleaned and secured.")
    except Exception as e:
        print(f"Failed to connect or run queries: {e}")
        print("Please ensure your database is running and DATABASE_URL is set if using a remote DB.")

if __name__ == "__main__":
    asyncio.run(clean_database())
