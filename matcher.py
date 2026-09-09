import asyncio
import math
from collections import defaultdict
from db import get_db_pool
from fingerprint import fingerprint_audio

async def match_audio_snippet(file_path: str):
    """
    Fingerprints a query audio file, searches PostgreSQL for matches,
    aligns the offsets, and finds the best matching song.
    Uses IDF weighting to remain accurate as the database scales.
    """
    # 1. Fingerprint the query audio (CPU heavy, run in thread pool)
    query_hashes = await asyncio.to_thread(fingerprint_audio, file_path)
    
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
    
    # 3. Calculate IDF weights for each hash
    # Count how many distinct songs each hash appears in
    hash_song_count = defaultdict(set)
    for record in records:
        hash_song_count[record['hash_value']].add(str(record['song_id']))
    
    # IDF weight: hashes unique to 1 song get weight 1.0,
    # hashes in many songs get progressively less weight
    hash_idf = {}
    for h, songs in hash_song_count.items():
        num_songs = len(songs)
        # 1/n weighting: appears in 1 song = 1.0, in 5 songs = 0.2, in 20 songs = 0.05
        hash_idf[h] = 1.0 / num_songs
        
    # 4. Calculate Deltas with IDF-weighted counts
    song_delta_counts = defaultdict(lambda: defaultdict(float))
    
    for record in records:
        db_hash = record['hash_value']
        song_id = str(record['song_id'])
        db_offset = record['time_offset']
        
        weight = hash_idf[db_hash]
        query_offsets = hash_to_query_offsets[db_hash]
        
        for q_offset in query_offsets:
            delta = db_offset - q_offset
            
            # Bucket to nearest frame (approx 0.093s)
            frame_delta = int(round(delta / 0.0928798))
            
            # Fuzzy match: add to the exact frame, and adjacent frames to handle jitter
            song_delta_counts[song_id][frame_delta] += weight
            song_delta_counts[song_id][frame_delta - 1] += weight
            song_delta_counts[song_id][frame_delta + 1] += weight
            
    # 5. Find the best matches
    scored_songs = []
    
    for song_id, delta_histogram in song_delta_counts.items():
        if not delta_histogram:
            continue
            
        max_delta = max(delta_histogram, key=delta_histogram.get)
        peak_count = delta_histogram[max_delta]
        
        scored_songs.append({
            "song_id": song_id,
            "peak_count": round(peak_count, 1),
            "time_offset": max_delta
        })
        
    # Sort by highest peak count
    scored_songs.sort(key=lambda x: x["peak_count"], reverse=True)
    top_3 = scored_songs[:3]
    
    is_match = False
    best_match_data = None
    
    if len(top_3) > 0:
        best_peak_count = top_3[0]["peak_count"]
        second_peak_count = top_3[1]["peak_count"] if len(top_3) > 1 else 0
        
        # Absolute confidence threshold
        # We require at least 10 weighted hits to declare a definitive match.
        if best_peak_count >= 10:
            is_match = True
        # Relative confidence threshold
        # If the best match has fewer hits but is significantly
        # higher than the second best match, we can still declare a match.
        elif best_peak_count >= 5 and (second_peak_count == 0 or best_peak_count >= second_peak_count * 2):
            is_match = True
            
    # 6. Fetch song metadata from PostgreSQL for the top 3
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

