import { useRef } from 'react';
import { LibraryItem } from '../../api/client';
import MediaCard from './MediaCard';

interface Props {
  title: string;
  items: LibraryItem[];
  onItemClick: (item: LibraryItem) => void;
  /** Optional map of tmdb_id → progress percentage for overlay bars. */
  progressMap?: Map<number, number>;
  /** Optional set of tmdb_ids that are fully watched. */
  watchedSet?: Set<number>;
}

function MediaRow({ title, items, onItemClick, progressMap, watchedSet }: Props) {
  const scrollRef = useRef<HTMLDivElement>(null);

  if (items.length === 0) return null;

  const scroll = (direction: 'left' | 'right') => {
    if (!scrollRef.current) return;
    const amount = scrollRef.current.clientWidth * 0.75;
    scrollRef.current.scrollBy({
      left: direction === 'right' ? amount : -amount,
      behavior: 'smooth',
    });
  };

  return (
    <div className="mb-6">
      {/* Row header */}
      <h3 className="text-lg font-semibold text-dark-text mb-3 px-1">{title}</h3>

      {/* Scroll container with nav arrows */}
      <div className="relative group/row">
        {/* Left arrow */}
        <button
          onClick={() => scroll('left')}
          className="absolute left-0 top-0 bottom-0 z-10 w-8 flex items-center justify-center
                     bg-gradient-to-r from-dark-bg/90 to-transparent
                     opacity-0 group-hover/row:opacity-100 transition-opacity"
          aria-label="Scroll left"
        >
          <svg className="w-5 h-5 text-dark-text" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M15 19l-7-7 7-7" />
          </svg>
        </button>

        {/* Scrollable row */}
        <div
          ref={scrollRef}
          className="flex gap-3 overflow-x-auto scrollbar-hide pb-2 px-1"
          style={{ scrollbarWidth: 'none', msOverflowStyle: 'none' }}
        >
          {items.map((item) => {
            const tmdbId = item.tmdb_id;
            const pct = tmdbId !== null && progressMap ? progressMap.get(tmdbId) : undefined;
            const watched = tmdbId !== null && watchedSet ? watchedSet.has(tmdbId) : false;

            return (
              <MediaCard
                key={item.folder_name}
                item={item}
                onClick={() => onItemClick(item)}
                progressPct={pct}
                watched={watched}
              />
            );
          })}
        </div>

        {/* Right arrow */}
        <button
          onClick={() => scroll('right')}
          className="absolute right-0 top-0 bottom-0 z-10 w-8 flex items-center justify-center
                     bg-gradient-to-l from-dark-bg/90 to-transparent
                     opacity-0 group-hover/row:opacity-100 transition-opacity"
          aria-label="Scroll right"
        >
          <svg className="w-5 h-5 text-dark-text" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M9 5l7 7-7 7" />
          </svg>
        </button>
      </div>
    </div>
  );
}

export default MediaRow;
