import { useState, useCallback } from 'react';

/**
 * Chat hook with SSE streaming, thinking states, and tool history.
 *
 * Connects to /api/chat/stream for streaming responses.
 * Falls back to /api/chat if streaming is unavailable.
 */
export function useChat() {
  const [messages, setMessages] = useState([
    {
      role: 'zora',
      text: "Hey! I'm Zora, your PC's new best friend. What can I help you with? 🚀",
    },
  ]);
  const [isStreaming, setIsStreaming] = useState(false);
  const [currentTool, setCurrentTool] = useState(null);
  const [toolHistory, setToolHistory] = useState([]);

  const sendMessage = useCallback(async (text) => {
    if (!text.trim() || isStreaming) return;

    // Add user message
    setMessages((prev) => [...prev, { role: 'user', text: text.trim() }]);
    setIsStreaming(true);
    setCurrentTool(null);

    try {
      const response = await fetch('/api/chat/stream', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: text.trim() }),
      });

      if (!response.ok) throw new Error(`HTTP ${response.status}`);

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let assistantText = '';
      let hasStartedResponse = false;
      let messageTools = [];

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        const chunk = decoder.decode(value, { stream: true });
        const lines = chunk.split('\n');

        for (const line of lines) {
          if (!line.startsWith('data: ')) continue;

          let data;
          try {
            data = JSON.parse(line.slice(6));
          } catch {
            continue;
          }

          if (data.type === 'tool_call') {
            setCurrentTool(data.name);
            const label = _toolLabel(data.name);
            setMessages((prev) => [
              ...prev.filter((m) => m.role !== 'tool_indicator'),
              { role: 'tool_indicator', text: label, toolName: data.name },
            ]);
          } else if (data.type === 'tool_result') {
            // Track tool for expandable details
            messageTools.push({ name: data.name, result: data.result });
            setToolHistory((prev) => [...prev, { name: data.name, result: data.result }]);
            // Remove indicator
            setMessages((prev) => prev.filter((m) => m.role !== 'tool_indicator'));
            setCurrentTool(null);
          } else if (data.type === 'text') {
            assistantText += data.content;
            if (!hasStartedResponse) {
              hasStartedResponse = true;
              setMessages((prev) => [
                ...prev.filter((m) => m.role !== 'tool_indicator'),
                { role: 'zora', text: assistantText, tools: [...messageTools] },
              ]);
            } else {
              setMessages((prev) => {
                const updated = [...prev];
                for (let i = updated.length - 1; i >= 0; i--) {
                  if (updated[i].role === 'zora') {
                    updated[i] = { ...updated[i], text: assistantText, tools: [...messageTools] };
                    break;
                  }
                }
                return updated;
              });
            }
          } else if (data.type === 'done') {
            // Done
          }
        }
      }
    } catch (err) {
      console.error('Stream failed:', err);
      // Fallback
      try {
        const res = await fetch('/api/chat', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ message: text.trim() }),
        });
        const data = await res.json();
        setMessages((prev) => [
          ...prev.filter((m) => m.role !== 'tool_indicator'),
          { role: 'zora', text: data.reply, action: data.action },
        ]);
      } catch {
        setMessages((prev) => [
          ...prev,
          { role: 'system', text: 'Connection error. Is the Zora backend running?' },
        ]);
      }
    } finally {
      setIsStreaming(false);
      setCurrentTool(null);
    }
  }, [isStreaming]);

  const resetChat = useCallback(async () => {
    try { await fetch('/api/chat/reset', { method: 'POST' }); } catch { }
    setMessages([
      {
        role: 'zora',
        text: "Hey! I'm Zora, your PC's new best friend. What can I help you with? 🚀",
      },
    ]);
    setToolHistory([]);
  }, []);

  return { messages, isStreaming, currentTool, toolHistory, sendMessage, resetChat };
}

function _toolLabel(toolName) {
  const labels = {
    // Computer Use — Vision
    screenshot_and_analyze: '👁️ Looking at screen...',
    find_text_on_screen: '🔎 Finding text on screen...',
    read_screen: '👁️ Reading screen text...',
    // Computer Use — Mouse & Keyboard
    mouse_click: '🖱️ Clicking...',
    mouse_move: '🖱️ Moving cursor...',
    mouse_scroll: '🖱️ Scrolling...',
    type_text: '⌨️ Typing...',
    press_hotkey: '🎹 Pressing keys...',
    // Computer Use — Highlight
    highlight_screen_area: '🔴 Highlighting...',
    // Windows & Apps
    list_windows: '🪟 Listing windows...',
    focus_window: '🎯 Switching window...',
    launch_app: '🚀 Launching app...',
    run_powershell: '⚡ Running command...',
    // Diagnostics
    run_diagnostic: '🔍 Running scan...',
    apply_fix: '🔧 Applying fix...',
    // Windows Settings
    change_windows_setting: '⚙️ Changing setting...',
    // System
    get_system_info: '📊 Checking system...',
    list_processes: '📋 Scanning processes...',
    kill_process: '🛑 Stopping process...',
    // Support
    create_support_ticket: '🎫 Creating ticket...',
    web_search: '🌐 Searching web...',
  };
  return labels[toolName] || `⚙️ ${toolName}...`;
}
