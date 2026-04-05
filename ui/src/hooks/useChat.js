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
      text: "Hey! I'm Zora, your PC's new best friend. What can I help you with?",
    },
  ]);
  const [isStreaming, setIsStreaming] = useState(false);
  const [currentTool, setCurrentTool] = useState(null);
  const [toolHistory, setToolHistory] = useState([]);
  const [activeTaskId, setActiveTaskId] = useState(null);

  const streamResponse = useCallback(async (response) => {
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
          if (data.result?.task_id) {
            setActiveTaskId(data.result.task_id);
          }
          messageTools.push({ name: data.name, result: data.result });
          setToolHistory((prev) => [...prev, { name: data.name, result: data.result }]);
          setMessages((prev) => prev.filter((m) => m.role !== 'tool_indicator'));
          setCurrentTool(null);
        } else if (data.type === 'consent_request') {
          const taskIdForConsent = data.task_id || activeTaskId;
          if (data.task_id) setActiveTaskId(data.task_id);
          setMessages((prev) => [
            ...prev.filter((m) => m.role !== 'tool_indicator'),
            {
              role: 'consent',
              stepId: data.step_id,
              taskId: taskIdForConsent,
              title: data.title,
              reason: data.reason,
              status: 'pending',
            },
          ]);
          setCurrentTool(null);
        } else if (data.type === 'user_input_request') {
          const taskIdForInput = data.task_id || activeTaskId;
          if (data.task_id) setActiveTaskId(data.task_id);
          setMessages((prev) => [
            ...prev.filter((m) => m.role !== 'tool_indicator'),
            {
              role: 'user_input',
              stepId: data.step_id,
              taskId: taskIdForInput,
              fieldName: data.field_name,
              prompt: data.prompt || data.reason || 'I need a little more info to continue.',
              status: 'pending',
              // Phase 5: select_from_list carries a choices list + kind
              // discriminator so the UI renders a radio-list card.
              choices: data.choices || null,
              kind: data.kind || 'text',
            },
          ]);
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
        }
      }
    }
  }, []);

  const sendMessage = useCallback(async (text) => {
    if (!text.trim() || isStreaming) return;

    const trimmed = text.trim();
    setMessages((prev) => [...prev, { role: 'user', text: trimmed }]);
    setIsStreaming(true);
    setCurrentTool(null);

    try {
      const confirmMatch = trimmed.match(/^confirm\s+(.+)/i);
      if (confirmMatch && activeTaskId) {
        const confirmRes = await fetch(`/api/tasks/${activeTaskId}/confirm`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ step_id: confirmMatch[1].trim() }),
        });
        if (!confirmRes.ok) throw new Error(`HTTP ${confirmRes.status}`);
        const streamRes = await fetch(`/api/tasks/${activeTaskId}/stream`);
        await streamResponse(streamRes);
        return;
      }

      if (/^cancel$/i.test(trimmed) && activeTaskId) {
        const cancelRes = await fetch(`/api/tasks/${activeTaskId}/cancel`, { method: 'POST' });
        if (!cancelRes.ok) throw new Error(`HTTP ${cancelRes.status}`);
        setMessages((prev) => [...prev, { role: 'system', text: `Cancelled task ${activeTaskId}.` }]);
        setActiveTaskId(null);
        return;
      }

      const response = await fetch('/api/chat/stream', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: trimmed }),
      });
      await streamResponse(response);
    } catch (err) {
      console.error('Stream failed:', err);
      try {
        const res = await fetch('/api/chat', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ message: trimmed }),
        });
        const data = await res.json();
        if (data.task_id) setActiveTaskId(data.task_id);
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
  }, [activeTaskId, isStreaming, streamResponse]);

  const confirmStep = useCallback(async (taskId, stepId) => {
    if (!taskId || !stepId || isStreaming) return;
    setIsStreaming(true);
    setCurrentTool(null);
    setMessages((prev) =>
      prev.map((m) =>
        m.role === 'consent' && m.taskId === taskId && m.stepId === stepId
          ? { ...m, status: 'approved' }
          : m,
      ),
    );
    try {
      const confirmRes = await fetch(`/api/tasks/${taskId}/confirm`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ step_id: stepId }),
      });
      if (!confirmRes.ok) throw new Error(`HTTP ${confirmRes.status}`);
      const streamRes = await fetch(`/api/tasks/${taskId}/stream`);
      await streamResponse(streamRes);
    } catch (err) {
      console.error('Confirm failed:', err);
      setMessages((prev) => [
        ...prev,
        { role: 'system', text: 'Could not confirm that step. Is the backend running?' },
      ]);
    } finally {
      setIsStreaming(false);
      setCurrentTool(null);
    }
  }, [isStreaming, streamResponse]);

  const cancelStep = useCallback(async (taskId, stepId) => {
    if (!taskId || isStreaming) return;
    setMessages((prev) =>
      prev.map((m) =>
        m.role === 'consent' && m.taskId === taskId && m.stepId === stepId
          ? { ...m, status: 'cancelled' }
          : m,
      ),
    );
    try {
      await fetch(`/api/tasks/${taskId}/cancel`, { method: 'POST' });
      setMessages((prev) => [
        ...prev,
        { role: 'system', text: 'Cancelled.' },
      ]);
    } catch (err) {
      console.error('Cancel failed:', err);
    } finally {
      setActiveTaskId(null);
    }
  }, [isStreaming]);

  const submitUserInput = useCallback(async (taskId, stepId, value) => {
    if (!taskId || !stepId || isStreaming) return;
    setIsStreaming(true);
    setCurrentTool(null);
    setMessages((prev) =>
      prev.map((m) =>
        m.role === 'user_input' && m.taskId === taskId && m.stepId === stepId
          ? { ...m, status: 'submitted', value }
          : m,
      ),
    );
    try {
      const res = await fetch(`/api/tasks/${taskId}/user_input`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ step_id: stepId, value }),
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const streamRes = await fetch(`/api/tasks/${taskId}/stream`);
      await streamResponse(streamRes);
    } catch (err) {
      console.error('User input failed:', err);
      setMessages((prev) => [
        ...prev,
        { role: 'system', text: 'Could not submit that value. Is the backend running?' },
      ]);
    } finally {
      setIsStreaming(false);
      setCurrentTool(null);
    }
  }, [isStreaming, streamResponse]);

  const resetChat = useCallback(async () => {
    try {
      await fetch('/api/chat/reset', { method: 'POST' });
    } catch {
      // ignore
    }
    setMessages([
      {
        role: 'zora',
        text: "Hey! I'm Zora, your PC's new best friend. What can I help you with?",
      },
    ]);
    setToolHistory([]);
    setActiveTaskId(null);
  }, []);

  return {
    messages,
    isStreaming,
    currentTool,
    toolHistory,
    sendMessage,
    resetChat,
    confirmStep,
    cancelStep,
    submitUserInput,
  };
}

