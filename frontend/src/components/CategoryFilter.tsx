'use client';

interface CategoryFilterProps {
  activeCategory: string | null;
  onFilter: (category: string | null) => void;
}

export const CATEGORIES = [
  'AI',
  'BIZ & IT',
  'CARS',
  'CULTURE',
  'GAMING',
  'HEALTH',
  'POLICY',
  'SCIENCE',
  'SECURITY',
  'SPACE',
  'TECH',
  'FORUM',
] as const;

export type Category = typeof CATEGORIES[number];

export default function CategoryFilter({ activeCategory, onFilter }: CategoryFilterProps) {
  return (
    <div className="flex items-center gap-2 overflow-x-auto pb-2 scrollbar-hide">
      <button
        onClick={() => onFilter(null)}
        className={`flex-shrink-0 px-4 py-1.5 rounded-full text-xs font-medium uppercase tracking-wide transition-colors ${
          activeCategory === null
            ? 'bg-accent-400 text-white font-semibold'
            : 'bg-dark-surface border border-dark-border text-text-secondary hover:text-accent-400 hover:border-accent-400/50'
        }`}
      >
        All
      </button>
      {CATEGORIES.map((category) => (
        <button
          key={category}
          onClick={() => onFilter(category)}
          className={`flex-shrink-0 px-4 py-1.5 rounded-full text-xs font-medium uppercase tracking-wide transition-colors ${
            activeCategory === category
              ? 'bg-accent-400 text-white font-semibold'
              : 'bg-dark-surface border border-dark-border text-text-secondary hover:text-accent-400 hover:border-accent-400/50'
          }`}
        >
          {category}
        </button>
      ))}
    </div>
  );
}
