import Link from 'next/link';
import { ArticleIndex } from '@/lib/articles';
import SourceBadge from './SourceBadge';
import CategoryThumbnail from './CategoryThumbnail';

interface ArticleCardProps {
  article: ArticleIndex;
}

function timeAgo(dateStr: string): string {
  const now = new Date();
  const date = new Date(dateStr);
  const diffMs = now.getTime() - date.getTime();
  const diffHours = Math.floor(diffMs / (1000 * 60 * 60));
  const diffDays = Math.floor(diffHours / 24);

  if (diffHours < 1) return 'Just now';
  if (diffHours < 24) return `${diffHours}h ago`;
  if (diffDays < 7) return `${diffDays}d ago`;
  return new Date(dateStr).toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
}

export default function ArticleCard({ article }: ArticleCardProps) {
  return (
    <Link
      href={`/article/${article.slug}`}
      className="group block bg-dark-surface border border-dark-border rounded-lg overflow-hidden hover:border-accent-400/50 transition-all duration-300"
    >
      {/* Image */}
      <div className="aspect-[16/9] overflow-hidden">
        {article.featured_image ? (
          <img
            src={article.featured_image}
            alt={article.title}
            className="w-full h-full object-cover group-hover:scale-105 transition-transform duration-500"
          />
        ) : (
          <CategoryThumbnail category={article.topic} title={article.title} className="w-full h-full" />
        )}
      </div>

      <div className="p-5">
        {/* Topic + Source badges */}
        <div className="flex items-center gap-2 mb-3">
          {article.topic && (
            <span className="bg-accent-400/10 text-accent-400 text-[10px] font-semibold uppercase tracking-wider px-2 py-0.5 rounded">
              {article.topic}
            </span>
          )}
          {article.source && <SourceBadge source={article.source} />}
        </div>

        {/* Title */}
        <h2 className="text-lg font-bold text-text-primary group-hover:text-accent-400 transition-colors line-clamp-2 leading-snug mb-2">
          {article.title}
        </h2>

        {/* Description */}
        <p className="text-text-secondary text-sm mb-4 line-clamp-2">
          {article.meta_description}
        </p>

        {/* Meta */}
        <div className="flex items-center gap-2 text-text-tertiary text-xs">
          <time dateTime={article.created_at}>
            {timeAgo(article.created_at)}
          </time>
          <span>&middot;</span>
          <span>{article.reading_time} min read</span>
        </div>

        {/* Keywords */}
        {article.keywords && article.keywords.length > 0 && (
          <div className="flex flex-wrap gap-2 mt-3 pt-3 border-t border-dark-border">
            {article.keywords.slice(0, 3).map((keyword) => (
              <span
                key={keyword}
                className="text-[11px] text-text-tertiary"
              >
                #{keyword}
              </span>
            ))}
          </div>
        )}
      </div>
    </Link>
  );
}
