import { useState, useEffect, useRef } from 'react';
import { apiClient, ContinueWatchingItem } from '../../api/client';
import { hashColor } from '../../utils/format';

/** Parse "S01E03 - Title.mkv" → { season: 1, episode: 3, title: "Title" } */
function parseEpisodeInfo(relPath: string): { label: string; season?: number; episode?: number } {
  const m = relPath.match(/[Ss](\d{1,2})[Ee](\d{1,3})/);
  if (m) {
    const season = parseInt(m[1], 10);
    const episode = parseInt(m[2], 10);
    return {
      label: `S${String(season).padStart(2, '0')}E${String(episode).padStart(2, '0')}`,
      season,
      episode,
    };
  }
  // Movie or unrecognized format — use filename without extension
  const name = relPath.replace(/\.[^.]+$/, '');
  return { label: name };
}

interface Props {
  onNavigateToDetail: (tmdbId: number) => void;
}

function ContinueWatchingRow({ onNavigateToDetail }: Props) {
  const [items, setItems] = useState<ContinueWatchingItem[]>([]);
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const load = async () => {
      try {
        const data = await apiClient.getContinueWatching();
        setItems(data);
      } catch (err) {
        console.error('Failed to load continue watching:', err);
      }
    };
    load();
  }, []);

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
      <h3 className="text-lg font-semibold text-dark-text mb-3 px-1">Continue Watching</h3>

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

        <div
          ref={scrollRef}
          className="flex gap-3 overflow-x-auto scrollbar-hide pb-2 px-1"
          style={{ scrollbarWidth: 'none', msOverflowStyle: 'none' }}
        >
          {items.map((item) => {
            const epInfo = parseEpisodeInfo(item.rel_path);
            const progressPct = item.duration_ms > 0
              ? Math.round((item.position_ms / item.duration_ms) * 100)
              : 0;

            return (
              <button
                key={`${item.tmdb_id}-${item.rel_path}`}
                onClick={() => onNavigateToDetail(item.tmdb_id)}
                className="flex-shrink-0 w-32 sm:w-36 group text-left focus:outline-none"
              >
                {/* Poster with progress */}
                <div className="relative aspect-[2/3] rounded-lg overflow-hidden bg-dark-bg mb-2">
                  <img
                    src={apiClient.getPosterUrl(item.tmdb_id)}
                    alt={item.title}
                    className="w-full h-full object-cover transition-transform group-hover:scale-105"
                    loading="lazy"
                    onError={(e) => {
                      (e.target as HTMLImageElement).style.display = 'none';
                      const fallback = (e.target as HTMLImageElement).nextElementSibling as HTMLElement;
                      if (fallback) fallback.style.display = 'flex';
                    }}
                  />
                  <div
                    className="absolute inset-0 items-center justify-center text-dark-bg font-bold text-3xl hidden"
                    style={{ backgroundColor: hashColor(item.title) }}
                  >
                    {item.title.charAt(0).toUpperCase()}
                  </div>

                  {/* Hover overlay */}
                  <div className="absolute inset-0 bg-black/0 group-hover:bg-black/20 transition-colors" />

                  {/* Episode badge */}
                  <div className="absolute top-1.5 left-1.5 px-1.5 py-0.5 bg-black/70 rounded text-xs font-semibold text-dark-text">
                    {epInfo.label}
                  </div>

                  {/* Progress bar */}
                  <div className="absolute bottom-0 left-0 right-0 h-1 bg-black/50">
                    <div
                      className="h-full bg-dark-accent transition-all"
                      style={{ width: `${progressPct}%` }}
                    />
                  </div>
                </div>

                {/* Title */}
                <p className="text-sm font-medium text-dark-text truncate group-hover:text-dark-accent transition-colors">
                  {item.title}
                </p>
                <p className="text-xs text-dark-text/50 truncate">
                  {progressPct}% watched
                </p>
              </button>
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

export default ContinueWatchingRow;
