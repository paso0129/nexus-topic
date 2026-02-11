import { Metadata } from 'next';
import { notFound } from 'next/navigation';
import { getArticle, getArticlesIndex } from '@/lib/articles';
import AdSense from '@/components/AdSense';
import SourceBadge from '@/components/SourceBadge';
import CategoryThumbnail from '@/components/CategoryThumbnail';

type Props = {
  params: { slug: string };
};

export async function generateMetadata({ params }: Props): Promise<Metadata> {
  const article = await getArticle(params.slug);

  if (!article) {
    return { title: 'Article Not Found' };
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
      ...(article.author?.name && { authors: [article.author.name] }),
      ...(article.featured_image && { images: [article.featured_image] }),
    },
    twitter: {
      card: 'summary_large_image',
      title: article.title,
      description: article.meta_description,
      ...(article.featured_image && { images: [article.featured_image] }),
    },
  };
}

export async function generateStaticParams() {
  const articles = await getArticlesIndex();
  return articles.map((article) => ({ slug: article.slug }));
}

export default async function ArticlePage({ params }: Props) {
  const article = await getArticle(params.slug);

  if (!article) {
    notFound();
  }

  return (
    <div className="container mx-auto px-4 py-8">
      {/* Top Banner Ad */}
      <div className="max-w-6xl mx-auto mb-8">
        <AdSense slot="header" format="horizontal" variant="banner" />
      </div>

      <div className="max-w-6xl mx-auto grid grid-cols-1 lg:grid-cols-12 gap-8">
        {/* Main Content */}
        <article className="lg:col-span-8">
          {/* Featured Image */}
          {article.featured_image ? (
            <div className="aspect-[21/9] rounded-lg overflow-hidden mb-8">
              <img
                src={article.featured_image}
                alt={article.title}
                className="w-full h-full object-cover"
              />
            </div>
          ) : (
            <div className="aspect-[21/9] rounded-lg overflow-hidden mb-8">
              <CategoryThumbnail category={article.topic} className="w-full h-full" />
            </div>
          )}

          {/* Article Header */}
          <header className="mb-8">
            <div className="flex items-center gap-2 mb-4">
              {article.topic && (
                <span className="bg-accent-400/10 text-accent-400 text-xs font-semibold uppercase tracking-wider px-3 py-1 rounded">
                  {article.topic}
                </span>
              )}
              {article.source_data?.source && (
                <SourceBadge source={article.source_data.source} />
              )}
            </div>

            <h1 className="text-3xl md:text-4xl font-bold text-text-primary mb-4 leading-tight">
              {article.title}
            </h1>

            <div className="flex items-center gap-4 text-text-secondary text-sm">
              <time dateTime={article.created_at}>
                {new Date(article.created_at).toLocaleDateString('en-US', {
                  year: 'numeric',
                  month: 'long',
                  day: 'numeric',
                })}
              </time>
              <span className="text-dark-border">&middot;</span>
              <span>{article.reading_time} min read</span>
              <span className="text-dark-border">&middot;</span>
              <span>{article.word_count} words</span>
            </div>

            {article.keywords && article.keywords.length > 0 && (
              <div className="flex flex-wrap gap-2 mt-4">
                {article.keywords.slice(0, 5).map((keyword) => (
                  <span
                    key={keyword}
                    className="px-3 py-1 bg-dark-surface border border-dark-border text-text-secondary rounded-full text-xs"
                  >
                    {keyword}
                  </span>
                ))}
              </div>
            )}
          </header>

          {/* Article Content */}
          <div
            className="article-content"
            dangerouslySetInnerHTML={{ __html: article.content }}
          />

          {/* Bottom AdSense */}
          <div className="mt-8">
            <AdSense slot="footer" format="horizontal" variant="banner" />
          </div>

          {/* Author Info */}
          {article.author && (
            <div className="mt-12 p-6 bg-dark-surface border border-dark-border rounded-lg">
              <h3 className="text-sm font-bold uppercase tracking-widest text-accent-400 mb-3">
                About the Author
              </h3>
              <p className="text-text-primary font-semibold">{article.author.name}</p>
              {article.author.bio && (
                <p className="text-text-secondary text-sm mt-2">{article.author.bio}</p>
              )}
            </div>
          )}
        </article>

        {/* Sidebar */}
        <aside className="lg:col-span-4 space-y-6">
          {/* Sticky sidebar ads */}
          <div className="lg:sticky lg:top-20 space-y-6">
            <AdSense slot="sidebar" format="vertical" variant="sidebar" />
            <AdSense slot="sidebar" format="rectangle" variant="sidebar" />
          </div>
        </aside>
      </div>
    </div>
  );
}

// Revalidate every hour
export const revalidate = 3600;
