'use client';

import { useState, useMemo } from 'react';
import { ArticleIndex } from '@/lib/articles';
import ArticleCard from './ArticleCard';
import CategoryFilter from './CategoryFilter';
import SearchBar from './SearchBar';
import Pagination from './Pagination';

const ARTICLES_PER_PAGE = 8;

interface HomepageContentProps {
  articles: ArticleIndex[];
}

export default function HomepageContent({ articles }: HomepageContentProps) {
  const [activeCategory, setActiveCategory] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState('');
  const [currentPage, setCurrentPage] = useState(1);

  const filteredArticles = useMemo(() => {
    let result = articles;

    // Category filter
    if (activeCategory) {
      result = result.filter((a) => a.topic?.toUpperCase() === activeCategory.toUpperCase());
    }

    // Search filter
    if (searchQuery.trim()) {
      const q = searchQuery.toLowerCase();
      result = result.filter(
        (a) =>
          a.title.toLowerCase().includes(q) ||
          a.meta_description.toLowerCase().includes(q) ||
          a.keywords?.some((k) => k.toLowerCase().includes(q)) ||
          a.topic?.toLowerCase().includes(q)
      );
    }

    return result;
  }, [articles, activeCategory, searchQuery]);

  const totalPages = Math.ceil(filteredArticles.length / ARTICLES_PER_PAGE);
  const paginatedArticles = filteredArticles.slice(
    (currentPage - 1) * ARTICLES_PER_PAGE,
    currentPage * ARTICLES_PER_PAGE
  );

  const handleFilter = (category: string | null) => {
    setActiveCategory(category);
    setCurrentPage(1);
  };

  const handleSearch = (query: string) => {
    setSearchQuery(query);
    setCurrentPage(1);
  };

  return (
    <>
      {/* Search */}
      <div className="mb-6">
        <SearchBar value={searchQuery} onChange={handleSearch} />
      </div>

      {/* Category Filter */}
      <div className="mb-8">
        <CategoryFilter activeCategory={activeCategory} onFilter={handleFilter} />
      </div>

      {/* Results count */}
      {(activeCategory || searchQuery) && (
        <p className="text-text-tertiary text-sm mb-4">
          {filteredArticles.length} article{filteredArticles.length !== 1 ? 's' : ''} found
          {activeCategory && <span> in <span className="text-accent-400">{activeCategory}</span></span>}
          {searchQuery && <span> matching &ldquo;<span className="text-accent-400">{searchQuery}</span>&rdquo;</span>}
        </p>
      )}

      {/* Article Grid */}
      {paginatedArticles.length === 0 ? (
        <div className="text-center py-12">
          <p className="text-text-secondary text-lg">No articles found.</p>
          {(activeCategory || searchQuery) && (
            <button
              onClick={() => { setActiveCategory(null); setSearchQuery(''); }}
              className="mt-3 text-accent-400 hover:text-accent-500 text-sm"
            >
              Clear filters
            </button>
          )}
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          {paginatedArticles.map((article) => (
            <ArticleCard key={article.slug} article={article} />
          ))}
        </div>
      )}

      {/* Pagination */}
      <Pagination
        currentPage={currentPage}
        totalPages={totalPages}
        onPageChange={setCurrentPage}
      />
    </>
  );
}
