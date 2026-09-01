import librosa
import numpy as np
from scipy.ndimage import maximum_filter
import hashlib

# Configuration constants
DEFAULT_FS = 11025 # Downsampled for robustness against pitch variations
WINDOW_SIZE = 2048 # Adjusted window size for the lower sample rate
OVERLAP_RATIO = 0.5
FAN_VALUE = 15
MIN_HASH_TIME_DELTA = 10 # Enforce a target zone (at least 10 frames ahead)
MAX_HASH_TIME_DELTA = 50 # Reduced to 50 to prevent time-drift destruction of hashes

# The 2D Max Filter Neighborhood (Time x Frequency)
# We use a rectangular neighborhood to force sparseness in time but allow more density in frequency
PEAK_NEIGHBORHOOD_SIZE_TIME = 20
PEAK_NEIGHBORHOOD_SIZE_FREQ = 10 

# Thresholding constants
MIN_FREQ_HZ = 250 # High-pass filter to block rumble
THRESHOLD_OFFSET_DB = 15 # Dynamic threshold: Mean + 15dB

def generate_spectrogram(audio_path, sr=DEFAULT_FS):
    """
    Loads audio, converts to mono, resamples, and computes a log-power spectrogram.
    Using log-power (dB) instead of raw magnitude makes peak detection robust
    across different recording volumes and environments.
    """
    y, sr = librosa.load(audio_path, sr=sr, mono=True)
    
    # Compute STFT
    hop_length = int(WINDOW_SIZE * (1 - OVERLAP_RATIO))
    stft = librosa.stft(y, n_fft=WINDOW_SIZE, hop_length=hop_length)
    
    # Convert to log-power spectrogram (dB scale) for dynamic range compression
    # This makes peak detection much more robust across different volumes
    spectrogram = librosa.amplitude_to_db(np.abs(stft), ref=np.max)
    
    return spectrogram, sr, hop_length

def get_2D_peaks(arr2D, sr=DEFAULT_FS, n_fft=WINDOW_SIZE):
    """
    Applies a 2D max filter to find the highest energy peaks.
    Uses dynamic global thresholding (Mean + 15dB) to prevent noise amplification,
    and a rectangular filter to ensure peaks are distinct in time.
    """
    # Calculate frequency per bin
    freq_per_bin = sr / n_fft
    
    # Filter bounds
    min_bin = int(MIN_FREQ_HZ / freq_per_bin)
    
    # Create a rectangular 2D filter structure (Time x Frequency)
    # We want it wider in time (20) and shorter in freq (10)
    neighborhood = np.ones((PEAK_NEIGHBORHOOD_SIZE_TIME, PEAK_NEIGHBORHOOD_SIZE_FREQ))
    
    # Apply the local maximum filter over the ENTIRE spectrogram
    local_max = maximum_filter(arr2D, footprint=neighborhood) == arr2D
    
    # Dynamic Global Thresholding: Calculate mean across the entire array
    mean_db = np.mean(arr2D)
    threshold = mean_db + THRESHOLD_OFFSET_DB
    threshold_mask = arr2D > threshold
    
    # Ignore frequencies below 250Hz
    freq_mask = np.ones(arr2D.shape, dtype=bool)
    freq_mask[:min_bin, :] = False
    
    # Get the final valid peaks
    peaks_mask = local_max & threshold_mask & freq_mask
    
    # Get coordinates of peaks (freq_idx, time_idx)
    frequencies, times = np.where(peaks_mask)
    
    # Return as list of (time, frequency)
    # We sort by time to facilitate combinatorial hashing
    peaks = list(zip(times, frequencies))
    peaks.sort(key=lambda x: x[0])
    
    return peaks

def generate_hashes(peaks):
    """
    Combinatorial Hashing: For every "anchor" peak, look ahead to "target" peaks 
    within a specific target zone. Generate a robust 32-bit hash.
    """
    hashes = []
    
    for i in range(len(peaks)):
        anchor = peaks[i]
        
        # Scan forward to find targets IN the target zone
        targets_found = 0
        j = 1
        
        while (i + j) < len(peaks) and targets_found < FAN_VALUE:
            target = peaks[i + j]
            t_delta = target[0] - anchor[0]
            
            # If we've passed the max delta, stop looking for this anchor
            if t_delta > MAX_HASH_TIME_DELTA:
                break
                
            # Check if target is within the valid time delta zone
            if t_delta >= MIN_HASH_TIME_DELTA:
                anchor_freq = anchor[1]
                target_freq = target[1]
                
                # Generate a robust 32-bit hash string using SHA1
                # [Anchor Frequency, Target Frequency, Delta Time]
                hash_input = f"{anchor_freq}|{target_freq}|{t_delta}"
                hash_obj = hashlib.sha1(hash_input.encode('utf-8'))
                
                # Take the first 8 hex characters (32 bits)
                hash_value = hash_obj.hexdigest()[:8]
                
                # Track absolute time offset of anchor (in frames)
                offset = anchor[0]
                hashes.append((hash_value, offset))
                
                targets_found += 1
                
            j += 1
                    
    return hashes

def fingerprint_audio(audio_path):
    """
    End-to-end function to generate hashes for an audio file.
    Returns: list of (hash_value, offset_in_seconds) tuples
    """
    spectrogram, sr, hop_length = generate_spectrogram(audio_path)
    peaks = get_2D_peaks(spectrogram, sr)
    hashes = generate_hashes(peaks)
    
    # Convert frame offsets to seconds for better interpretability and robustness
    # time = frame_idx * hop_length / sr
    hashes_in_seconds = [(h[0], h[1] * hop_length / sr) for h in hashes]
    
    return hashes_in_seconds
