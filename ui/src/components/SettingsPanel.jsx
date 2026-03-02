import { useState, useEffect } from 'react';
import { X } from 'lucide-react';

export function SettingsPanel({ isOpen, onClose }) {
  const [provider, setProvider] = useState('ollama');
  const [model, setModel] = useState('');
  const [apiKey, setApiKey] = useState('');
  const [baseUrl, setBaseUrl] = useState('');
  const [saving, setSaving] = useState(false);
  const [status, setStatus] = useState('');

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

  if (!isOpen) return null;

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
          <div className="settings-group">
            <label>AI Provider</label>
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
        </div>
      </div>
    </div>
  );
}
