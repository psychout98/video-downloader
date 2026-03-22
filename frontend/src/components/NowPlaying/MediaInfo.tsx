import { MpcMediaContext } from '../../api/client';
import { hashColor } from '../../utils/format';

interface Props {
  media: MpcMediaContext | null;
  filename: string | null;
}

function MediaInfo({ media, filename }: Props) {
  const title = media?.title || filename || 'No file loaded';

  const subtitle = media
    ? [
        media.type === 'movie' ? null : media.season != null ? `Season ${media.season}` : null,
        media.type === 'movie' ? null : media.episode != null ? `Episode ${media.episode}` : null,
      ]
        .filter(Boolean)
        .join(' \u00B7 ')
    : null;

  const posterUrl = media?.poster_url
    ? `/api/library/poster?path=${encodeURIComponent(media.poster_url)}`
    : null;

  return (
    <div className="flex gap-5 items-center">
      {/* Poster */}
      <div className="w-20 h-28 rounded overflow-hidden flex-shrink-0 bg-dark-bg">
        {posterUrl ? (
          <img
            src={posterUrl}
            alt={title}
            className="w-full h-full object-cover"
          />
        ) : (
          <div
            className="w-full h-full flex items-center justify-center text-dark-bg font-bold text-2xl"
            style={{ backgroundColor: hashColor(title) }}
          >
            {title.charAt(0).toUpperCase()}
          </div>
        )}
      </div>

      {/* Text */}
      <div className="flex-1 min-w-0">
        <h2 className="text-xl font-bold text-dark-text truncate">{title}</h2>
        {subtitle && (
          <p className="text-sm text-dark-text/60 mt-1">{subtitle}</p>
        )}
        {media?.type && (
          <span className="inline-block mt-2 px-2 py-0.5 text-xs font-semibold rounded bg-dark-accent/20 text-dark-accent capitalize">
            {media.type}
          </span>
        )}
      </div>
    </div>
  );
}

export default MediaInfo;
