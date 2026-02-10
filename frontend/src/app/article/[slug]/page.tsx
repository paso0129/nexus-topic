import { Metadata } from 'next';
import { notFound } from 'next/navigation';
import { getArticle, getArticlesIndex } from '@/lib/articles';
import AdSense from '@/components/AdSense';

type Props = {
  params: { slug: string };
};

export async function generateMetadata({ params }: Props): Promise<Metadata> {
  const article = await getArticle(params.slug);

  if (!article) {
    return {
      title: 'Article Not Found',
    };
  }

  return {
    title: article.title,
    description: article.meta_description,
    keywords: article.keywords,
    openGraph: {
      title: article.title,
      description: article.meta_description,
      type: 'article',
      publishedTime: article.created_at,
      authors: [article.author.name],
    },
    twitter: {
      card: 'summary_large_image',
      title: article.title,
      description: article.meta_description,
    },
  };
}

export async function generateStaticParams() {
  const articles = await getArticlesIndex();

  return articles.map((article) => ({
    slug: article.slug,
  }));
}

export default async function ArticlePage({ params }: Props) {
  const article = await getArticle(params.slug);

  if (!article) {
    notFound();
  }

  return (
    <article className="max-w-4xl mx-auto">
      {/* Article Header */}
      <header className="mb-8">
        <h1 className="text-4xl md:text-5xl font-bold text-gray-900 dark:text-white mb-4">
          {article.title}
        </h1>

        <div className="flex items-center gap-4 text-gray-600 dark:text-gray-400">
          <time dateTime={article.created_at}>
            {new Date(article.created_at).toLocaleDateString('en-US', {
              year: 'numeric',
              month: 'long',
              day: 'numeric',
            })}
          </time>
          <span>•</span>
          <span>{article.reading_time} min read</span>
          <span>•</span>
          <span>{article.word_count} words</span>
        </div>

        {article.keywords && article.keywords.length > 0 && (
          <div className="flex flex-wrap gap-2 mt-4">
            {article.keywords.slice(0, 5).map((keyword) => (
              <span
                key={keyword}
                className="px-3 py-1 bg-blue-100 dark:bg-blue-900 text-blue-800 dark:text-blue-200 rounded-full text-sm"
              >
                {keyword}
              </span>
            ))}
          </div>
        )}
      </header>

      {/* Top AdSense */}
      <div className="mb-8">
        <AdSense slot="header" format="horizontal" />
      </div>

      {/* Article Content */}
      <div
        className="article-content prose prose-lg max-w-none"
        dangerouslySetInnerHTML={{ __html: article.content }}
      />

      {/* Bottom AdSense */}
      <div className="mt-8">
        <AdSense slot="footer" format="horizontal" />
      </div>

      {/* Author Info */}
      {article.author && (
        <div className="mt-12 p-6 bg-gray-100 dark:bg-gray-800 rounded-lg">
          <h3 className="text-lg font-semibold mb-2">About the Author</h3>
          <p className="text-gray-600 dark:text-gray-400">{article.author.name}</p>
          {article.author.bio && (
            <p className="text-gray-600 dark:text-gray-400 mt-2">{article.author.bio}</p>
          )}
        </div>
      )}
    </article>
  );
}

// Revalidate every hour
export const revalidate = 3600;
