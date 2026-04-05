import { Cpu, HardDrive, Activity, Terminal } from 'lucide-react';
import clsx from 'clsx';
import { twMerge } from 'tailwind-merge';
import { useSystemStats } from '../hooks/useSystemStats';

function cn(...inputs) {
  return twMerge(clsx(inputs));
}

function StatCard({ title, value, subtext, icon, color, percent }) {
  const colorMap = {
    primary: 'bg-primary border-primary/30 text-primary-300',
    secondary: 'bg-secondary border-secondary/30 text-secondary-300',
    warning: 'bg-warning border-warning/30 text-warning-300',
    success: 'bg-success border-success/30 text-success-300',
  };

  return (
    <div className="glass rounded-2xl p-5 relative overflow-hidden group hover:bg-surface/80 transition-all border-l border-t border-white/5">
      <div className="flex justify-between items-start mb-4">
        <div className="flex flex-col">
          <span className="text-xs font-bold tracking-widest text-gray-500 mb-1">{title}</span>
          <div className="flex items-baseline space-x-1">
            <span className="text-2xl font-bold text-white neon-text">{value}</span>
            {subtext && <span className="text-xs text-gray-400 font-medium">{subtext}</span>}
          </div>
        </div>
        <div className="p-2 rounded-lg bg-black/40 border border-white/5 group-hover:bg-black/60 transition-colors">
          {icon}
        </div>
      </div>

      {percent !== undefined && (
        <div className="w-full h-1.5 bg-black/50 rounded-full overflow-hidden">
          <div
            className={cn('h-full rounded-full transition-all duration-1000', colorMap[color].split(' ')[0])}
            style={{ width: `${percent}%` }}
          />
        </div>
      )}

      <div
        className={cn(
          'absolute -bottom-6 -right-6 w-24 h-24 rounded-full blur-2xl opacity-10 transition-opacity group-hover:opacity-20',
          colorMap[color].split(' ')[0]
        )}
      />
    </div>
  );
}

export function SystemStats() {
  const { stats } = useSystemStats();

  if (!stats) {
    return <div className="glass rounded-xl p-6 animate-pulse bg-white/5 h-32"></div>;
  }

  return (
    <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
      <StatCard
        title="CPU CORE"
        value={`${stats.cpu_percent.toFixed(1)}%`}
        icon={<Cpu className="w-5 h-5 text-secondary" />}
        color="secondary"
        percent={stats.cpu_percent}
      />
      <StatCard
        title="MEMORY"
        value={`${stats.memory_used_gb.toFixed(1)}GB`}
        subtext={`/ ${stats.memory_total_gb.toFixed(0)}GB`}
        icon={<Activity className="w-5 h-5 text-primary" />}
        color="primary"
        percent={stats.memory_percent}
      />
      <StatCard
        title="STORAGE"
        value={`${stats.disk_free_gb.toFixed(0)}GB`}
        subtext="Free"
        icon={<HardDrive className="w-5 h-5 text-warning" />}
        color="warning"
        percent={stats.disk_percent}
      />
      <StatCard
        title="UPTIME"
        value={`${stats.uptime_hours.toFixed(1)}H`}
        icon={<Terminal className="w-5 h-5 text-success" />}
        color="success"
      />
    </div>
  );
}

