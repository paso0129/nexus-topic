import Link from 'next/link';
import { ArticleIndex } from '@/lib/articles';

interface TrendingSidebarProps {
  articles: ArticleIndex[];
}

export default function TrendingSidebar({ articles }: TrendingSidebarProps) {
  if (articles.length === 0) return null;

  return (
    <div className="bg-dark-surface border border-dark-border rounded-lg p-6 relative overflow-hidden">
      {/* Watermark background text */}
      <div className="absolute -right-4 top-6 text-[120px] font-black text-dark-elevated/50 leading-none select-none pointer-events-none">
        #
      </div>

      {/* Header */}
      <h3 className="text-sm font-bold uppercase tracking-widest text-accent-400 mb-6 relative z-10">
        Trending Now
      </h3>

      {/* Trending list */}
      <div className="space-y-0 divide-y divide-dark-border relative z-10">
        {articles.slice(0, 5).map((article, index) => (
          <Link
            key={article.slug}
            href={`/article/${article.slug}`}
            className="group flex gap-4 py-4 first:pt-0 last:pb-0"
          >
            {/* Number */}
            <span className="text-3xl font-black text-accent-400/30 group-hover:text-accent-400/60 transition-colors w-8 flex-shrink-0 leading-none pt-1">
              {index + 1}
            </span>

            {/* Content */}
            <div className="flex-1 min-w-0">
              {article.topic && (
                <span className="text-[10px] font-semibold uppercase tracking-wider text-text-tertiary">
                  {article.topic}
                </span>
              )}
              <h4 className="text-sm font-semibold text-text-primary group-hover:text-accent-400 transition-colors line-clamp-2 leading-snug mt-0.5">
                {article.title}
              </h4>
              <span className="text-[11px] text-text-tertiary mt-1 block">
                {article.reading_time} min read
              </span>
            </div>
          </Link>
        ))}
      </div>
    </div>
  );
}
