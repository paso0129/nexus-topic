'use client';

interface PaginationProps {
  currentPage: number;
  totalPages: number;
  onPageChange: (page: number) => void;
}

export default function Pagination({ currentPage, totalPages, onPageChange }: PaginationProps) {
  if (totalPages <= 1) return null;

  const pages = Array.from({ length: totalPages }, (_, i) => i + 1);

  return (
    <div className="flex items-center justify-center gap-2 mt-10">
      <button
        onClick={() => onPageChange(currentPage - 1)}
        disabled={currentPage === 1}
        className="px-3 py-2 rounded-lg text-sm font-medium bg-dark-surface border border-dark-border text-text-secondary hover:text-accent-400 hover:border-accent-400/50 disabled:opacity-30 disabled:hover:text-text-secondary disabled:hover:border-dark-border transition-colors"
      >
        Prev
      </button>

      {pages.map((page) => (
        <button
          key={page}
          onClick={() => onPageChange(page)}
          className={`w-10 h-10 rounded-lg text-sm font-medium transition-colors ${
            page === currentPage
              ? 'bg-accent-400 text-dark-base'
              : 'bg-dark-surface border border-dark-border text-text-secondary hover:text-accent-400 hover:border-accent-400/50'
          }`}
        >
          {page}
        </button>
      ))}

      <button
        onClick={() => onPageChange(currentPage + 1)}
        disabled={currentPage === totalPages}
        className="px-3 py-2 rounded-lg text-sm font-medium bg-dark-surface border border-dark-border text-text-secondary hover:text-accent-400 hover:border-accent-400/50 disabled:opacity-30 disabled:hover:text-text-secondary disabled:hover:border-dark-border transition-colors"
      >
        Next
      </button>
    </div>
  );
}
