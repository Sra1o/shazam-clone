import { useState, useRef } from 'react';
import { Mic, Square, Loader2 } from 'lucide-react';

function App() {
  const [isRecording, setIsRecording] = useState(false);
  const [isProcessing, setIsProcessing] = useState(false);
  const [result, setResult] = useState<any>(null);
  const [topMatches, setTopMatches] = useState<any[]>([]);
  const [notFound, setNotFound] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [lastRecordingUrl, setLastRecordingUrl] = useState<string | null>(null);
  
  // Spotify Ingestion State
  const [spotifyUrl, setSpotifyUrl] = useState('');
  const [ingestStatus, setIngestStatus] = useState<'idle' | 'loading' | 'success' | 'error'>('idle');
  const [ingestMessage, setIngestMessage] = useState('');
  
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const audioChunksRef = useRef<BlobPart[]>([]);

  const startRecording = async () => {
    try {
      setResult(null);
      setTopMatches([]);
      setNotFound(false);
      setError(null);
      if (lastRecordingUrl) {
        URL.revokeObjectURL(lastRecordingUrl);
        setLastRecordingUrl(null);
      }
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const mediaRecorder = new MediaRecorder(stream);
      mediaRecorderRef.current = mediaRecorder;
      audioChunksRef.current = [];

      mediaRecorder.ondataavailable = (e) => {
        if (e.data.size > 0) {
          audioChunksRef.current.push(e.data);
        }
      };

      mediaRecorder.onstop = async () => {
        const audioBlob = new Blob(audioChunksRef.current, { type: 'audio/webm' });
        
        // Save the URL for playback
        const url = URL.createObjectURL(audioBlob);
        setLastRecordingUrl(url);

        // Stop all tracks immediately to release microphone
        stream.getTracks().forEach(track => track.stop());
        
        await sendAudioToAPI(audioBlob);
      };

      mediaRecorder.start();
      setIsRecording(true);
      
      // Auto-stop after 8 seconds
      setTimeout(() => {
        if (mediaRecorderRef.current && mediaRecorderRef.current.state === 'recording') {
          stopRecording();
        }
      }, 8000);
      
    } catch (err) {
      console.error(err);
      setError('Microphone access denied or not available.');
    }
  };

  const stopRecording = () => {
    if (mediaRecorderRef.current && mediaRecorderRef.current.state !== 'inactive') {
      mediaRecorderRef.current.stop();
      setIsRecording(false);
      setIsProcessing(true);
    }
  };

  const sendAudioToAPI = async (blob: Blob) => {
    try {
      const formData = new FormData();
      formData.append('file', blob, 'recording.webm');

      const apiUrl = import.meta.env.VITE_API_URL || 'http://localhost:8000';
      const response = await fetch(`${apiUrl}/identify`, {
        method: 'POST',
        body: formData,
      });

      if (!response.ok) {
        let errDetail = 'Unknown error';
        try {
          const errData = await response.json();
          errDetail = errData.detail || errDetail;
        } catch (e) {}
        throw new Error(`API error: ${response.status} - ${errDetail}`);
      }

      const data = await response.json();
      
      if (data.status === 'success') {
        setResult(data.match);
        setTopMatches(data.top_matches || []);
      } else {
        setNotFound(true);
        setTopMatches(data.top_matches || []);
      }
    } catch (err: any) {
      console.error(err);
      setError(err.message || 'Failed to connect to the matching server.');
    } finally {
      setIsProcessing(false);
    }
  };

  const handleSpotifyIngest = async () => {
    if (!spotifyUrl) return;
    setIngestStatus('loading');
    setIngestMessage('');

    try {
      const apiUrl = import.meta.env.VITE_API_URL || 'http://localhost:8000';
      const response = await fetch(`${apiUrl}/ingest/spotify`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ url: spotifyUrl }),
      });

      const data = await response.json().catch(() => ({}));

      if (!response.ok) {
        throw new Error(data.detail || 'Failed to start ingestion');
      }

      setIngestStatus('success');
      setIngestMessage(data.message);
      setSpotifyUrl('');
      
      // Clear success message after 5 seconds
      setTimeout(() => {
        setIngestStatus('idle');
        setIngestMessage('');
      }, 5000);
      
    } catch (err: any) {
      setIngestStatus('error');
      setIngestMessage(err.message);
    }
  };

  return (
    <div className="app-container">
      <div>
        <h1>Shazam Clone</h1>
        <p className="subtitle">Identify any song in seconds</p>
      </div>

      <button 
        className={`mic-button ${isRecording ? 'recording' : ''}`}
        onClick={isRecording ? stopRecording : startRecording}
        disabled={isProcessing}
      >
        {isProcessing ? (
          <Loader2 size={48} className="animate-spin" />
        ) : isRecording ? (
          <Square size={48} fill="currentColor" />
        ) : (
          <Mic size={48} />
        )}
      </button>

      <div className="status-text">
        {isRecording && "Listening... (auto-stops in 8s)"}
        {isProcessing && "Identifying..."}
        {!isRecording && !isProcessing && "Tap to listen"}
      </div>

      {error && (
        <div className="error-message">
          {error}
        </div>
      )}

      {notFound && (
        <div className="not-found-card">
          <div className="not-found-icon">
            <svg xmlns="http://www.w3.org/2000/svg" width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
              <path d="M9 18V5l12-2v13"/>
              <circle cx="6" cy="18" r="3"/>
              <circle cx="18" cy="16" r="3"/>
              <line x1="2" y1="2" x2="22" y2="22" strokeWidth="2"/>
            </svg>
          </div>
          <div className="not-found-title">Song not recognized</div>
          <div className="not-found-subtitle">Try recording a louder or clearer snippet, or add the song using a Spotify link below.</div>
          
          {lastRecordingUrl && (
            <div style={{ marginTop: '1.5rem', marginBottom: '1.5rem' }}>
              <div style={{ fontSize: '0.85rem', color: '#8c9bb4', marginBottom: '0.5rem' }}>Listen to your recording:</div>
              <audio src={lastRecordingUrl} controls style={{ width: '100%', height: '36px' }} />
            </div>
          )}

          {topMatches.length > 0 && (
            <div className="top-matches-container">
              <div className="top-matches-header">Closest Partial Matches:</div>
              {topMatches.map((match, i) => (
                <div key={match.song_id} className="top-match-item">
                  <span className="top-match-rank">#{i + 1}</span>
                  {match.cover_art_url ? (
                    <img src={match.cover_art_url} alt="Cover" className="top-match-cover" />
                  ) : (
                    <div className="top-match-cover-placeholder" />
                  )}
                  <div className="top-match-info">
                    <div className="top-match-title">{match.title}</div>
                    <div className="top-match-artist">{match.artist}</div>
                  </div>
                  <div className="top-match-confidence">{match.confidence} hits</div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {result && (
        <div className="result-card">
          <div className="result-card-inner">
            {result.cover_art_url ? (
              <img 
                src={result.cover_art_url} 
                alt={`${result.album || result.title} cover art`}
                className="cover-art"
              />
            ) : (
              <div className="cover-art-placeholder">
                <svg xmlns="http://www.w3.org/2000/svg" width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M9 18V5l12-2v13"/>
                  <circle cx="6" cy="18" r="3"/>
                  <circle cx="18" cy="16" r="3"/>
                </svg>
              </div>
            )}
            <div className="result-info">
              <div className="song-title">{result.title}</div>
              <div className="song-artist">{result.artist}</div>
              {result.album && <div className="song-album">{result.album}</div>}
            </div>
          </div>
          
          {lastRecordingUrl && (
            <div style={{ marginTop: '1.5rem', paddingTop: '1.5rem', borderTop: '1px solid rgba(255, 255, 255, 0.08)' }}>
              <div style={{ fontSize: '0.85rem', color: '#8c9bb4', marginBottom: '0.5rem' }}>Listen to your recording:</div>
              <audio src={lastRecordingUrl} controls style={{ width: '100%', height: '36px' }} />
            </div>
          )}
        </div>
      )}

      {/* Spotify Ingestion Section */}
      <div className="spotify-ingest-container">
        <div className="spotify-input-wrapper">
          <input
            type="text"
            className="spotify-input"
            placeholder="Paste a Spotify Track link..."
            value={spotifyUrl}
            onChange={(e) => setSpotifyUrl(e.target.value)}
            disabled={ingestStatus === 'loading'}
          />
          <button 
            className="spotify-btn" 
            onClick={handleSpotifyIngest}
            disabled={!spotifyUrl || ingestStatus === 'loading'}
          >
            {ingestStatus === 'loading' ? <Loader2 className="animate-spin" size={20} /> : 'Add'}
          </button>
        </div>
        
        {ingestMessage && (
          <div className={`ingest-message ${ingestStatus}`}>
            {ingestMessage}
          </div>
        )}
      </div>

    </div>
  );
}

export default App;
