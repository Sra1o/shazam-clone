from collections import defaultdict
from db import get_db_pool
from fingerprint import fingerprint_audio

async def match_audio_snippet(file_path: str):
    """
    Fingerprints a query audio file, searches PostgreSQL for matches,
    aligns the offsets, and finds the best matching song.
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
            # Bucket to nearest 0.5s for recording robustness
            bucketed_delta = round(delta * 2) / 2
            song_delta_counts[song_id][bucketed_delta] += 1
            
    # 4. Find the best match
    best_song_id = None
    best_peak_count = 0
    best_delta = 0
    
    for song_id, delta_histogram in song_delta_counts.items():
        if not delta_histogram:
            continue
            
        max_delta = max(delta_histogram, key=delta_histogram.get)
        peak_count = delta_histogram[max_delta]
        
        if peak_count > best_peak_count:
            best_peak_count = peak_count
            best_song_id = song_id
            best_delta = max_delta
            
    # Confidence threshold
    if best_peak_count < 3:
        return None
        
    # 5. Fetch song metadata from PostgreSQL
    if best_song_id:
        async with pool.acquire() as conn:
            song_doc = await conn.fetchrow(
                "SELECT title, artist, album FROM songs WHERE id = $1::uuid",
                best_song_id
            )
            
            if song_doc:
                return {
                    "song_id": best_song_id,
                    "title": song_doc['title'],
                    "artist": song_doc['artist'],
                    "album": song_doc['album'],
                    "confidence": best_peak_count,
                    "time_offset": best_delta
                }
        
    return None
