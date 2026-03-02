import { useState, useEffect, useRef } from 'react';
import { Send, Terminal, Zap, ChevronRight, Shield } from 'lucide-react';

const QUICK_ACTIONS = [
    { label: '👁️ What\'s on screen?', message: 'Look at my screen and tell me what you see' },
    { label: '🔊 Fix Audio', message: 'My audio is not working' },
    { label: '🌐 Check WiFi', message: 'My internet is not working' },
    { label: '🖨️ Fix Printer', message: 'My printer is not printing' },
    { label: '💻 System Health', message: 'Check my system health' },
    { label: '🧹 Cleanup', message: 'Clean up temp files and free space' },
];

function WelcomeState({ onQuickAction }) {
    return (
        <div className="welcome-container">
            <div className="welcome-icon">
                <Shield />
            </div>
            <div className="welcome-title">Hey there! 👋</div>
            <div className="welcome-subtitle">
                I'm Zora, your AI tech support companion. Tell me what's going on with your PC.
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

function ToolDetail({ name, result }) {
    const [expanded, setExpanded] = useState(false);
    const summary = typeof result === 'string'
        ? result.slice(0, 80)
        : JSON.stringify(result).slice(0, 80);

    return (
        <div className="tool-detail">
            <button
                className={`tool-detail-toggle ${expanded ? 'expanded' : ''}`}
                onClick={() => setExpanded(!expanded)}
            >
                <ChevronRight />
                <span>Tool: {name}</span>
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
    toolHistory,
    onSend,
    onQuickAction,
}) {
    const [input, setInput] = useState('');
    const scrollRef = useRef(null);
    const inputRef = useRef(null);

    // Auto-scroll on new messages
    useEffect(() => {
        if (scrollRef.current) {
            scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
        }
    }, [messages, isStreaming, currentTool]);

    const handleSubmit = (e) => {
        e?.preventDefault();
        if (!input.trim() || isStreaming) return;
        const msg = input.trim();
        setInput('');
        onSend(msg);
    };

    // Only welcome message — show welcome state
    const isWelcome = messages.length <= 1 && messages[0]?.role === 'zora';

    return (
        <>
            {/* Message List */}
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

                                    {/* Action chip */}
                                    {m.action && (
                                        <button
                                            className="action-chip"
                                            onClick={() => onQuickAction(`Run ${m.action} diagnostic`)}
                                        >
                                            <Zap />
                                            Run '{m.action}' diagnostic
                                        </button>
                                    )}

                                    {/* Tool details for this message */}
                                    {m.tools && m.tools.length > 0 && m.tools.map((t, ti) => (
                                        <ToolDetail key={ti} name={t.name} result={t.result} />
                                    ))}
                                </div>
                            </div>
                        );
                    })
                )}

                {/* Typing dots when streaming with no current text */}
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

            {/* Input Bar */}
            <div className="input-bar">
                <form className="input-form" onSubmit={handleSubmit}>
                    <input
                        ref={inputRef}
                        type="text"
                        className="input-field"
                        value={input}
                        onChange={(e) => setInput(e.target.value)}
                        placeholder="What's going on with your PC?"
                        disabled={isStreaming}
                    />
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
