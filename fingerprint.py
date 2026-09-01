import librosa
import numpy as np
from scipy.ndimage import maximum_filter
import hashlib

# Configuration constants
DEFAULT_FS = 22050
WINDOW_SIZE = 4096
OVERLAP_RATIO = 0.5
FAN_VALUE = 15 # Restored to 15 to ensure enough hashes are generated despite noise
MIN_HASH_TIME_DELTA = 0
MAX_HASH_TIME_DELTA = 100 # Keep at 100 for time precision
PEAK_NEIGHBORHOOD_SIZE = 20 # Restored to 20 to allow more peaks (vital for short mic recordings)
MIN_AMPLITUDE_PERCENTILE = 80 # Lowered from 90 to 80 to keep more peaks, ensuring robustness to noise

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

def get_2D_peaks(arr2D):
    """
    Applies a 2D max filter to find the highest energy peaks.
    Uses a larger neighborhood and stricter threshold to produce fewer,
    more distinctive peaks — critical for accuracy at scale.
    """
    # Create a 2D filter structure
    neighborhood = np.ones((PEAK_NEIGHBORHOOD_SIZE, PEAK_NEIGHBORHOOD_SIZE))
    
    # Apply the local maximum filter
    local_max = maximum_filter(arr2D, footprint=neighborhood) == arr2D
    
    # Thresholding based on percentile to be robust across different audio volumes
    threshold = np.percentile(arr2D, MIN_AMPLITUDE_PERCENTILE)
    threshold_mask = arr2D > threshold
    
    # Get the peaks (no need for background mask with dB spectrogram — silence is already very negative)
    peaks_mask = local_max & threshold_mask
    
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
        
        # Look ahead up to FAN_VALUE targets within the target window
        for j in range(1, FAN_VALUE + 1):
            if (i + j) < len(peaks):
                target = peaks[i + j]
                
                t_delta = target[0] - anchor[0]
                
                # Check if target is within the valid time delta zone
                if MIN_HASH_TIME_DELTA <= t_delta <= MAX_HASH_TIME_DELTA:
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
                    
    return hashes

def fingerprint_audio(audio_path):
    """
    End-to-end function to generate hashes for an audio file.
    Returns: list of (hash_value, offset_in_seconds) tuples
    """
    spectrogram, sr, hop_length = generate_spectrogram(audio_path)
    peaks = get_2D_peaks(spectrogram)
    hashes = generate_hashes(peaks)
    
    # Convert frame offsets to seconds for better interpretability and robustness
    # time = frame_idx * hop_length / sr
    hashes_in_seconds = [(h[0], h[1] * hop_length / sr) for h in hashes]
    
    return hashes_in_seconds
