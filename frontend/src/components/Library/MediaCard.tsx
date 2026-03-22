import { apiClient, LibraryItem } from '../../api/client';
import { hashColor } from '../../utils/format';

interface Props {
  item: LibraryItem;
  onClick: () => void;
  /** 0-100 progress percentage overlay. */
  progressPct?: number;
  /** Show a watched checkmark badge. */
  watched?: boolean;
  /** Optional subtitle line below the title (e.g. "S01E03"). */
  subtitle?: string;
}

function MediaCard({ item, onClick, progressPct, watched, subtitle }: Props) {
  const hasPoster = item.tmdb_id !== null;

  return (
    <button
      onClick={onClick}
      className="flex-shrink-0 w-32 sm:w-36 group text-left focus:outline-none"
    >
      {/* Poster */}
      <div className="relative aspect-[2/3] rounded-lg overflow-hidden bg-dark-bg mb-2">
        {hasPoster ? (
          <img
            src={apiClient.getPosterUrl(item.tmdb_id!)}
            alt={item.title}
            className="w-full h-full object-cover transition-transform group-hover:scale-105"
            loading="lazy"
            onError={(e) => {
              // Hide broken image, show fallback
              (e.target as HTMLImageElement).style.display = 'none';
              const fallback = (e.target as HTMLImageElement).nextElementSibling as HTMLElement;
              if (fallback) fallback.style.display = 'flex';
            }}
          />
        ) : null}

        {/* Fallback initial */}
        <div
          className="absolute inset-0 flex items-center justify-center text-dark-bg font-bold text-3xl"
          style={{
            backgroundColor: hashColor(item.title),
            display: hasPoster ? 'none' : 'flex',
          }}
        >
          {item.title.charAt(0).toUpperCase()}
        </div>

        {/* Hover overlay */}
        <div className="absolute inset-0 bg-black/0 group-hover:bg-black/20 transition-colors" />

        {/* Watched badge */}
        {watched && (
          <div className="absolute top-1.5 right-1.5 w-6 h-6 rounded-full bg-success flex items-center justify-center">
            <svg className="w-3.5 h-3.5 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={3}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
            </svg>
          </div>
        )}

        {/* Progress bar overlay at bottom */}
        {progressPct !== undefined && progressPct > 0 && !watched && (
          <div className="absolute bottom-0 left-0 right-0 h-1 bg-black/50">
            <div
              className="h-full bg-dark-accent transition-all"
              style={{ width: `${Math.min(progressPct, 100)}%` }}
            />
          </div>
        )}
      </div>

      {/* Title */}
      <p className="text-sm font-medium text-dark-text truncate group-hover:text-dark-accent transition-colors">
        {item.title}
      </p>

      {/* Subtitle or year/type */}
      {subtitle ? (
        <p className="text-xs text-dark-text/50 truncate">{subtitle}</p>
      ) : (
        <div className="flex items-center gap-1.5 mt-0.5">
          {item.type && (
            <span className="text-xs text-dark-accent/80 capitalize">{item.type}</span>
          )}
          {item.year && (
            <span className="text-xs text-dark-text/40">{item.year}</span>
          )}
        </div>
      )}
    </button>
  );
}

export default MediaCard;
