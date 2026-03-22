import { useState, useEffect, useMemo } from 'react';
import { apiClient, LibraryItemDetail, EpisodeDetail } from '../../api/client';
import { formatSize, formatMs, hashColor } from '../../utils/format';

interface Props {
  tmdbId: number;
  onBack: () => void;
  onPlay: () => void;
  showToast: (message: string, type?: 'success' | 'error' | 'info') => void;
}

interface SeasonGroup {
  season: number;
  episodes: EpisodeDetail[];
  watchedCount: number;
}

function MediaDetailPage({ tmdbId, onBack, onPlay, showToast }: Props) {
  const [item, setItem] = useState<LibraryItemDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [expandedSeason, setExpandedSeason] = useState<number | null>(null);

  useEffect(() => {
    const load = async () => {
      try {
        setLoading(true);
        const data = await apiClient.getLibraryItem(tmdbId);
        setItem(data);
      } catch (error) {
        showToast('Failed to load media details', 'error');
        console.error('Detail error:', error);
      } finally {
        setLoading(false);
      }
    };
    load();
  }, [tmdbId, showToast]);

  // Group episodes by season
  const seasonGroups = useMemo((): SeasonGroup[] => {
    if (!item?.episodes) return [];

    const grouped = new Map<number, EpisodeDetail[]>();
    for (const ep of item.episodes) {
      const season = ep.season ?? 0;
      if (!grouped.has(season)) grouped.set(season, []);
      grouped.get(season)!.push(ep);
    }

    const groups: SeasonGroup[] = [];
    for (const [season, episodes] of grouped) {
      episodes.sort((a, b) => (a.episode ?? 0) - (b.episode ?? 0));
      groups.push({
        season,
        episodes,
        watchedCount: episodes.filter((e) => e.watched).length,
      });
    }

    groups.sort((a, b) => a.season - b.season);

    // Auto-expand first season with unwatched episodes
    if (groups.length > 0 && expandedSeason === null) {
      const firstUnwatched = groups.find((g) => g.watchedCount < g.episodes.length);
      if (firstUnwatched) {
        // Use setTimeout to avoid setState during render
        setTimeout(() => setExpandedSeason(firstUnwatched.season), 0);
      }
    }

    return groups;
  }, [item?.episodes, expandedSeason]);

  // Find the resume point (last partially watched episode)
  const resumeEpisode = useMemo((): EpisodeDetail | null => {
    if (!item?.episodes) return null;
    const partial = item.episodes
      .filter((e) => e.progress_pct > 0 && !e.watched)
      .sort((a, b) => {
        // Sort by season, then episode — pick the most recent one
        const sa = a.season ?? 0, sb = b.season ?? 0;
        const ea = a.episode ?? 0, eb = b.episode ?? 0;
        return sa !== sb ? sa - sb : ea - eb;
      });
    return partial.length > 0 ? partial[partial.length - 1] : null;
  }, [item?.episodes]);

  // Find the first unwatched episode (for "Play" button)
  const nextUnwatched = useMemo((): EpisodeDetail | null => {
    if (!item?.episodes) return null;
    const sorted = [...item.episodes].sort((a, b) => {
      const sa = a.season ?? 0, sb = b.season ?? 0;
      const ea = a.episode ?? 0, eb = b.episode ?? 0;
      return sa !== sb ? sa - sb : ea - eb;
    });
    return sorted.find((e) => !e.watched) ?? sorted[0] ?? null;
  }, [item?.episodes]);

  const isMovie = item?.type === 'movie' || (item?.episodes?.length === 1 && !item.episodes[0].season);

  const handlePlayEpisode = async (ep: EpisodeDetail) => {
    if (!item) return;
    try {
      // Build playlist: all episodes in the same season starting from this one
      const season = ep.season;
      const sameSeasonEps = item.episodes
        .filter((e) => e.season === season && (e.episode ?? 0) >= (ep.episode ?? 0))
        .sort((a, b) => (a.episode ?? 0) - (b.episode ?? 0));
      const playlist = sameSeasonEps.map((e) => e.rel_path);

      await apiClient.openInMpc(tmdbId, ep.rel_path, playlist.length > 1 ? playlist : undefined);
      onPlay();
      showToast('Playing in MPC-BE', 'success');
    } catch (error) {
      showToast('Failed to open in MPC-BE', 'error');
      console.error('Play error:', error);
    }
  };

  const handlePlayMovie = async () => {
    if (!item?.episodes?.[0]) return;
    try {
      await apiClient.openInMpc(tmdbId, item.episodes[0].rel_path);
      onPlay();
      showToast('Playing in MPC-BE', 'success');
    } catch (error) {
      showToast('Failed to open in MPC-BE', 'error');
      console.error('Play error:', error);
    }
  };

  if (loading) {
    return (
      <div className="text-center py-12">
        <p className="text-dark-text/60">Loading...</p>
      </div>
    );
  }

  if (!item) {
    return (
      <div className="text-center py-12">
        <button onClick={onBack} className="btn-secondary mb-4">Back to Library</button>
        <p className="text-dark-text/60">Media not found.</p>
      </div>
    );
  }

  return (
    <div className="space-y-6 fade-in">
      {/* Back button */}
      <button
        onClick={onBack}
        className="flex items-center gap-2 text-dark-text/60 hover:text-dark-text transition-colors"
      >
        <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M15 19l-7-7 7-7" />
        </svg>
        Back to Library
      </button>

      {/* Header: poster + info */}
      <div className="flex gap-6">
        {/* Poster */}
        <div className="w-40 sm:w-48 flex-shrink-0">
          <div className="aspect-[2/3] rounded-lg overflow-hidden bg-dark-bg">
            <img
              src={apiClient.getPosterUrl(tmdbId)}
              alt={item.title}
              className="w-full h-full object-cover"
              onError={(e) => {
                (e.target as HTMLImageElement).style.display = 'none';
                const fallback = (e.target as HTMLImageElement).nextElementSibling as HTMLElement;
                if (fallback) fallback.style.display = 'flex';
              }}
            />
            <div
              className="w-full h-full items-center justify-center text-dark-bg font-bold text-4xl hidden"
              style={{ backgroundColor: hashColor(item.title) }}
            >
              {item.title.charAt(0).toUpperCase()}
            </div>
          </div>
        </div>

        {/* Info */}
        <div className="flex-1 min-w-0">
          <h1 className="text-3xl font-bold text-dark-text mb-2">{item.title}</h1>

          <div className="flex flex-wrap items-center gap-2 mb-4">
            {item.year && <span className="badge badge-accent">{item.year}</span>}
            {item.type && <span className="badge badge-accent capitalize">{item.type}</span>}
            <span className="badge badge-info capitalize">{item.location}</span>
            <span className="text-sm text-dark-text/50">
              {item.file_count} file{item.file_count !== 1 ? 's' : ''} &middot; {formatSize(item.size_bytes)}
            </span>
          </div>

          {item.overview && (
            <p className="text-dark-text/70 text-sm mb-4 leading-relaxed max-w-2xl">
              {item.overview}
            </p>
          )}

          {/* Action buttons */}
          <div className="flex flex-wrap gap-3">
            {isMovie ? (
              <button onClick={handlePlayMovie} className="btn-primary flex items-center gap-2">
                <svg className="w-4 h-4" fill="currentColor" viewBox="0 0 20 20">
                  <path d="M6.3 2.841A1.5 1.5 0 004 4.11V15.89a1.5 1.5 0 002.3 1.269l9.344-5.89a1.5 1.5 0 000-2.538L6.3 2.84z" />
                </svg>
                {resumeEpisode ? `Resume at ${formatMs(resumeEpisode.position_ms)}` : 'Play'}
              </button>
            ) : (
              <>
                {resumeEpisode && (
                  <button
                    onClick={() => handlePlayEpisode(resumeEpisode)}
                    className="btn-primary flex items-center gap-2"
                  >
                    <svg className="w-4 h-4" fill="currentColor" viewBox="0 0 20 20">
                      <path d="M6.3 2.841A1.5 1.5 0 004 4.11V15.89a1.5 1.5 0 002.3 1.269l9.344-5.89a1.5 1.5 0 000-2.538L6.3 2.84z" />
                    </svg>
                    Resume S{String(resumeEpisode.season).padStart(2, '0')}E{String(resumeEpisode.episode).padStart(2, '0')}
                  </button>
                )}
                {nextUnwatched && nextUnwatched !== resumeEpisode && (
                  <button
                    onClick={() => handlePlayEpisode(nextUnwatched)}
                    className="btn-secondary flex items-center gap-2"
                  >
                    <svg className="w-4 h-4" fill="currentColor" viewBox="0 0 20 20">
                      <path d="M6.3 2.841A1.5 1.5 0 004 4.11V15.89a1.5 1.5 0 002.3 1.269l9.344-5.89a1.5 1.5 0 000-2.538L6.3 2.84z" />
                    </svg>
                    Play S{String(nextUnwatched.season).padStart(2, '0')}E{String(nextUnwatched.episode).padStart(2, '0')}
                  </button>
                )}
              </>
            )}
          </div>
        </div>
      </div>

      {/* Episodes (TV / Anime) */}
      {!isMovie && seasonGroups.length > 0 && (
        <div>
          <h2 className="text-xl font-semibold text-dark-text mb-4">Episodes</h2>
          <div className="space-y-2">
            {seasonGroups.map((group) => (
              <div key={group.season} className="rounded-lg overflow-hidden">
                {/* Season header */}
                <button
                  onClick={() =>
                    setExpandedSeason(expandedSeason === group.season ? null : group.season)
                  }
                  className="w-full flex items-center justify-between p-3 bg-dark-surface hover:bg-dark-surface/80 transition-colors"
                >
                  <div className="flex items-center gap-3">
                    <span className="font-semibold text-dark-text">
                      {group.season === 0 ? 'Specials' : `Season ${group.season}`}
                    </span>
                    <span className="text-sm text-dark-text/50">
                      {group.episodes.length} episode{group.episodes.length !== 1 ? 's' : ''}
                    </span>
                    {group.watchedCount > 0 && (
                      <span className="text-xs text-dark-text/40">
                        {group.watchedCount}/{group.episodes.length} watched
                      </span>
                    )}
                  </div>
                  <svg
                    className={`w-4 h-4 text-dark-text/50 transition-transform ${
                      expandedSeason === group.season ? 'rotate-180' : ''
                    }`}
                    fill="none"
                    viewBox="0 0 24 24"
                    stroke="currentColor"
                    strokeWidth={2}
                  >
                    <path strokeLinecap="round" strokeLinejoin="round" d="M19 9l-7 7-7-7" />
                  </svg>
                </button>

                {/* Episode list */}
                {expandedSeason === group.season && (
                  <div className="bg-dark-bg/50">
                    {group.episodes.map((ep) => (
                      <button
                        key={ep.rel_path}
                        onClick={() => handlePlayEpisode(ep)}
                        className="w-full text-left px-4 py-3 hover:bg-dark-accent/10 transition-colors border-t border-dark-text/5 flex items-center gap-3"
                      >
                        {/* Episode number */}
                        <span className="text-sm font-mono text-dark-text/50 w-10 flex-shrink-0">
                          {ep.episode !== null ? `E${String(ep.episode).padStart(2, '0')}` : ''}
                        </span>

                        {/* Title & progress */}
                        <div className="flex-1 min-w-0">
                          <p className="text-sm font-medium text-dark-text truncate">
                            {ep.title || ep.filename}
                          </p>
                          {ep.progress_pct > 0 && (
                            <div className="mt-1 flex items-center gap-2">
                              <div className="flex-1 max-w-32 h-1 bg-dark-bg rounded-full overflow-hidden">
                                <div
                                  className="h-full bg-dark-accent"
                                  style={{ width: `${ep.progress_pct}%` }}
                                />
                              </div>
                              <span className="text-xs text-dark-text/40">{ep.progress_pct}%</span>
                            </div>
                          )}
                        </div>

                        {/* Status icon */}
                        <div className="flex items-center gap-2 flex-shrink-0">
                          <span className="text-xs text-dark-text/40">{formatSize(ep.size_bytes)}</span>
                          {ep.watched ? (
                            <div className="w-5 h-5 rounded-full bg-success/20 flex items-center justify-center">
                              <svg className="w-3 h-3 text-success" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={3}>
                                <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
                              </svg>
                            </div>
                          ) : ep.progress_pct > 0 ? (
                            <div className="w-5 h-5 rounded-full bg-dark-accent/20 flex items-center justify-center">
                              <svg className="w-3 h-3 text-dark-accent" fill="currentColor" viewBox="0 0 20 20">
                                <path d="M6.3 2.841A1.5 1.5 0 004 4.11V15.89a1.5 1.5 0 002.3 1.269l9.344-5.89a1.5 1.5 0 000-2.538L6.3 2.84z" />
                              </svg>
                            </div>
                          ) : (
                            <div className="w-5 h-5 rounded-full border border-dark-text/20" />
                          )}
                        </div>
                      </button>
                    ))}
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

export default MediaDetailPage;
