import { useState, useEffect, useRef, useCallback } from 'react';
import {
  Send, Terminal, Zap, ChevronRight, Shield, AlertTriangle,
  Check, X as XIcon, Bell, Mic, MicOff, Volume2, VolumeX,
} from 'lucide-react';

const QUICK_ACTIONS = [
  { label: 'What is on screen?', message: 'Look at my screen and tell me what you see' },
  { label: 'Enable dark mode', message: 'Change this to dark mode' },
  { label: 'Find my PDF', message: 'Where is my PDF file?' },
  { label: 'Run OEM check', message: 'Run the OEM hardware check' },
  { label: 'Check WiFi', message: 'My internet is not working' },
  { label: 'Prepare support case', message: 'Prepare a support ticket and track it' },
];

function WelcomeState({ onQuickAction }) {
  return (
    <div className="welcome-container">
      <div className="welcome-icon">
        <Shield />
      </div>
      <div className="welcome-title">Hi there</div>
      <div className="welcome-subtitle">
        I'm Zora, your Windows support assistant. Tell me what you need and I will route it to the right helper.
      </div>
      <div className="welcome-chips">
        {QUICK_ACTIONS.map((a) => (
          <button
            key={a.label}
            className="welcome-chip"
            onClick={() => onQuickAction(a.message)}
          >
            {a.label}
          </button>
        ))}
      </div>
    </div>
  );
}

function ConsentCard({ message, onConfirm, onCancel, disabled }) {
  const { taskId, stepId, title, reason, status } = message;
  const isDone = status === 'approved' || status === 'cancelled';
  return (
    <div className="message-row zora">
      <div className="message-bubble zora consent-card">
        <div className="zora-label">
          <AlertTriangle />
          <span>Confirm before I continue</span>
        </div>
        <div className="consent-title">{title}</div>
        {reason && <div className="consent-reason">{reason}</div>}
        {status === 'approved' ? (
          <div className="consent-footer approved">Confirmed — continuing…</div>
        ) : status === 'cancelled' ? (
          <div className="consent-footer cancelled">Cancelled.</div>
        ) : (
          <div className="consent-actions">
            <button
              type="button"
              className="consent-btn confirm"
              disabled={disabled || isDone}
              onClick={() => onConfirm(taskId, stepId)}
            >
              <Check />
              <span>Confirm</span>
            </button>
            <button
              type="button"
              className="consent-btn cancel"
              disabled={disabled || isDone}
              onClick={() => onCancel(taskId, stepId)}
            >
              <XIcon />
              <span>Cancel</span>
            </button>
          </div>
        )}
      </div>
    </div>
  );
}

function UserInputCard({ message, onSubmit, disabled }) {
  const { taskId, stepId, fieldName, prompt, status, value, choices, kind } = message;
  const isSelect = kind === 'select_from_list' && Array.isArray(choices) && choices.length > 0;
  const [draft, setDraft] = useState('');
  const [selected, setSelected] = useState(isSelect ? String(choices[0]?.value ?? '') : '');
  const isDone = status === 'submitted';

  const handleSubmit = (e) => {
    e?.preventDefault();
    if (disabled || isDone) return;
    if (isSelect) {
      if (!selected) return;
      // Find the choice we picked so onSubmit gets the real value shape
      // (which might be a dict for complex options).
      const match = choices.find((c) => String(c.value) === String(selected));
      onSubmit(taskId, stepId, match ? match.value : selected);
      return;
    }
    if (!draft.trim()) return;
    onSubmit(taskId, stepId, draft.trim());
  };

  return (
    <div className="message-row zora">
      <div className="message-bubble zora consent-card">
        <div className="zora-label">
          <Terminal />
          <span>{isSelect ? 'Pick one' : 'I need one detail'}</span>
        </div>
        <div className="consent-title">{prompt}</div>
        {fieldName && <div className="consent-reason">Field: {fieldName}</div>}
        {isDone ? (
          <div className="consent-footer approved">
            Thanks — continuing with “{typeof value === 'string' ? value : JSON.stringify(value)}”…
          </div>
        ) : isSelect ? (
          <form className="user-input-form select-list" onSubmit={handleSubmit}>
            <div className="select-list-options">
              {choices.map((c, idx) => {
                const val = String(c.value ?? idx);
                return (
                  <label key={idx} className="select-list-option">
                    <input
                      type="radio"
                      name={`select-${stepId}`}
                      value={val}
                      checked={selected === val}
                      onChange={() => setSelected(val)}
                      disabled={disabled}
                    />
                    <span>{c.label}</span>
                  </label>
                );
              })}
            </div>
            <button
              type="submit"
              className="consent-btn confirm"
              disabled={disabled || !selected}
            >
              <Send />
              <span>Use this</span>
            </button>
          </form>
        ) : (
          <form className="user-input-form" onSubmit={handleSubmit}>
            <input
              type="text"
              className="input-field"
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              placeholder={fieldName || 'Type your answer…'}
              disabled={disabled}
              autoFocus
            />
            <button
              type="submit"
              className="consent-btn confirm"
              disabled={disabled || !draft.trim()}
            >
              <Send />
              <span>Send</span>
            </button>
          </form>
        )}
      </div>
    </div>
  );
}

