import { useState, useEffect, useCallback } from 'react';

/**
 * Tauri integration hook.
 *
 * Provides window management: drag, minimize, close, pin-to-edge, always-on-top.
 * All functions are no-ops when running in browser (non-Tauri) mode.
 */
export function useTauri() {
  const [isTauri, setIsTauri] = useState(false);

  useEffect(() => {
    setIsTauri(!!window.__TAURI_INTERNALS__);
  }, []);

  const minimizeToTray = useCallback(async () => {
    if (!isTauri) return;
    try {
      const { getCurrentWindow } = await import('@tauri-apps/api/window');
      await getCurrentWindow().hide();
    } catch (err) {
      console.error('Minimize failed:', err);
    }
  }, [isTauri]);

  const closeWindow = useCallback(async () => {
    if (!isTauri) return;
    try {
      const { getCurrentWindow } = await import('@tauri-apps/api/window');
      await getCurrentWindow().close();
    } catch (err) {
      console.error('Close failed:', err);
    }
  }, [isTauri]);

  const startDrag = useCallback(async () => {
    if (!isTauri) return;
    try {
      const { getCurrentWindow } = await import('@tauri-apps/api/window');
      await getCurrentWindow().startDragging();
    } catch (err) {
      console.error('Drag failed:', err);
    }
  }, [isTauri]);

  const pinToEdge = useCallback(async (edge) => {
    if (!isTauri) return;
    try {
      const { invoke } = await import('@tauri-apps/api/core');
      await invoke('pin_to_edge', { edge });
    } catch (err) {
      console.error('Pin failed:', err);
    }
  }, [isTauri]);

  const setAlwaysOnTop = useCallback(async (onTop) => {
    if (!isTauri) return;
    try {
      const { getCurrentWindow } = await import('@tauri-apps/api/window');
      await getCurrentWindow().setAlwaysOnTop(onTop);
    } catch (err) {
      console.error('Always-on-top failed:', err);
    }
  }, [isTauri]);

  return {
    isTauri,
    minimizeToTray,
    closeWindow,
    startDrag,
    pinToEdge,
    setAlwaysOnTop,
  };
}
