import Link from 'next/link';
import { ArticleIndex } from '@/lib/articles';

interface ArticleCardProps {
  article: ArticleIndex;
}

export default function ArticleCard({ article }: ArticleCardProps) {
  return (
    <Link
      href={`/article/${article.slug}`}
      className="group block bg-white dark:bg-gray-800 rounded-lg shadow-md hover:shadow-xl transition-shadow duration-300 overflow-hidden"
    >
      <div className="p-6">
        {/* Topic Badge */}
        {article.topic && (
          <div className="mb-3">
            <span className="inline-block px-3 py-1 bg-blue-100 dark:bg-blue-900 text-blue-800 dark:text-blue-200 rounded-full text-xs font-medium">
              {article.topic}
            </span>
          </div>
        )}

        {/* Title */}
        <h2 className="text-xl font-bold text-gray-900 dark:text-white mb-3 group-hover:text-blue-600 dark:group-hover:text-blue-400 transition-colors line-clamp-2">
          {article.title}
        </h2>

        {/* Description */}
        <p className="text-gray-600 dark:text-gray-400 mb-4 line-clamp-3">
          {article.meta_description}
        </p>

        {/* Meta Info */}
        <div className="flex items-center justify-between text-sm text-gray-500 dark:text-gray-500">
          <div className="flex items-center gap-2">
            <time dateTime={article.created_at}>
              {new Date(article.created_at).toLocaleDateString('en-US', {
                month: 'short',
                day: 'numeric',
                year: 'numeric',
              })}
            </time>
            <span>•</span>
            <span>{article.reading_time} min read</span>
          </div>
        </div>

        {/* Keywords */}
        {article.keywords && article.keywords.length > 0 && (
          <div className="flex flex-wrap gap-2 mt-4">
            {article.keywords.slice(0, 3).map((keyword) => (
              <span
                key={keyword}
                className="text-xs text-gray-500 dark:text-gray-400"
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
