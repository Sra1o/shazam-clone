import { useState, useRef } from 'react';
import { Mic, Square, Loader2 } from 'lucide-react';

function App() {
  const [isRecording, setIsRecording] = useState(false);
  const [isProcessing, setIsProcessing] = useState(false);
  const [result, setResult] = useState<any>(null);
  const [error, setError] = useState<string | null>(null);
  
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const audioChunksRef = useRef<BlobPart[]>([]);

  const startRecording = async () => {
    try {
      setResult(null);
      setError(null);
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
      } else {
        setError('No match found. Try again!');
      }
    } catch (err: any) {
      console.error(err);
      setError(err.message || 'Failed to connect to the matching server.');
    } finally {
      setIsProcessing(false);
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

      {result && (
        <div className="result-card">
          <div className="song-title">{result.title}</div>
          <div className="song-artist">{result.artist}</div>
          {result.album && <div className="song-album">{result.album}</div>}
        </div>
      )}
    </div>
  );
}

export default App;
