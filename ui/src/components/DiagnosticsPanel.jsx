import { useState, useEffect } from 'react';
import { Activity, Wifi, Volume2, MonitorPlay, Shield, Cpu, HardDrive, Printer, FolderOpen, Zap } from 'lucide-react';
import clsx from 'clsx';
import { twMerge } from 'tailwind-merge';

function cn(...inputs) {
  return twMerge(clsx(inputs));
}

export function DiagnosticsPanel({ forceDiagnostic }) {
  const [running, setRunning] = useState(false);
  const [results, setResults] = useState(null);
  const [activeCategory, setActiveCategory] = useState(null);

  useEffect(() => {
    if (forceDiagnostic) {
      runDiag(forceDiagnostic.id);
    }
  }, [forceDiagnostic]);

  const modules = [
    { id: 'internet', name: 'Network', icon: <Wifi className="w-4 h-4" /> },
    { id: 'audio', name: 'Audio', icon: <Volume2 className="w-4 h-4" /> },
    { id: 'display', name: 'Display', icon: <MonitorPlay className="w-4 h-4" /> },
    { id: 'security', name: 'Security', icon: <Shield className="w-4 h-4" /> },
    { id: 'software', name: 'System', icon: <Cpu className="w-4 h-4" /> },
    { id: 'hardware', name: 'Hardware', icon: <HardDrive className="w-4 h-4" /> },
    { id: 'printer', name: 'Printer', icon: <Printer className="w-4 h-4" /> },
    { id: 'files', name: 'Files', icon: <FolderOpen className="w-4 h-4" /> },
  ];

  const runDiag = async (id) => {
    setRunning(true);
    setActiveCategory(id);
    setResults(null);
    try {
      const res = await fetch(`/api/diagnostics/run/${id}`);
      const data = await res.json();
      setResults(data);
    } catch (err) {
      console.error(err);
    } finally {
      setRunning(false);
    }
  };

  const applyFix = async (issueName) => {
    try {
      setResults((prev) => ({
        ...prev,
        results: prev.results.map((r) =>
          r.name === issueName ? { ...r, status: 'fixed', fix_applied: true } : r
        ),
      }));

      await fetch(`/api/diagnostics/fix/${activeCategory}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ issue_name: issueName }),
      });
    } catch (err) {
      console.error(err);
    }
  };

  return (
    <div className="glass rounded-2xl p-6 border-t border-l border-white/5 flex flex-col h-full bg-[#12121c]/80">
      <div className="flex items-center space-x-2 mb-6">
        <Activity className="w-5 h-5 text-secondary" />
        <h3 className="text-lg font-bold text-white tracking-wide">Diagnostic Toolset</h3>
      </div>

      <div className="grid grid-cols-4 gap-3 mb-6">
        {modules.map((m) => (
          <button
            key={m.id}
            onClick={() => runDiag(m.id)}
            disabled={running}
            className={cn(
              'flex flex-col items-center justify-center p-3 rounded-xl border transition-all',
              activeCategory === m.id
                ? 'bg-primary/20 border-primary/50 text-white neon-border'
                : 'bg-black/30 border-white/5 text-gray-400 hover:bg-black/50 hover:text-white'
            )}
          >
            <div
              className={cn(
                'p-2 rounded-full mb-1',
                activeCategory === m.id ? 'bg-primary/30 text-primary' : 'bg-white/5'
              )}
            >
              {m.icon}
            </div>
            <span className="text-xs font-medium">{m.name}</span>
          </button>
        ))}
      </div>

      <div className="flex-1 overflow-y-auto bg-black/20 rounded-xl border border-white/5 p-4 min-h-[250px]">
        {running ? (
          <div className="h-full flex flex-col items-center justify-center space-y-4 text-secondary">
            <div className="w-8 h-8 rounded-full border-2 border-secondary border-t-transparent animate-spin"></div>
            <p className="text-sm font-mono animate-pulse">Executing diagnostics...</p>
          </div>
        ) : !results ? (
          <div className="h-full flex items-center justify-center text-gray-500 text-sm">
            Select a module to run diagnostics.
          </div>
        ) : (
          <div className="space-y-3">
            <h4 className="text-sm justify-between flex font-medium text-white mb-4 uppercase tracking-wider">
              {activeCategory} Scan Results
              <span className="text-xs px-2 py-0.5 rounded bg-black/50 text-gray-400">
                {results.results.length} checks
              </span>
            </h4>

            {results.results.map((r, i) => (
              <div key={i} className="flex flex-col p-3 rounded-lg bg-surface border border-white/5">
                <div className="flex items-start justify-between">
                  <div className="flex items-center space-x-3">
                    <div
                      className={cn(
                        'w-2 h-2 rounded-full',
                        r.status === 'ok'
                          ? "bg-success shadow-[0_0_8px_rgba(16,185,129,0.8)]"
                          : r.status === 'warning'
                            ? "bg-warning shadow-[0_0_8px_rgba(245,158,11,0.8)]"
                            : r.status === 'error'
                              ? "bg-danger shadow-[0_0_8px_rgba(239,68,68,0.8)]"
                              : "bg-primary shadow-[0_0_8px_rgba(109,40,217,0.8)]"
                      )}
                    ></div>
                    <span className="text-sm font-medium text-gray-200">{r.name}</span>
                  </div>

                  {r.fix_available && !r.fix_applied && (
                    <button
                      onClick={() => applyFix(r.name)}
                      className="px-3 py-1 bg-primary hover:bg-primary/80 text-white text-xs rounded shadow-lg shadow-primary/20 transition-all"
                    >
                      FIX
                    </button>
                  )}
                  {r.status === 'fixed' && (
                    <span className="text-xs text-primary font-medium tracking-wide">RESOLVED</span>
                  )}
                </div>
                {r.details && (
                  <p className="text-xs text-gray-500 mt-2 ml-5 line-clamp-2">{r.details}</p>
                )}
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
