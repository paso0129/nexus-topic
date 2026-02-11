import { Metadata } from 'next';
import { getArticlesIndex, getTrendingArticles } from '@/lib/articles';
import HeroSection from '@/components/HeroSection';
import TrendingSidebar from '@/components/TrendingSidebar';
import HomepageContent from '@/components/HomepageContent';
import AdSense from '@/components/AdSense';

export const metadata: Metadata = {
  title: 'Home',
  description: 'Discover trending topics and insights powered by AI',
};

export default async function Home() {
  const articles = await getArticlesIndex();
  const trending = await getTrendingArticles(5);

  // Hero gets the first 6, main content gets the rest
  const heroArticles = articles.slice(0, 6);
  const mainArticles = articles.slice(6);

  return (
    <div>
      {/* Hero Section */}
      {articles.length > 0 ? (
        <HeroSection articles={heroArticles} />
      ) : (
        <div className="container mx-auto px-4 py-16 text-center">
          <h1 className="text-4xl md:text-5xl font-bold text-text-primary mb-4">
            Welcome to NexusTopic
          </h1>
          <p className="text-xl text-text-secondary max-w-2xl mx-auto mb-8">
            Discover trending topics and insights powered by AI
          </p>
          <div className="bg-dark-surface border border-dark-border rounded-lg p-6 max-w-2xl mx-auto text-left">
            <h3 className="text-lg font-semibold text-text-primary mb-3">Quick Start:</h3>
            <code className="block bg-dark-base text-accent-400 p-4 rounded text-sm">
              cd backend && python main.py --articles 3
            </code>
          </div>
        </div>
      )}

      {/* Ad Banner */}
      <div className="container mx-auto px-4 py-4">
        <AdSense slot="header" format="horizontal" variant="banner" />
      </div>

      {/* Main Content */}
      {articles.length > 0 && (
        <div className="container mx-auto px-4 py-8">
          <div className="grid grid-cols-1 lg:grid-cols-12 gap-8">
            {/* Main Article Grid */}
            <div className="lg:col-span-8">
              <h2 className="text-sm font-bold uppercase tracking-widest text-accent-400 mb-6">
                Latest Articles
              </h2>
              <HomepageContent articles={mainArticles.length > 0 ? mainArticles : articles} />
            </div>

            {/* Sidebar */}
            <aside className="lg:col-span-4 space-y-6">
              <TrendingSidebar articles={trending} />
              <AdSense slot="sidebar" format="vertical" variant="sidebar" />
            </aside>
          </div>
        </div>
      )}

      {/* Bottom Ad Banner */}
      <div className="container mx-auto px-4 pb-8">
        <AdSense slot="footer" format="horizontal" variant="banner" />
      </div>
    </div>
  );
}

// Revalidate every hour
export const revalidate = 3600;
