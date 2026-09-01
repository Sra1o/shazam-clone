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
MAX_HASH_TIME_DELTA = 150 # Look up to 150 frames ahead
PEAK_NEIGHBORHOOD_SIZE = 20 # Keep neighborhood size

# Frequency bounds for filtering out low-end rumble and high-end hiss
MIN_FREQ_HZ = 250
MAX_FREQ_HZ = 3000

# Number of logarithmic frequency bands to balance peak extraction
NUM_BANDS = 6
MIN_AMPLITUDE_PERCENTILE = 80

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
    Applies a 2D max filter to find the highest energy peaks, but strictly limits
    them to specific frequency bands (250Hz - 3000Hz) to ignore rumble and hiss.
    Extracts peaks independently per logarithmic frequency band to prevent bass 
    from dominating the fingerprint.
    """
    frequencies, times = [], []
    
    # Calculate frequency per bin
    freq_per_bin = sr / n_fft
    
    # Filter bounds
    min_bin = int(MIN_FREQ_HZ / freq_per_bin)
    max_bin = int(MAX_FREQ_HZ / freq_per_bin)
    
    # Ensure max_bin doesn't exceed array shape
    max_bin = min(max_bin, arr2D.shape[0])
    
    # Create logarithmic frequency bands
    # We want bands that get exponentially larger in higher frequencies (like human hearing)
    band_edges = np.logspace(np.log10(min_bin), np.log10(max_bin), NUM_BANDS + 1)
    band_edges = np.round(band_edges).astype(int)
    
    neighborhood = np.ones((PEAK_NEIGHBORHOOD_SIZE, PEAK_NEIGHBORHOOD_SIZE))
    
    # Process each band independently
    for i in range(NUM_BANDS):
        start_bin = band_edges[i]
        end_bin = band_edges[i+1]
        
        if start_bin >= end_bin:
            continue
            
        band_slice = arr2D[start_bin:end_bin, :]
        
        if band_slice.size == 0:
            continue
            
        # Apply local max filter within the band
        local_max = maximum_filter(band_slice, footprint=neighborhood) == band_slice
        
        # Thresholding based on percentile WITHIN THIS BAND ONLY
        threshold = np.percentile(band_slice, MIN_AMPLITUDE_PERCENTILE)
        threshold_mask = band_slice > threshold
        
        # Get peaks
        peaks_mask = local_max & threshold_mask
        band_freqs, band_times = np.where(peaks_mask)
        
        # Offset the frequencies back to their global indices
        frequencies.extend(band_freqs + start_bin)
        times.extend(band_times)
        
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
    peaks = get_2D_peaks(spectrogram, sr)
    hashes = generate_hashes(peaks)
    
    # Convert frame offsets to seconds for better interpretability and robustness
    # time = frame_idx * hop_length / sr
    hashes_in_seconds = [(h[0], h[1] * hop_length / sr) for h in hashes]
    
    return hashes_in_seconds
