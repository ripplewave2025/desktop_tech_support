import { useCallback, useEffect, useRef, useState } from 'react';

/**
 * Voice hook — microphone in, speaker out.
 *
 * Primary path: browser Web Speech API.
 *   - SpeechRecognition       (Chrome, Edge, Safari 14.5+)
 *   - SpeechSynthesis         (universal in modern browsers)
 *
 * Fallback path: server endpoints /api/voice/transcribe and /api/voice/speak
 *   (see api/server.py). Only used if the browser APIs are unavailable and
 *   the server reports them as installed.
 *
 * Why this hook exists: Zora's north star is a user who has never touched
 * a computer before. They shouldn't need a keyboard. They should be able
 * to talk, and hear Zora talk back. This is that layer.
 */

const STORAGE_KEY = 'zora_voice_mode';

function _getRecognitionCtor() {
  if (typeof window === 'undefined') return null;
  return (
    window.SpeechRecognition ||
    window.webkitSpeechRecognition ||
    null
  );
}

function _getSynth() {
  if (typeof window === 'undefined') return null;
  return window.speechSynthesis || null;
}

export function useVoice({ onTranscript } = {}) {
  const RecognitionCtor = _getRecognitionCtor();
  const synth = _getSynth();

  const browserSttSupported = !!RecognitionCtor;
  const browserTtsSupported = !!synth;

  const [isListening, setIsListening] = useState(false);
  const [isSpeaking, setIsSpeaking] = useState(false);
  const [voiceMode, setVoiceModeState] = useState(() => {
    if (typeof window === 'undefined') return false;
    try {
      return window.localStorage.getItem(STORAGE_KEY) === '1';
    } catch {
      return false;
    }
  });
  const [serverCaps, setServerCaps] = useState({
    stt_server_available: false,
    tts_server_available: false,
  });
  const [lastError, setLastError] = useState(null);

  const recognitionRef = useRef(null);
  const mediaRecorderRef = useRef(null);
  const onTranscriptRef = useRef(onTranscript);
  const currentUtteranceRef = useRef(null);

  useEffect(() => {
    onTranscriptRef.current = onTranscript;
  }, [onTranscript]);

  // Ask the backend what it supports, quietly.
  useEffect(() => {
    let cancelled = false;
    fetch('/api/voice/capabilities')
      .then((r) => (r.ok ? r.json() : null))
      .then((data) => {
        if (!cancelled && data) setServerCaps(data);
      })
      .catch(() => {
        // Backend may be degraded — browser path still works.
      });
    return () => {
      cancelled = true;
    };
  }, []);

  // Persist voice-mode preference across sessions.
  const setVoiceMode = useCallback((on) => {
    setVoiceModeState(!!on);
    try {
      if (on) {
        window.localStorage.setItem(STORAGE_KEY, '1');
      } else {
        window.localStorage.removeItem(STORAGE_KEY);
      }
    } catch {
      // Non-fatal.
    }
  }, []);

  const toggleVoiceMode = useCallback(() => {
    setVoiceMode(!voiceMode);
  }, [voiceMode, setVoiceMode]);

  // ─── Speech synthesis (text-to-speech) ────────────────────────────────

  const stopSpeaking = useCallback(() => {
    if (synth && synth.speaking) {
      synth.cancel();
    }
    currentUtteranceRef.current = null;
    setIsSpeaking(false);
  }, [synth]);

  const _speakBrowser = useCallback((text) => {
    if (!synth) return false;
    try {
      synth.cancel(); // Interrupt any in-flight utterance.
      const utter = new SpeechSynthesisUtterance(text);
      // Accessibility defaults: slightly slower, natural pitch.
      utter.rate = 1.0;
      utter.pitch = 1.0;
      utter.volume = 1.0;
      // Prefer a local English voice if one exists.
      const voices = synth.getVoices?.() || [];
      const preferred = voices.find(
        (v) => /en[-_]?us/i.test(v.lang) && v.localService,
      ) || voices.find((v) => /^en/i.test(v.lang));
      if (preferred) utter.voice = preferred;

      utter.onstart = () => setIsSpeaking(true);
      utter.onend = () => {
        setIsSpeaking(false);
        currentUtteranceRef.current = null;
      };
      utter.onerror = (e) => {
        setIsSpeaking(false);
        currentUtteranceRef.current = null;
        setLastError(`TTS error: ${e.error || 'unknown'}`);
      };

      currentUtteranceRef.current = utter;
      synth.speak(utter);
      return true;
    } catch (e) {
      setLastError(`TTS exception: ${e.message || e}`);
      return false;
    }
  }, [synth]);

  const _speakServer = useCallback(async (text) => {
    try {
      setIsSpeaking(true);
      const res = await fetch('/api/voice/speak', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text }),
      });
      if (!res.ok) {
        setIsSpeaking(false);
        return false;
      }
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const audio = new Audio(url);
      audio.onended = () => {
        setIsSpeaking(false);
        URL.revokeObjectURL(url);
      };
      audio.onerror = () => {
        setIsSpeaking(false);
        URL.revokeObjectURL(url);
      };
      await audio.play();
      return true;
    } catch (e) {
      setIsSpeaking(false);
      setLastError(`Server TTS failed: ${e.message || e}`);
      return false;
    }
  }, []);

  const speak = useCallback(async (text) => {
    if (!text || typeof text !== 'string') return;
    const cleaned = text.trim();
    if (!cleaned) return;
    if (browserTtsSupported) {
      if (_speakBrowser(cleaned)) return;
    }
    if (serverCaps.tts_server_available) {
      await _speakServer(cleaned);
    }
  }, [browserTtsSupported, serverCaps.tts_server_available, _speakBrowser, _speakServer]);

  // ─── Speech recognition (speech-to-text) ──────────────────────────────

  const _startBrowserRecognition = useCallback(() => {
    if (!RecognitionCtor) return false;
    try {
      const rec = new RecognitionCtor();
      rec.lang = 'en-US';
      rec.interimResults = false;
      rec.maxAlternatives = 1;
      rec.continuous = false;

      rec.onstart = () => setIsListening(true);
      rec.onresult = (event) => {
        const results = event.results;
        if (results && results.length > 0) {
          const transcript = (results[0][0]?.transcript || '').trim();
          if (transcript && onTranscriptRef.current) {
            onTranscriptRef.current(transcript);
          }
        }
      };
      rec.onerror = (e) => {
        setLastError(`STT error: ${e.error || 'unknown'}`);
        setIsListening(false);
      };
      rec.onend = () => {
        setIsListening(false);
        recognitionRef.current = null;
      };

      recognitionRef.current = rec;
      rec.start();
      return true;
    } catch (e) {
      setLastError(`STT exception: ${e.message || e}`);
      return false;
    }
  }, [RecognitionCtor]);

  const _startServerRecognition = useCallback(async () => {
    // Fallback: capture 5 seconds of audio via MediaRecorder, POST to
    // /api/voice/transcribe, then pipe the text through onTranscript.
    if (!navigator.mediaDevices?.getUserMedia) {
      setLastError('Microphone not supported in this browser');
      return false;
    }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const chunks = [];
      const recorder = new MediaRecorder(stream, { mimeType: 'audio/webm' });
      mediaRecorderRef.current = recorder;
      setIsListening(true);

      recorder.ondataavailable = (e) => {
        if (e.data && e.data.size > 0) chunks.push(e.data);
      };
      recorder.onstop = async () => {
        setIsListening(false);
        stream.getTracks().forEach((t) => t.stop());
        if (chunks.length === 0) return;
        const blob = new Blob(chunks, { type: 'audio/webm' });
        try {
          const res = await fetch('/api/voice/transcribe', {
            method: 'POST',
            headers: { 'Content-Type': 'audio/webm' },
            body: blob,
          });
          if (!res.ok) {
            setLastError(`Server STT failed: HTTP ${res.status}`);
            return;
          }
          const data = await res.json();
          const text = (data.text || '').trim();
          if (text && onTranscriptRef.current) {
            onTranscriptRef.current(text);
          }
        } catch (e) {
          setLastError(`Upload failed: ${e.message || e}`);
        }
      };

      recorder.start();
      return true;
    } catch (e) {
      setLastError(`Mic access denied: ${e.message || e}`);
      setIsListening(false);
      return false;
    }
  }, []);

  const startListening = useCallback(async () => {
    setLastError(null);
    if (isListening) return;
    if (browserSttSupported) {
      if (_startBrowserRecognition()) return;
    }
    if (serverCaps.stt_server_available) {
      await _startServerRecognition();
      return;
    }
    setLastError(
      browserSttSupported
        ? 'Microphone not available'
        : 'Voice input not supported in this browser. Try Edge or Chrome.',
    );
  }, [
    isListening,
    browserSttSupported,
    serverCaps.stt_server_available,
    _startBrowserRecognition,
    _startServerRecognition,
  ]);

  const stopListening = useCallback(() => {
    if (recognitionRef.current) {
      try { recognitionRef.current.stop(); } catch { /* noop */ }
      recognitionRef.current = null;
    }
    if (mediaRecorderRef.current && mediaRecorderRef.current.state !== 'inactive') {
      try { mediaRecorderRef.current.stop(); } catch { /* noop */ }
      mediaRecorderRef.current = null;
    }
    setIsListening(false);
  }, []);

  const toggleListening = useCallback(() => {
    if (isListening) {
      stopListening();
    } else {
      startListening();
    }
  }, [isListening, startListening, stopListening]);

  // Cleanup on unmount.
  useEffect(() => {
    return () => {
      stopListening();
      stopSpeaking();
    };
  }, [stopListening, stopSpeaking]);

  const anyVoiceSupported =
    browserSttSupported || browserTtsSupported ||
    serverCaps.stt_server_available || serverCaps.tts_server_available;

  return {
    // Capabilities
    anyVoiceSupported,
    browserSttSupported,
    browserTtsSupported,
    serverSttAvailable: serverCaps.stt_server_available,
    serverTtsAvailable: serverCaps.tts_server_available,

    // State
    isListening,
    isSpeaking,
    voiceMode,
    lastError,

    // Actions
    startListening,
    stopListening,
    toggleListening,
    speak,
    stopSpeaking,
    setVoiceMode,
    toggleVoiceMode,
  };
}
