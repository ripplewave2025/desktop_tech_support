import { useState, useEffect, useRef } from 'react';
import { Terminal, MessageSquare, Zap, Shield, Activity, RotateCcw, Settings, Loader } from 'lucide-react';
import clsx from 'clsx';
import { twMerge } from 'tailwind-merge';
import { useChat } from '../hooks/useChat';

function cn(...inputs) {
  return twMerge(clsx(inputs));
}

export function ChatPanel({ onRunDiagnostic, onOpenSettings }) {
  const { messages, isStreaming, currentTool, sendMessage, resetChat } = useChat();
  const [input, setInput] = useState('');
  const scrollRef = useRef(null);

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [messages, isStreaming]);

  const handleSend = async (e) => {
    e?.preventDefault();
    if (!input.trim() || isStreaming) return;
    const msg = input.trim();
    setInput('');
    await sendMessage(msg);
  };

  return (
    <div className="flex flex-col h-full glass rounded-2xl overflow-hidden border-t border-l border-white/5 bg-[#12121c]/80 transition-all duration-300">
      {/* Header */}
      <div className="px-6 py-4 border-b border-white/10 bg-black/20 flex items-center justify-between">
        <div className="flex items-center space-x-3">
          <div className="relative">
            <div className="w-10 h-10 rounded-full bg-primary/20 border border-primary/50 flex items-center justify-center neon-border">
              <Shield className="w-5 h-5 text-primary" />
            </div>
            <div className="absolute -bottom-1 -right-1 w-3.5 h-3.5 bg-success rounded-full border-2 border-[#12121c]"></div>
          </div>
          <div>
            <h2 className="text-lg font-bold text-white tracking-wide">
              Zora <span className="text-secondary text-sm font-normal">AI</span>
            </h2>
            <p className="text-xs text-secondary/70">
              {isStreaming ? (currentTool ? 'Working...' : 'Typing...') : 'Online & Ready'}
            </p>
          </div>
        </div>
        <div className="flex space-x-2">
          <button
            onClick={resetChat}
            className="p-2 rounded-lg bg-black/30 border border-white/5 text-gray-400 hover:text-white hover:bg-black/50 transition-colors"
            title="Reset conversation"
          >
            <RotateCcw className="w-4 h-4" />
          </button>
          {onOpenSettings && (
            <button
              onClick={onOpenSettings}
              className="p-2 rounded-lg bg-black/30 border border-white/5 text-gray-400 hover:text-white hover:bg-black/50 transition-colors"
              title="Settings"
            >
              <Settings className="w-4 h-4" />
            </button>
          )}
        </div>
      </div>

      {/* Messages */}
      <div ref={scrollRef} className="flex-1 p-6 overflow-y-auto space-y-6">
        {messages.map((m, i) => (
          <div key={i} className={cn('flex', m.role === 'user' ? 'justify-end' : 'justify-start')}>
            {m.role === 'tool_indicator' ? (
              <div className="max-w-[80%] rounded-2xl px-5 py-3 bg-secondary/10 border border-secondary/20 text-secondary text-sm flex items-center space-x-3">
                <Loader className="w-4 h-4 animate-spin" />
                <span>{m.text}</span>
              </div>
            ) : (
              <div
                className={cn(
                  'max-w-[80%] rounded-2xl px-5 py-3 shadow-lg',
                  m.role === 'user'
                    ? 'bg-primary/90 text-white rounded-tr-sm'
                    : m.role === 'system'
                      ? 'bg-danger/20 text-danger border border-danger/30 text-sm'
                      : 'bg-surface border border-white/10 text-gray-200 rounded-tl-sm neon-border'
                )}
              >
                {m.role === 'zora' && (
                  <div className="flex items-center space-x-2 mb-1.5 opacity-80">
                    <Terminal className="w-3.5 h-3.5 text-secondary" />
                    <span className="text-xs font-semibold text-secondary tracking-wider">ZORA</span>
                  </div>
                )}
                <p className="leading-relaxed whitespace-pre-wrap">{m.text}</p>

                {m.action && (
                  <div className="mt-3">
                    <button
                      onClick={() => onRunDiagnostic && onRunDiagnostic(m.action)}
                      className="inline-flex items-center px-2.5 py-1 rounded text-xs font-medium bg-black/30 border border-white/10 text-gray-300 hover:bg-black/50 hover:text-white cursor-pointer transition-colors"
                    >
                      <Zap className="w-3 h-3 mr-1 text-warning" />
                      Run '{m.action}' diagnostic
                    </button>
                  </div>
                )}
              </div>
            )}
          </div>
        ))}

        {isStreaming && !currentTool && messages[messages.length - 1]?.role !== 'zora' && (
          <div className="flex justify-start">
            <div className="bg-surface border border-white/10 rounded-2xl rounded-tl-sm px-5 py-4 w-20 flex justify-center space-x-1 neon-border">
              <div className="w-2 h-2 rounded-full bg-secondary/60 animate-bounce" style={{ animationDelay: '0ms' }} />
              <div className="w-2 h-2 rounded-full bg-secondary/80 animate-bounce" style={{ animationDelay: '150ms' }} />
              <div className="w-2 h-2 rounded-full bg-secondary/100 animate-bounce" style={{ animationDelay: '300ms' }} />
            </div>
          </div>
        )}
      </div>

      {/* Input */}
      <div className="p-4 bg-black/20 border-t border-white/5">
        <form onSubmit={handleSend} className="relative flex items-center">
          <input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="Tell me what's going on with your PC..."
            className="w-full bg-surface/80 border border-white/10 text-white placeholder-gray-500 rounded-xl pl-5 pr-12 py-3.5 focus:outline-none focus:ring-2 focus:ring-primary/50 focus:border-primary/50 transition-all text-sm shadow-inner"
          />
          <button
            type="submit"
            disabled={!input.trim() || isStreaming}
            className="absolute right-2 p-2 rounded-lg bg-primary/20 text-primary hover:bg-primary/30 hover:text-white transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
          >
            <MessageSquare className="w-5 h-5" />
          </button>
        </form>
      </div>
    </div>
  );
}
