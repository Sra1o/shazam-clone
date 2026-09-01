import json
from collections import defaultdict
from db import get_db, get_redis
from fingerprint import fingerprint_audio

async def match_audio_snippet(file_path: str):
    """
    Fingerprints a query audio file, searches Redis for matches,
    aligns the offsets, and finds the best matching song.
    """
    # 1. Fingerprint the query audio
    query_hashes = fingerprint_audio(file_path)
    
    if not query_hashes:
        return None
        
    redis_client = get_redis()
    
    # 2. Query Redis for all matching hashes
    # To optimize, we can batch the lrange commands using pipeline
    pipeline = redis_client.pipeline()
    
    # We only take the unique hashes from the query to avoid redundant queries,
    # but we need to track their query offsets.
    hash_to_query_offsets = defaultdict(list)
    for h, offset in query_hashes:
        hash_to_query_offsets[h].append(offset)
        
    unique_hashes = list(hash_to_query_offsets.keys())
    
    for h in unique_hashes:
        # Get all elements from the list stored at this hash key
        pipeline.lrange(h, 0, -1)
        
    results = await pipeline.execute()
    
    # 3. Calculate Deltas
    # Structure: song_id -> delta -> count
    # Bucket to 1 decimal place (100ms) for robustness against slight timing shifts
    song_delta_counts = defaultdict(lambda: defaultdict(int))
    
    for i, h in enumerate(unique_hashes):
        db_matches = results[i]
        query_offsets = hash_to_query_offsets[h]
        
        for match_str in db_matches:
            try:
                match = json.loads(match_str)
                song_id = match["s"]
                db_offset = match["o"]
                
                for q_offset in query_offsets:
                    # Calculate delta
                    delta = db_offset - q_offset
                    
                    # Bucket the delta (e.g., to the nearest 0.1s)
                    bucketed_delta = round(delta, 1)
                    
                    song_delta_counts[song_id][bucketed_delta] += 1
            except Exception:
                continue
                
    if not song_delta_counts:
        return None
        
    # 4. Find the song with the highest peak in its delta histogram
    best_song_id = None
    best_peak_count = 0
    best_delta = 0
    
    for song_id, delta_histogram in song_delta_counts.items():
        if not delta_histogram:
            continue
            
        # Find the max peak for this song
        max_delta = max(delta_histogram, key=delta_histogram.get)
        peak_count = delta_histogram[max_delta]
        
        if peak_count > best_peak_count:
            best_peak_count = peak_count
            best_song_id = song_id
            best_delta = max_delta
            
    # Confidence threshold to avoid false positives
    if best_peak_count < 5:
        return None
        
    # 5. Fetch song metadata from DB
    if best_song_id:
        db = get_db()
        song_doc = await db.songs.find_one({"_id": best_song_id})
        
        if song_doc:
            return {
                "song_id": best_song_id,
                "title": song_doc.get("title"),
                "artist": song_doc.get("artist"),
                "album": song_doc.get("album"),
                "confidence": best_peak_count,
                "time_offset": best_delta
            }
        
    return None
