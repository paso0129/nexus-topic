interface SourceBadgeProps {
  source: string;
}

const sourceConfig: Record<string, { label: string; color: string }> = {
  hackernews: { label: 'HN', color: 'bg-orange-500/10 text-orange-400 border-orange-500/20' },
  reddit: { label: 'Reddit', color: 'bg-red-500/10 text-red-400 border-red-500/20' },
  google_trends: { label: 'Trending', color: 'bg-blue-500/10 text-blue-400 border-blue-500/20' },
};

export default function SourceBadge({ source }: SourceBadgeProps) {
  const config = sourceConfig[source.toLowerCase()] || {
    label: source,
    color: 'bg-accent-400/10 text-accent-400 border-accent-400/20',
  };

  return (
    <span className={`inline-flex items-center px-2 py-0.5 rounded text-[10px] font-semibold uppercase tracking-wider border ${config.color}`}>
      {config.label}
    </span>
  );
}