function FollowUpsPill({ due, onResolve, onOpen }) {
  if (!due || due.length === 0) return null;
  // Flatten so we can count individual follow-ups, not just cases.
  const count = due.reduce((acc, entry) => acc + (entry.due_follow_ups?.length || 0), 0);
  return (
    <div className="followups-pill">
      <Bell />
      <span className="followups-label">
        {count} follow-up{count === 1 ? '' : 's'} due
      </span>
      <button
        type="button"
        className="followups-open-btn"
        onClick={() => onOpen && onOpen(due)}
      >
        Review
      </button>
    </div>
  );
}

function ToolDetail({ name, result }) {
  const [expanded, setExpanded] = useState(false);

  return (
    <div className="tool-detail">
      <button
        className={`tool-detail-toggle ${expanded ? 'expanded' : ''}`}
        onClick={() => setExpanded(!expanded)}
      >
        <ChevronRight />
        <span>Step: {name}</span>
      </button>
      {expanded && (
        <div className="tool-detail-content">
          {typeof result === 'string' ? result : JSON.stringify(result, null, 2)}
        </div>
      )}
    </div>
  );
}

export function ChatWidget({
  messages,
  isStreaming,
  currentTool,
  onSend,
  onQuickAction,
  onConfirmStep,
  onCancelStep,
  onSubmitUserInput,
  voice,
}) {
  const [input, setInput] = useState('');
  const [dueFollowUps, setDueFollowUps] = useState([]);
  const scrollRef = useRef(null);
  const inputRef = useRef(null);
  const lastSpokenIndexRef = useRef(-1);

  // Voice state is owned by App and passed down so the Settings panel
  // can share the same voice-mode toggle. Fall back to a no-op shape if
  // the prop is missing (e.g. in isolated component tests).
  const {
    anyVoiceSupported = false,
    browserSttSupported = false,
    isListening = false,
    isSpeaking = false,
    voiceMode = false,
    lastError: voiceError = null,
    toggleListening = () => {},
    speak = () => {},
    stopSpeaking = () => {},
    toggleVoiceMode = () => {},
  } = voice || {};

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [messages, isStreaming, currentTool]);

  // Auto-speak new Zora / consent / user_input messages when voice mode
  // is on. We track the last spoken index so each message only gets
  // spoken once, even if the component re-renders.
  useEffect(() => {
    if (!voiceMode) return;
    if (isStreaming) return; // wait until streaming completes
    for (let i = lastSpokenIndexRef.current + 1; i < messages.length; i++) {
      const m = messages[i];
      if (!m) continue;
      let text = null;
      if (m.role === 'zora' && typeof m.text === 'string') {
        text = m.text;
      } else if (m.role === 'consent' && m.title) {
        text = `I need your permission. ${m.title}. ${m.reason || ''}`;
      } else if (m.role === 'user_input' && m.prompt) {
        text = m.prompt;
      }
      if (text) speak(text);
      lastSpokenIndexRef.current = i;
    }
  }, [messages, voiceMode, isStreaming, speak]);

  // Poll /api/followups/due on mount and every 5 minutes. Quiet failures
  // if the endpoint is unavailable so the main UI still renders.
  useEffect(() => {
    let cancelled = false;
    const fetchDue = async () => {
      try {
        const res = await fetch('/api/followups/due');
        if (!res.ok) return;
        const json = await res.json();
        if (!cancelled) setDueFollowUps(json.due || []);
      } catch (_) {
        // endpoint may not be available during degraded startup
      }
    };
    fetchDue();
    const id = setInterval(fetchDue, 5 * 60 * 1000);
    return () => {
      cancelled = true;
      clearInterval(id);
    };
  }, []);

  const handleOpenFollowUps = useCallback((due) => {
    if (!due || due.length === 0) return;
    // Drop the user into the chat flow that summarizes the oldest case.
    const first = due[0];
    const caseId = first.case?.case_id || '';
    const summary = first.case?.issue_summary || '';
    onSend(`Check in on case ${caseId} — ${summary}`);
  }, [onSend]);

  const handleSubmit = (e) => {
    e?.preventDefault();
    if (!input.trim() || isStreaming) return;
    const msg = input.trim();
    setInput('');
    onSend(msg);
  };

  const isWelcome = messages.length <= 1 && messages[0]?.role === 'zora';

  const handleMicClick = () => {
    if (isSpeaking) {
      stopSpeaking();
      return;
    }
    toggleListening();
  };

  return (
    <>
      <FollowUpsPill
        due={dueFollowUps}
        onOpen={handleOpenFollowUps}
      />
      {anyVoiceSupported && (
        <div className="voice-bar">
          <button
            type="button"
            className={`voice-pill ${voiceMode ? 'active' : ''}`}
            onClick={toggleVoiceMode}
            title={voiceMode ? 'Voice mode on — Zora reads replies aloud' : 'Turn on voice mode'}
          >
            {voiceMode ? <Volume2 /> : <VolumeX />}
            <span>{voiceMode ? 'Voice on' : 'Voice off'}</span>
          </button>
          {isSpeaking && (
            <button
              type="button"
              className="voice-pill speaking"
              onClick={stopSpeaking}
              title="Stop speaking"
            >
              <VolumeX />
              <span>Stop</span>
            </button>
          )}
          {voiceError && !isListening && (
            <span className="voice-error" title={voiceError}>
              {voiceError.length > 40 ? voiceError.slice(0, 40) + '…' : voiceError}
            </span>
          )}
        </div>
      )}
      <div ref={scrollRef} className="message-list">
        {isWelcome ? (
          <WelcomeState onQuickAction={onQuickAction} />
        ) : (
          messages.map((m, i) => {
            if (m.role === 'tool_indicator') {
              return (
                <div key={i} className="message-row zora">
                  <div className="thinking-indicator">
                    <div className="thinking-spinner" />
                    <div className="thinking-text">
                      <span className="action-name">{m.text}</span>
                    </div>
                  </div>
                </div>
              );
            }

            if (m.role === 'consent') {
              return (
                <ConsentCard
                  key={i}
                  message={m}
                  onConfirm={onConfirmStep}
                  onCancel={onCancelStep}
                  disabled={isStreaming}
                />
              );
            }

            if (m.role === 'user_input') {
              return (
                <UserInputCard
                  key={i}
                  message={m}
                  onSubmit={onSubmitUserInput}
                  disabled={isStreaming}
                />
              );
            }

            return (
              <div key={i} className={`message-row ${m.role === 'user' ? 'user' : 'zora'}`}>
                <div className={`message-bubble ${m.role === 'user' ? 'user' : m.role === 'system' ? 'system' : 'zora'}`}>
                  {m.role === 'zora' && (
                    <div className="zora-label">
                      <Terminal />
                      <span>Zora</span>
                    </div>
                  )}
                  <div>{m.text}</div>

                  {m.action && (
                    <button
                      className="action-chip"
                      onClick={() => onQuickAction(`Run ${m.action} workflow`)}
                    >
                      <Zap />
                      Run '{m.action}' workflow
                    </button>
                  )}

                  {m.tools && m.tools.length > 0 && m.tools.map((t, ti) => (
                    <ToolDetail key={ti} name={t.name} result={t.result} />
                  ))}
                </div>
              </div>
            );
          })
        )}

        {isStreaming && !currentTool && messages[messages.length - 1]?.role !== 'zora' && (
          <div className="message-row zora">
            <div className="typing-dots">
              <div className="typing-dot" />
              <div className="typing-dot" />
              <div className="typing-dot" />
            </div>
          </div>
        )}
      </div>

      <div className="input-bar">
        <form className="input-form" onSubmit={handleSubmit}>
          <input
            ref={inputRef}
            type="text"
            className="input-field"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder={isListening ? 'Listening…' : 'Tell Zora what you need help with'}
            disabled={isStreaming || isListening}
          />
          {anyVoiceSupported && (
            <button
              type="button"
              className={`mic-btn ${isListening ? 'listening' : ''} ${isSpeaking ? 'speaking' : ''}`}
              onClick={handleMicClick}
              disabled={isStreaming && !isSpeaking}
              title={
                isSpeaking ? 'Tap to stop Zora talking'
                  : isListening ? 'Tap to stop listening'
                    : browserSttSupported ? 'Tap and speak'
                      : 'Tap to record (server fallback)'
              }
            >
              {isListening ? <MicOff /> : <Mic />}
            </button>
          )}
          <button
            type="submit"
            className="send-btn"
            disabled={!input.trim() || isStreaming}
          >
            <Send />
          </button>
        </form>
      </div>
    </>
  );
}

