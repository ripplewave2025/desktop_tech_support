import { useState, useEffect, useCallback } from 'react';
import {
  X, Home, Zap, Lock, Volume2, Mic, Download, RefreshCw,
  AlertTriangle, FileText, ChevronRight, ChevronDown, Trash2,
} from 'lucide-react';

export function SettingsPanel({ isOpen, onClose, onRunRecipe, voice }) {
  const [provider, setProvider] = useState('ollama');
  const [model, setModel] = useState('');
  const [apiKey, setApiKey] = useState('');
  const [baseUrl, setBaseUrl] = useState('');
  const [expertMode, setExpertMode] = useState(false);
  const [saving, setSaving] = useState(false);
  const [status, setStatus] = useState('');
  const [smartHome, setSmartHome] = useState(null);
  const [smartHomeError, setSmartHomeError] = useState('');
  // Update state
  const [updateInfo, setUpdateInfo] = useState(null);
  const [updateState, setUpdateState] = useState('idle'); // idle|checking|downloading|ready|installing|error
  const [updateError, setUpdateError] = useState('');
  // Diagnostics state
  const [diagOpen, setDiagOpen] = useState(false);  // accordion: hidden until clicked
  const [crashes, setCrashes] = useState([]);
  const [bsods, setBsods] = useState(null);
  const [eventLog, setEventLog] = useState(null);
  const [diagLoading, setDiagLoading] = useState(false);
  const [diagError, setDiagError] = useState('');

  useEffect(() => {
    if (!isOpen) return;
    fetch('/api/settings')
      .then((r) => r.json())
      .then((data) => {
        setProvider(data.provider || 'ollama');
        setModel(data.model || '');
        setBaseUrl(data.base_url || '');
        setExpertMode(!!data.expert_mode);
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
        body: JSON.stringify({
          provider,
          model,
          api_key: apiKey || undefined,
          base_url: baseUrl || undefined,
          expert_mode: expertMode,
        }),
      });
      const data = await res.json();
      setStatus(data.status === 'updated' ? `Active: ${data.active_provider}` : `Error: ${data.detail}`);
    } catch {
      setStatus('Failed to save');
    }
    setSaving(false);
  };

  // Toggle expert mode independently of the Save button — the user expects
  // the badge in the header to flip immediately. We POST the change right
  // away so the agent rebuilds with the new system prompt before the next
  // chat turn.
  const handleExpertToggle = async (next) => {
    setExpertMode(next);
    try {
      await fetch('/api/settings', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ expert_mode: next }),
      });
    } catch {
      // Roll back the local state if the save failed so the UI doesn't
      // lie about the persisted setting.
      setExpertMode(!next);
    }
  };

  // ── Auto-update flow ───────────────────────────────────────────
  // Check on settings open so the user sees pending updates without
  // having to click. Two-step apply (download → install) so the user
  // can see what's about to run before it runs.

  useEffect(() => {
    if (!isOpen) return;
    setUpdateState('checking');
    setUpdateError('');
    fetch('/api/update/check')
      .then((r) => r.json())
      .then((data) => {
        setUpdateInfo(data);
        if (data.error) {
          setUpdateState('error');
          setUpdateError(data.error);
        } else {
          setUpdateState('idle');
        }
      })
      .catch((e) => {
        setUpdateState('error');
        setUpdateError(e.message || 'Network error');
      });
  }, [isOpen]);

  const handleDownload = async () => {
    setUpdateState('downloading');
    setUpdateError('');
    try {
      const res = await fetch('/api/update/download', { method: 'POST' });
      const data = await res.json();
      if (!res.ok) {
        throw new Error(data.detail || `HTTP ${res.status}`);
      }
      setUpdateInfo((prev) => ({ ...(prev || {}), ...data }));
      setUpdateState('ready');
    } catch (e) {
      setUpdateState('error');
      setUpdateError(e.message);
    }
  };

  const handleInstall = async () => {
    setUpdateState('installing');
    try {
      const res = await fetch('/api/update/install', { method: 'POST' });
      const data = await res.json();
      if (!res.ok) {
        throw new Error(data.detail || `HTTP ${res.status}`);
      }
      // Backend will exit within ~2 seconds; show a closing message.
      setUpdateError('Installer launched. Zora will close and reopen automatically.');
    } catch (e) {
      setUpdateState('error');
      setUpdateError(e.message);
    }
  };

  const formatBytes = (n) => {
    if (!n) return '';
    const mb = n / (1024 * 1024);
    return `${mb.toFixed(1)} MB`;
  };

  // ── Diagnostics (lazy: only fetch when the user expands the panel) ──
  // We do three parallel reads so the panel hydrates in one round trip
  // instead of waterfalling.
  const loadDiagnostics = useCallback(async () => {
    setDiagLoading(true);
    setDiagError('');
    try {
      const [crashRes, bsodRes, logRes] = await Promise.all([
        fetch('/api/crashes').then((r) => r.json()).catch(() => ({ crashes: [] })),
        fetch('/api/diagnostics/bsod?limit=5').then((r) => r.json()).catch(() => ({ events: [], supported: false })),
        fetch('/api/diagnostics/event_log?hours=24').then((r) => r.json()).catch(() => ({ groups: [], supported: false })),
      ]);
      setCrashes(crashRes.crashes || []);
      setBsods(bsodRes);
      setEventLog(logRes);
    } catch (e) {
      setDiagError(e.message || 'Failed to load diagnostics.');
    } finally {
      setDiagLoading(false);
    }
  }, []);

  const toggleDiagnostics = () => {
    const next = !diagOpen;
    setDiagOpen(next);
    if (next && crashes.length === 0 && !bsods && !eventLog) {
      loadDiagnostics();
    }
  };

  const handleDeleteCrash = async (filename) => {
    try {
      await fetch(`/api/crashes/${encodeURIComponent(filename)}`, { method: 'DELETE' });
      setCrashes((prev) => prev.filter((c) => c.filename !== filename));
    } catch {
      /* ignore — UI will reflect on next reload */
    }
  };

  const handleCrashBundle = (filename) => {
    // Trigger a download by navigating to the endpoint. The browser handles
    // the Content-Disposition header from FileResponse.
    fetch(`/api/crashes/${encodeURIComponent(filename)}/bundle`, { method: 'POST' })
      .then((r) => (r.ok ? r.blob() : Promise.reject(new Error(`HTTP ${r.status}`))))
      .then((blob) => {
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `zora-support-bundle-${filename.replace(/\.json$/, '')}.zip`;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);
      })
      .catch((e) => setDiagError(e.message));
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

          {/* ── Updates ───────────────────────────────────────────── */}
          <div className="settings-section-title">Updates</div>
          <div style={{ fontSize: 11, color: '#94a3b8', marginBottom: 8 }}>
            {updateInfo && updateInfo.current_version && (
              <>Current: <strong>v{updateInfo.current_version}</strong></>
            )}
          </div>
          {updateState === 'checking' && (
            <div style={{ fontSize: 11, color: '#64748b' }}>
              <RefreshCw size={11} style={{ verticalAlign: 'middle', marginRight: 4 }} />
              Checking for updates…
            </div>
          )}
          {updateInfo && updateInfo.available && updateState === 'idle' && (
            <div style={{ fontSize: 11 }}>
              <div style={{ color: '#10b981', marginBottom: 4 }}>
                Update available: <strong>v{updateInfo.latest_version}</strong>
                {updateInfo.asset_size_bytes
                  ? <> &middot; {formatBytes(updateInfo.asset_size_bytes)}</>
                  : null}
              </div>
              {updateInfo.published_at && (
                <div style={{ color: '#94a3b8', marginBottom: 6 }}>
                  Released {updateInfo.published_at.slice(0, 10)}
                </div>
              )}
              <button className="smart-home-setup-btn" onClick={handleDownload}>
                <Download size={12} style={{ verticalAlign: 'middle', marginRight: 4 }} />
                Download installer
              </button>
            </div>
          )}
          {updateState === 'downloading' && (
            <div style={{ fontSize: 11, color: '#64748b' }}>
              Downloading installer…
            </div>
          )}
          {updateState === 'ready' && (
            <div style={{ fontSize: 11 }}>
              <div style={{ color: '#10b981', marginBottom: 4 }}>
                Installer ready ({formatBytes(updateInfo?.size_bytes)})
              </div>
              {updateInfo?.sha256 && (
                <div style={{ color: '#94a3b8', fontFamily: 'monospace',
                              fontSize: 10, wordBreak: 'break-all', marginBottom: 6 }}>
                  SHA-256: {updateInfo.sha256.slice(0, 32)}…
                  {updateInfo.sha256_match === true && ' ✓ verified'}
                  {updateInfo.sha256_match === false && ' ✗ MISMATCH'}
                </div>
              )}
              <button className="smart-home-setup-btn" onClick={handleInstall}>
                Restart and install
              </button>
            </div>
          )}
          {updateState === 'installing' && (
            <div style={{ fontSize: 11, color: '#f59e0b' }}>
              Closing Zora to apply the update…
            </div>
          )}
          {updateInfo && !updateInfo.available && updateState === 'idle' && !updateError && (
            <div style={{ fontSize: 11, color: '#64748b' }}>
              You're up to date.
            </div>
          )}
          {updateError && (
            <div style={{ fontSize: 11, color: '#f59e0b', marginTop: 4 }}>
              {updateError}
            </div>
          )}

          {/* ── Diagnostics ───────────────────────────────────────── */}
          <div
            className="settings-section-title"
            style={{ cursor: 'pointer', userSelect: 'none' }}
            onClick={toggleDiagnostics}
          >
            {diagOpen ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
            {' '}Diagnostics
            {crashes.length > 0 && (
              <span style={{ marginLeft: 6, color: '#f59e0b', fontSize: 11 }}>
                ({crashes.length} crash{crashes.length === 1 ? '' : 'es'})
              </span>
            )}
          </div>
          {diagOpen && (
            <div style={{ fontSize: 11 }}>
              {diagLoading && (
                <div style={{ color: '#64748b' }}>
                  <RefreshCw size={11} style={{ verticalAlign: 'middle', marginRight: 4 }} />
                  Loading diagnostics…
                </div>
              )}
              {diagError && (
                <div style={{ color: '#f59e0b', marginBottom: 6 }}>{diagError}</div>
              )}

              {/* Recent crashes */}
              {!diagLoading && crashes.length === 0 && (
                <div style={{ color: '#64748b', marginBottom: 8 }}>
                  No crash reports. Zora is running clean.
                </div>
              )}
              {!diagLoading && crashes.length > 0 && (
                <div style={{ marginBottom: 8 }}>
                  <div style={{ fontWeight: 600, marginBottom: 4 }}>
                    <AlertTriangle size={11} style={{ verticalAlign: 'middle', marginRight: 4 }} />
                    Recent crashes
                  </div>
                  {crashes.slice(0, 5).map((c) => (
                    <div key={c.filename}
                         style={{ padding: '4px 0', borderBottom: '1px solid rgba(255,255,255,0.06)' }}>
                      <div style={{ color: '#e2e8f0' }}>
                        <strong>{c.exception_type}</strong>
                        <span style={{ color: '#94a3b8', marginLeft: 6 }}>
                          {c.timestamp?.slice(0, 19)?.replace('T', ' ')}
                        </span>
                      </div>
                      {c.exception_message && (
                        <div style={{ color: '#94a3b8', marginBottom: 4,
                                      whiteSpace: 'nowrap', overflow: 'hidden',
                                      textOverflow: 'ellipsis' }}>
                          {c.exception_message}
                        </div>
                      )}
                      <div style={{ display: 'flex', gap: 6 }}>
                        <button
                          className="smart-home-setup-btn"
                          style={{ flex: '0 0 auto', padding: '3px 8px' }}
                          onClick={() => handleCrashBundle(c.filename)}
                          title="Download a ZIP of this crash + recent logs to send to support"
                        >
                          <FileText size={11} style={{ verticalAlign: 'middle', marginRight: 3 }} />
                          Bundle
                        </button>
                        <button
                          className="smart-home-setup-btn"
                          style={{ flex: '0 0 auto', padding: '3px 8px' }}
                          onClick={() => handleDeleteCrash(c.filename)}
                          title="Delete this crash report"
                        >
                          <Trash2 size={11} style={{ verticalAlign: 'middle' }} />
                        </button>
                      </div>
                    </div>
                  ))}
                </div>
              )}

              {/* Recent BSODs */}
              {!diagLoading && bsods && bsods.supported && (
                <div style={{ marginBottom: 8 }}>
                  <div style={{ fontWeight: 600, marginBottom: 4 }}>Blue screens</div>
                  {bsods.events && bsods.events.length > 0 ? (
                    bsods.events.slice(0, 3).map((ev, i) => (
                      <div key={i} style={{ padding: '4px 0',
                                            borderBottom: '1px solid rgba(255,255,255,0.06)' }}>
                        <div style={{ color: '#e2e8f0' }}>
                          <strong>{ev.bugcheck_code_hex}</strong> {ev.name}
                          <span style={{ color: '#94a3b8', marginLeft: 6 }}>
                            {ev.timestamp?.slice(0, 19)?.replace('T', ' ')}
                          </span>
                        </div>
                        {ev.common_causes && ev.common_causes.length > 0 && (
                          <div style={{ color: '#94a3b8' }}>
                            {ev.common_causes[0]}
                          </div>
                        )}
                      </div>
                    ))
                  ) : (
                    <div style={{ color: '#64748b' }}>No blue screens in recent history.</div>
                  )}
                </div>
              )}
              {!diagLoading && bsods && !bsods.supported && (
                <div style={{ color: '#64748b', marginBottom: 8 }}>
                  Blue screen scan unavailable: {bsods.error || 'not supported on this platform'}
                </div>
              )}

              {/* Event log triage */}
              {!diagLoading && eventLog && eventLog.supported && (
                <div style={{ marginBottom: 8 }}>
                  <div style={{ fontWeight: 600, marginBottom: 4 }}>
                    System log (last 24h)
                  </div>
                  {eventLog.groups && eventLog.groups.length > 0 ? (
                    eventLog.groups.slice(0, 5).map((g, i) => (
                      <div key={i} style={{ padding: '4px 0',
                                            borderBottom: '1px solid rgba(255,255,255,0.06)' }}>
                        <div style={{ color: '#e2e8f0' }}>
                          <strong>{g.provider}</strong> (id {g.event_id})
                          <span style={{ marginLeft: 6, color: '#94a3b8' }}>
                            ×{g.count}
                          </span>
                        </div>
                        {g.explanation && (
                          <div style={{ color: '#94a3b8' }}>{g.explanation}</div>
                        )}
                      </div>
                    ))
                  ) : (
                    <div style={{ color: '#64748b' }}>
                      No critical or error events in the last 24 hours.
                    </div>
                  )}
                </div>
              )}
              {!diagLoading && eventLog && !eventLog.supported && (
                <div style={{ color: '#64748b', marginBottom: 8 }}>
                  Event log scan unavailable: {eventLog.error || 'not supported on this platform'}
                </div>
              )}

              <button
                className="smart-home-setup-btn"
                onClick={loadDiagnostics}
                style={{ marginTop: 4 }}
              >
                <RefreshCw size={11} style={{ verticalAlign: 'middle', marginRight: 4 }} />
                Refresh
              </button>
            </div>
          )}

          {/* ── Mode (Novice / Expert) ────────────────────────────── */}
          <div className="settings-section-title">Mode</div>
          <div className="voice-toggle-row">
            <div className="voice-toggle-label">
              <span>
                ⚡ Power user mode
              </span>
              <span className="desc">
                {expertMode
                  ? 'Technical terms, raw output, full tool catalog. Safety gates still apply.'
                  : 'Plain English, step-by-step, lots of confirmations. Best for getting started.'}
              </span>
            </div>
            <button
              type="button"
              className={`voice-toggle-switch ${expertMode ? 'on' : ''}`}
              onClick={() => handleExpertToggle(!expertMode)}
              title={expertMode ? 'Switch to novice mode' : 'Switch to power-user mode'}
              aria-label="Toggle power-user mode"
              aria-pressed={expertMode}
            />
          </div>

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
