import Link from 'next/link';
import { ArticleIndex } from '@/lib/articles';
import CategoryThumbnail from './CategoryThumbnail';

interface HeroSectionProps {
  articles: ArticleIndex[];
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

export default function HeroSection({ articles }: HeroSectionProps) {
  if (articles.length === 0) return null;

  const featured = articles[0];
  const sideArticles = articles.slice(1, 6);

  return (
    <section className="border-b border-dark-border">
      <div className="container mx-auto px-4 py-6">
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
          {/* Left: Article list */}
          <div className="lg:col-span-5 space-y-0 divide-y divide-dark-border">
            {sideArticles.map((article) => (
              <Link
                key={article.slug}
                href={`/article/${article.slug}`}
                className="group flex gap-4 py-4 first:pt-0 last:pb-0"
              >
                {/* Thumbnail */}
                <div className="flex-shrink-0 w-20 h-20 rounded-md overflow-hidden">
                  {article.featured_image ? (
                    <img
                      src={article.featured_image}
                      alt={article.title}
                      className="w-full h-full object-cover"
                    />
                  ) : (
                    <CategoryThumbnail category={article.topic} className="w-full h-full" />
                  )}
                </div>

                {/* Content */}
                <div className="flex-1 min-w-0">
                  {article.topic && (
                    <span className="text-[10px] font-semibold uppercase tracking-wider text-accent-400">
                      {article.topic}
                    </span>
                  )}
                  <h3 className="text-sm font-semibold text-text-primary group-hover:text-accent-400 transition-colors line-clamp-2 leading-snug mt-0.5">
                    {article.title}
                  </h3>
                  <span className="text-[11px] text-text-tertiary mt-1 block">
                    {timeAgo(article.created_at)}
                  </span>
                </div>
              </Link>
            ))}
          </div>

          {/* Right: Featured article */}
          <div className="lg:col-span-7">
            <Link href={`/article/${featured.slug}`} className="group block relative">
              <div className="relative aspect-[16/9] rounded-lg overflow-hidden">
                {featured.featured_image ? (
                  <img
                    src={featured.featured_image}
                    alt={featured.title}
                    className="w-full h-full object-cover group-hover:scale-105 transition-transform duration-500"
                  />
                ) : (
                  <CategoryThumbnail category={featured.topic} className="w-full h-full" />
                )}
                {/* Gradient overlay */}
                <div className="absolute inset-0 bg-gradient-to-t from-black/90 via-black/40 to-transparent" />

                {/* Content overlay */}
                <div className="absolute bottom-0 left-0 right-0 p-6">
                  <span className="inline-block bg-accent-400/10 text-accent-400 text-[10px] font-semibold uppercase tracking-wider px-2 py-1 rounded mb-3 backdrop-blur-sm">
                    Featured
                  </span>
                  {featured.topic && (
                    <span className="inline-block bg-white/10 text-white/80 text-[10px] font-semibold uppercase tracking-wider px-2 py-1 rounded mb-3 ml-2 backdrop-blur-sm">
                      {featured.topic}
                    </span>
                  )}
                  <h2 className="text-2xl lg:text-3xl font-bold text-white group-hover:text-accent-400 transition-colors leading-tight">
                    {featured.title}
                  </h2>
                  <p className="text-white/70 text-sm mt-2 line-clamp-2">
                    {featured.meta_description}
                  </p>
                  <div className="flex items-center gap-3 mt-3 text-white/50 text-xs">
                    <span>{featured.reading_time} min read</span>
                    <span>&middot;</span>
                    <span>{timeAgo(featured.created_at)}</span>
                  </div>
                </div>
              </div>
            </Link>
          </div>
        </div>
      </div>
    </section>
  );
}
