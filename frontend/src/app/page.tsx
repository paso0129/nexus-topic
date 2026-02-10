import { Metadata } from 'next';
import ArticleCard from '@/components/ArticleCard';
import { getArticlesIndex } from '@/lib/articles';

export const metadata: Metadata = {
  title: 'Home',
  description: 'Explore our latest AI-generated articles on technology, business, and more',
};

export default async function Home() {
  const articles = await getArticlesIndex();

  return (
    <div className="max-w-7xl mx-auto">
      <div className="mb-12 text-center">
        <h1 className="text-4xl md:text-5xl font-bold text-gray-900 dark:text-white mb-4">
          Welcome to Our Blog
        </h1>
        <p className="text-xl text-gray-600 dark:text-gray-400 max-w-2xl mx-auto">
          Discover trending topics and insights powered by AI
        </p>
      </div>

      {articles.length === 0 ? (
        <div className="text-center py-12">
          <p className="text-gray-600 dark:text-gray-400 text-lg">
            No articles available yet. Run the backend automation to generate content!
          </p>
          <div className="mt-6 bg-gray-100 dark:bg-gray-800 rounded-lg p-6 max-w-2xl mx-auto text-left">
            <h3 className="text-lg font-semibold mb-3">Quick Start:</h3>
            <code className="block bg-gray-900 text-gray-100 p-4 rounded">
              cd backend<br/>
              python main.py --articles 3
            </code>
          </div>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-8">
          {articles.map((article) => (
            <ArticleCard key={article.slug} article={article} />
          ))}
        </div>
      )}
    </div>
  );
}

// Revalidate every hour
export const revalidate = 3600;
