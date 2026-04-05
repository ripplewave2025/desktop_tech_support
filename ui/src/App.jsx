import { useState, useCallback } from 'react';
import './index.css';
import { Shield, Minus, X, Pin, Settings, RotateCcw } from 'lucide-react';
import { ChatWidget } from './components/ChatWidget';
import { SettingsPanel } from './components/SettingsPanel';
import { PinMenu } from './components/PinMenu';
import { useTauri } from './hooks/useTauri';
import { useChat } from './hooks/useChat';
import { useVoice } from './hooks/useVoice';

function App() {
  const [showSettings, setShowSettings] = useState(false);
  const [showPinMenu, setShowPinMenu] = useState(false);
  const [isPinned, setIsPinned] = useState(false);

  const {
    isTauri, minimizeToTray, closeWindow, startDrag,
    pinToEdge, setAlwaysOnTop,
  } = useTauri();

  const {
    messages, isStreaming, currentTool, toolHistory,
    sendMessage, resetChat,
    confirmStep, cancelStep, submitUserInput,
  } = useChat();

  // Voice layer lives at the App level so the Settings panel and the
  // ChatWidget can share one source of truth for voice-mode, mic state,
  // and the speaker. The transcript callback feeds straight back into
  // sendMessage — speaking to Zora is indistinguishable from typing.
  const voice = useVoice({ onTranscript: sendMessage });

  const handlePin = useCallback((edge) => {
    if (edge === 'none') {
      setIsPinned(false);
      setAlwaysOnTop(false);
    } else {
      setIsPinned(true);
      setAlwaysOnTop(true);
      pinToEdge(edge);
    }
    setShowPinMenu(false);
  }, [pinToEdge, setAlwaysOnTop]);

  const status = isStreaming
    ? (currentTool ? 'Working...' : 'Thinking...')
    : 'Online';

  return (
    <div className={isTauri ? '' : 'zora-fullscreen'}>
      <div className="zora-widget">
        {/* ── Title Bar ── */}
        <div
          className="title-bar"
          onMouseDown={isTauri ? startDrag : undefined}
        >
          <div className="title-bar-left">
            <div className="title-bar-logo">
              <Shield />
            </div>
            <div>
              <div className="title-bar-title">Zora</div>
              <div className="title-bar-status">
                <span
                  className={`status-dot ${isStreaming ? 'busy' : 'online'}`}
                  style={{ display: 'inline-block', marginRight: 5, verticalAlign: 'middle' }}
                />
                {status}
              </div>
            </div>
          </div>

          <div className="title-bar-right">
            <button
              className="title-btn"
              onClick={resetChat}
              title="Reset conversation"
            >
              <RotateCcw />
            </button>
            <button
              className="title-btn"
              onClick={() => setShowSettings(true)}
              title="Settings"
            >
              <Settings />
            </button>
            <button
              className={`title-btn ${isPinned ? 'pin-active' : ''}`}
              onClick={() => setShowPinMenu(!showPinMenu)}
              title="Pin to edge"
            >
              <Pin />
            </button>
            {isTauri && (
              <>
                <button className="title-btn" onClick={minimizeToTray} title="Minimize">
                  <Minus />
                </button>
                <button className="title-btn close" onClick={closeWindow} title="Close">
                  <X />
                </button>
              </>
            )}
          </div>
        </div>

        {/* ── Pin Menu Dropdown ── */}
        {showPinMenu && (
          <PinMenu
            onSelect={handlePin}
            onClose={() => setShowPinMenu(false)}
          />
        )}

        {/* ── Chat Content ── */}
        <ChatWidget
          messages={messages}
          isStreaming={isStreaming}
          currentTool={currentTool}
          toolHistory={toolHistory}
          onSend={sendMessage}
          onQuickAction={sendMessage}
          onConfirmStep={confirmStep}
          onCancelStep={cancelStep}
          onSubmitUserInput={submitUserInput}
          voice={voice}
        />

        {/* ── Settings Modal ── */}
        {showSettings && (
          <SettingsPanel
            isOpen={showSettings}
            onClose={() => setShowSettings(false)}
            onRunRecipe={(text) => {
              sendMessage(text);
              setShowSettings(false);
            }}
            voice={voice}
          />
        )}
      </div>
    </div>
  );
}

export default App;
