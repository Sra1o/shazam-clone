from collections import defaultdict
from db import get_db_pool
from fingerprint import fingerprint_audio

async def match_audio_snippet(file_path: str):
    """
    Fingerprints a query audio file, searches PostgreSQL for matches,
    aligns the offsets, and finds the best matching song.
    Uses relative confidence scoring to avoid false positives at scale.
    """
    # 1. Fingerprint the query audio
    query_hashes = fingerprint_audio(file_path)
    
    if not query_hashes:
        return None
        
    pool = get_db_pool()
    
    hash_to_query_offsets = defaultdict(list)
    for h, offset in query_hashes:
        hash_to_query_offsets[h].append(offset)
        
    unique_hashes = list(hash_to_query_offsets.keys())
    
    if not unique_hashes:
        return None
        
    # 2. Query PostgreSQL for all matching hashes
    async with pool.acquire() as conn:
        records = await conn.fetch(
            """
            SELECT hash_value, song_id, time_offset 
            FROM hashes 
            WHERE hash_value = ANY($1)
            """,
            unique_hashes
        )
        
    if not records:
        return None
        
    # 3. Calculate Deltas
    song_delta_counts = defaultdict(lambda: defaultdict(int))
    
    for record in records:
        db_hash = record['hash_value']
        song_id = str(record['song_id'])
        db_offset = record['time_offset']
        
        query_offsets = hash_to_query_offsets[db_hash]
        
        for q_offset in query_offsets:
            delta = db_offset - q_offset
            # Bucket to nearest 0.25s for tighter alignment (was 0.5s)
            bucketed_delta = round(delta * 4) / 4
            song_delta_counts[song_id][bucketed_delta] += 1
            
    # 4. Find the best and second-best matches
    best_song_id = None
    best_peak_count = 0
    best_delta = 0
    second_best_peak_count = 0
    
    for song_id, delta_histogram in song_delta_counts.items():
        if not delta_histogram:
            continue
            
        max_delta = max(delta_histogram, key=delta_histogram.get)
        peak_count = delta_histogram[max_delta]
        
        if peak_count > best_peak_count:
            # Demote the current best to second-best
            second_best_peak_count = best_peak_count
            best_peak_count = peak_count
            best_song_id = song_id
            best_delta = max_delta
        elif peak_count > second_best_peak_count:
            second_best_peak_count = peak_count
            
    # Absolute confidence threshold — need at least 8 aligned hits (was 3)
    if best_peak_count < 8:
        return None
    
    # Relative confidence check — best must be at least 2x the runner-up
    # This prevents false positives when random collisions spread evenly across songs
    if second_best_peak_count > 0 and best_peak_count < (second_best_peak_count * 2):
        return None
        
    # 5. Fetch song metadata from PostgreSQL
    if best_song_id:
        async with pool.acquire() as conn:
            song_doc = await conn.fetchrow(
                "SELECT title, artist, album, cover_art_url FROM songs WHERE id = $1::uuid",
                best_song_id
            )
            
            if song_doc:
                return {
                    "song_id": best_song_id,
                    "title": song_doc['title'],
                    "artist": song_doc['artist'],
                    "album": song_doc['album'],
                    "cover_art_url": song_doc['cover_art_url'],
                    "confidence": best_peak_count,
                    "time_offset": best_delta
                }
        
    return None