function _toolLabel(toolName) {
  const labels = {
    RouterAgent: 'Routing issue...',
    ResearchAgent: 'Researching trusted sources...',
    WindowsAgent: 'Working through Windows settings...',
    FilesAgent: 'Looking through files...',
    OEMAgent: 'Checking OEM tools...',
    BrowserSupportAgent: 'Working in the browser...',
    DesktopNavigationAgent: 'Inspecting the desktop...',
    SupportCaseAgent: 'Preparing support case...',
    screenshot_and_analyze: 'Looking at screen...',
    find_text_on_screen: 'Finding text on screen...',
    read_screen: 'Reading screen text...',
    mouse_click: 'Clicking...',
    mouse_move: 'Moving cursor...',
    mouse_scroll: 'Scrolling...',
    type_text: 'Typing...',
    press_hotkey: 'Pressing keys...',
    highlight_screen_area: 'Highlighting...',
    list_windows: 'Listing windows...',
    focus_window: 'Switching window...',
    launch_app: 'Launching app...',
    run_powershell: 'Running command...',
    run_diagnostic: 'Running scan...',
    apply_fix: 'Applying fix...',
    change_windows_setting: 'Changing setting...',
    get_system_info: 'Checking system...',
    list_processes: 'Scanning processes...',
    kill_process: 'Stopping process...',
    create_support_ticket: 'Creating ticket...',
    web_search: 'Searching web...',
    manage_files: 'Managing files...',
    open_url: 'Opening page...',
  };
  return labels[toolName] || `${toolName}...`;
}
