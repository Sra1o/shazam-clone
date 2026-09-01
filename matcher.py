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
            
    # 4. Find the best matches
    scored_songs = []
    
    for song_id, delta_histogram in song_delta_counts.items():
        if not delta_histogram:
            continue
            
        max_delta = max(delta_histogram, key=delta_histogram.get)
        peak_count = delta_histogram[max_delta]
        
        scored_songs.append({
            "song_id": song_id,
            "peak_count": peak_count,
            "time_offset": max_delta
        })
        
    # Sort by highest peak count
    scored_songs.sort(key=lambda x: x["peak_count"], reverse=True)
    top_3 = scored_songs[:3]
    
    is_match = False
    best_match_data = None
    
    if len(top_3) > 0:
        best_peak_count = top_3[0]["peak_count"]
        second_best_peak_count = top_3[1]["peak_count"] if len(top_3) > 1 else 0
        
        # Absolute confidence threshold — need at least 5 aligned hits
        # Relative confidence check — best must be at least 2x the runner-up
        if best_peak_count >= 5 and (second_best_peak_count == 0 or best_peak_count >= (second_best_peak_count * 2)):
            is_match = True
            
    # 5. Fetch song metadata from PostgreSQL for the top 3
    top_matches_metadata = []
    
    if top_3:
        async with pool.acquire() as conn:
            for s in top_3:
                doc = await conn.fetchrow(
                    "SELECT title, artist, album, cover_art_url FROM songs WHERE id = $1::uuid",
                    s["song_id"]
                )
                
                if doc:
                    top_matches_metadata.append({
                        "song_id": s["song_id"],
                        "title": doc['title'],
                        "artist": doc['artist'],
                        "album": doc['album'],
                        "cover_art_url": doc['cover_art_url'],
                        "confidence": s["peak_count"],
                        "time_offset": s["time_offset"]
                    })
                    
    if is_match and top_matches_metadata:
        best_match_data = top_matches_metadata[0]
        
    return {
        "is_match": is_match,
        "match": best_match_data,
        "top_matches": top_matches_metadata
    }
