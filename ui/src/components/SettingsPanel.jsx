import { useState, useEffect, useCallback } from 'react';
import { X, Home, Zap, Lock, Volume2, Mic } from 'lucide-react';

export function SettingsPanel({ isOpen, onClose, onRunRecipe, voice }) {
  const [provider, setProvider] = useState('ollama');
  const [model, setModel] = useState('');
  const [apiKey, setApiKey] = useState('');
  const [baseUrl, setBaseUrl] = useState('');
  const [saving, setSaving] = useState(false);
  const [status, setStatus] = useState('');
  const [smartHome, setSmartHome] = useState(null);
  const [smartHomeError, setSmartHomeError] = useState('');

  useEffect(() => {
    if (!isOpen) return;
    fetch('/api/settings')
      .then((r) => r.json())
      .then((data) => {
        setProvider(data.provider || 'ollama');
        setModel(data.model || '');
        setBaseUrl(data.base_url || '');
        setStatus(data.active_provider !== 'none' ? `Active: ${data.active_provider}` : 'Not connected');
      })
      .catch(() => setStatus('Backend not running'));
  }, [isOpen]);

  // Smart-home status is refetched every time the modal opens, so the
  // user always sees the current credential snapshot (redacted).
  const loadSmartHome = useCallback(() => {
    fetch('/api/smart_home/status')
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(`HTTP ${r.status}`))))
      .then((data) => {
        setSmartHome(data);
        setSmartHomeError('');
      })
      .catch((e) => {
        setSmartHome(null);
        setSmartHomeError(e.message || 'Smart-home status unavailable');
      });
  }, []);

  useEffect(() => {
    if (!isOpen) return;
    loadSmartHome();
  }, [isOpen, loadSmartHome]);

  const handleSave = async () => {
    setSaving(true);
    try {
      const res = await fetch('/api/settings', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ provider, model, api_key: apiKey || undefined, base_url: baseUrl || undefined }),
      });
      const data = await res.json();
      setStatus(data.status === 'updated' ? `Active: ${data.active_provider}` : `Error: ${data.detail}`);
    } catch {
      setStatus('Failed to save');
    }
    setSaving(false);
  };

  const runRecipe = (text) => {
    if (typeof onRunRecipe === 'function') {
      onRunRecipe(text);
    }
  };

  if (!isOpen) return null;

  const hasHA = !!smartHome?.home_assistant?.configured;
  const hasHue = !!smartHome?.hue?.configured;
  const hasMqtt = !!smartHome?.mqtt?.configured;

  return (
    <div className="settings-overlay" onClick={onClose}>
      <div className="settings-panel" onClick={(e) => e.stopPropagation()}>
        <div className="settings-header">
          <h3>⚙️ Settings</h3>
          <button className="title-btn close" onClick={onClose}>
            <X />
          </button>
        </div>

        <div className="settings-body">
          {/* ── AI Provider ───────────────────────────────────────── */}
          <div className="settings-section-title">AI Provider</div>

          <div className="settings-group">
            <label>Provider</label>
            <select value={provider} onChange={(e) => setProvider(e.target.value)}>
              <option value="ollama">Ollama (Free, Local)</option>
              <option value="claude">Claude (Anthropic)</option>
              <option value="openai">OpenAI (GPT-4o)</option>
              <option value="grok">Grok (xAI)</option>
              <option value="groq">Groq (Fast)</option>
              <option value="custom">Custom (OpenAI-compatible)</option>
            </select>
          </div>

          <div className="settings-group">
            <label>Model</label>
            <input
              type="text"
              value={model}
              onChange={(e) => setModel(e.target.value)}
              placeholder={
                {
                  ollama: 'qwen2.5:7b',
                  claude: 'claude-sonnet-4-20250514',
                  openai: 'gpt-4o',
                  grok: 'grok-3-latest',
                  groq: 'llama-3.3-70b-versatile',
                  custom: 'model-name',
                }[provider] || 'model-name'
              }
            />
          </div>

          {provider !== 'ollama' && (
            <div className="settings-group">
              <label>API Key</label>
              <input
                type="password"
                value={apiKey}
                onChange={(e) => setApiKey(e.target.value)}
                placeholder={
                  provider === 'claude' ? 'sk-ant-...'
                    : provider === 'grok' ? 'xai-...'
                      : 'sk-...'
                }
              />
            </div>
          )}

          {['ollama', 'grok', 'groq', 'custom'].includes(provider) && (
            <div className="settings-group">
              <label>Base URL</label>
              <input
                type="text"
                value={baseUrl}
                onChange={(e) => setBaseUrl(e.target.value)}
                placeholder={
                  {
                    ollama: 'http://localhost:11434',
                    grok: 'https://api.x.ai/v1',
                    groq: 'https://api.groq.com/openai/v1',
                    custom: 'https://your-api.com/v1',
                  }[provider] || ''
                }
              />
            </div>
          )}

          <button
            className="settings-save-btn"
            onClick={handleSave}
            disabled={saving}
          >
            {saving ? 'Saving...' : 'Save & Connect'}
          </button>

          {status && (
            <div style={{
              fontSize: 11,
              color: status.startsWith('Active') ? '#10b981' : '#f59e0b',
              textAlign: 'center',
            }}>
              {status}
            </div>
          )}

          {/* ── Voice ─────────────────────────────────────────────── */}
          {voice?.anyVoiceSupported && (
            <>
              <div className="settings-section-title">Voice</div>
              <div className="voice-toggle-row">
                <div className="voice-toggle-label">
                  <span><Volume2 size={12} style={{ marginRight: 4, verticalAlign: 'middle' }} /> Read Zora's replies aloud</span>
                  <span className="desc">
                    {voice.browserSttSupported ? 'Mic + speaker ready' : 'Speaker ready (browser mic not detected)'}
                  </span>
                </div>
                <button
                  type="button"
                  className={`voice-toggle-switch ${voice.voiceMode ? 'on' : ''}`}
                  onClick={voice.toggleVoiceMode}
                  title="Toggle voice mode"
                  aria-label="Toggle voice mode"
                />
              </div>
              <button
                className="smart-home-setup-btn"
                style={{ flex: '1 1 100%' }}
                onClick={() => voice.speak('Hello. I am Zora. If you can hear me, voice mode is working.')}
              >
                <Mic size={12} style={{ marginRight: 4, verticalAlign: 'middle' }} />
                Test voice output
              </button>
            </>
          )}

          {/* ── Smart Home ────────────────────────────────────────── */}
          <div className="settings-section-title">Smart Home</div>

          {smartHomeError ? (
            <div style={{ fontSize: 11, color: '#f59e0b' }}>
              {smartHomeError}
            </div>
          ) : smartHome ? (
            <>
              <div className="smart-home-status">
                <div className="smart-home-status-row">
                  <span className="backend-label">
                    <Home size={13} /> Home Assistant
                  </span>
                  <span className={`backend-state ${hasHA ? 'connected' : 'disconnected'}`}>
                    {hasHA ? 'Connected' : 'Not set up'}
                  </span>
                </div>
                <div className="smart-home-status-row">
                  <span className="backend-label">
                    <Zap size={13} /> Philips Hue
                  </span>
                  <span className={`backend-state ${hasHue ? 'connected' : 'disconnected'}`}>
                    {hasHue ? 'Connected' : 'Not set up'}
                  </span>
                </div>
                <div className="smart-home-status-row">
                  <span className="backend-label">
                    <Lock size={13} /> MQTT
                  </span>
                  <span className={`backend-state ${hasMqtt ? 'connected' : 'disconnected'}`}>
                    {hasMqtt ? 'Connected' : 'Not set up'}
                  </span>
                </div>
              </div>

              <div className="smart-home-setup-buttons">
                <button
                  className="smart-home-setup-btn"
                  onClick={() => runRecipe('Connect my Home Assistant')}
                >
                  {hasHA ? 'Reconnect Home Assistant' : 'Set up Home Assistant'}
                </button>
                <button
                  className="smart-home-setup-btn"
                  onClick={() => runRecipe('Connect my Philips Hue bridge')}
                >
                  {hasHue ? 'Reconnect Hue' : 'Set up Hue'}
                </button>
                <button
                  className="smart-home-setup-btn"
                  onClick={() => runRecipe('Connect my MQTT broker')}
                >
                  {hasMqtt ? 'Reconnect MQTT' : 'Set up MQTT'}
                </button>
                {smartHome.any_configured && (
                  <button
                    className="smart-home-setup-btn"
                    onClick={() => runRecipe('List all my smart home devices')}
                  >
                    List my devices
                  </button>
                )}
              </div>
            </>
          ) : (
            <div style={{ fontSize: 11, color: '#64748b' }}>Checking smart-home status…</div>
          )}
        </div>
      </div>
    </div>
  );
}
