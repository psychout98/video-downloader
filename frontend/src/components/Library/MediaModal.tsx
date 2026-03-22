import { useState, useEffect } from 'react';
import { apiClient, LibraryItem, SeasonGroup, EpisodeInfo } from '../../api/client';
import { formatSize, hashColor } from '../../utils/format';

interface Props {
  item: LibraryItem;
  onClose: () => void;
  onPlay: () => void;
  showToast: (message: string, type?: 'success' | 'error' | 'info') => void;
}

function MediaModal({ item, onClose, onPlay, showToast }: Props) {
  const [seasonGroups, setSeasonGroups] = useState<SeasonGroup[]>([]);
  const [loading, setLoading] = useState(false);
  const [expandedSeason, setExpandedSeason] = useState<number | null>(null);

  // Load episodes for TV/Anime
  useEffect(() => {
    const loadEpisodes = async () => {
      if (item.type === 'movie') return;

      try {
        setLoading(true);
        const data = await apiClient.getEpisodes(item.folder, item.folder_archive);
        setSeasonGroups(data);
        if (data.length > 0) {
          setExpandedSeason(data[0].season);
        }
      } catch (error) {
        showToast('Failed to load episodes', 'error');
        console.error('Episodes error:', error);
      } finally {
        setLoading(false);
      }
    };

    loadEpisodes();
  }, [item, showToast]);

  const handlePlayEpisode = async (ep: EpisodeInfo) => {
    try {
      // Build playlist: all episodes in the same season starting from this one
      const group = seasonGroups.find((g) => g.season === ep.season);
      const playlist = group
        ? group.episodes.filter((e) => e.episode >= ep.episode).map((e) => e.path)
        : [ep.path];

      await apiClient.openInMpc(ep.path, undefined, playlist);
      onPlay();
      onClose();
      showToast('Playing in MPC-BE', 'success');
    } catch (error) {
      showToast('Failed to open in MPC-BE', 'error');
      console.error('Play error:', error);
    }
  };

  const handlePlayMovie = async () => {
    try {
      await apiClient.openInMpc(item.path);
      onPlay();
      onClose();
      showToast('Playing in MPC-BE', 'success');
    } catch (error) {
      showToast('Failed to open in MPC-BE', 'error');
      console.error('Play error:', error);
    }
  };

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4" onClick={onClose}>
      <div
        className="bg-dark-surface rounded-lg max-w-2xl w-full max-h-[90vh] overflow-auto"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="p-6">
          {/* Header */}
          <div className="flex items-start justify-between mb-6">
            <div className="flex-1 pr-4">
              <h2 className="text-2xl font-bold text-dark-text mb-2">{item.title}</h2>
              <div className="flex gap-2">
                <span className="badge badge-accent capitalize">{item.type}</span>
                {item.year && (
                  <span className="badge badge-accent">{item.year}</span>
                )}
                <span className="badge badge-info capitalize">{item.storage}</span>
              </div>
            </div>
            <button
              onClick={onClose}
              className="text-dark-text/60 hover:text-dark-text text-xl"
            >
              ×
            </button>
          </div>

          {/* Poster & Info */}
          <div className="flex gap-6 mb-6">
            <div className="w-32 h-48 rounded overflow-hidden flex-shrink-0 bg-dark-bg">
              {item.poster ? (
                <img
                  src={apiClient.getPosterUrl(item.poster)}
                  alt={item.title}
                  className="w-full h-full object-cover"
                />
              ) : (
                <div
                  className="w-full h-full flex items-center justify-center text-dark-bg font-bold text-3xl"
                  style={{ backgroundColor: hashColor(item.title) }}
                >
                  {item.title.charAt(0).toUpperCase()}
                </div>
              )}
            </div>

            <div className="flex-1">
              <p className="text-dark-text/80 mb-2 text-sm">
                <span className="font-semibold">Location:</span> {item.folder}
              </p>
              <p className="text-dark-text/80 mb-2 text-sm">
                <span className="font-semibold">Size:</span> {formatSize(item.size_bytes)}
              </p>
              <p className="text-dark-text/80 mb-2 text-sm">
                <span className="font-semibold">Files:</span> {item.file_count}
              </p>

              {item.type === 'movie' && (
                <button onClick={handlePlayMovie} className="btn-primary w-full mt-4">
                  Play in MPC-BE
                </button>
              )}
            </div>
          </div>

          {/* Episodes */}
          {item.type !== 'movie' && (
            <div>
              <h3 className="text-lg font-semibold mb-4">Episodes</h3>
              {loading ? (
                <p className="text-dark-text/60">Loading episodes...</p>
              ) : seasonGroups.length === 0 ? (
                <p className="text-dark-text/60">No episodes found</p>
              ) : (
                <div className="space-y-2">
                  {seasonGroups.map((group) => (
                    <div key={group.season}>
                      <button
                        onClick={() =>
                          setExpandedSeason(
                            expandedSeason === group.season ? null : group.season
                          )
                        }
                        className="w-full flex items-center justify-between p-3 bg-dark-bg rounded hover:bg-dark-bg/80 transition-colors"
                      >
                        <span className="font-semibold">
                          Season {group.season} ({group.episodes.length} episodes)
                        </span>
                        <span className="text-dark-text/60">
                          {expandedSeason === group.season ? '▼' : '▶'}
                        </span>
                      </button>

                      {expandedSeason === group.season && (
                        <div className="mt-1 space-y-1 pl-4">
                          {group.episodes.map((ep) => (
                            <button
                              key={`${ep.season}-${ep.episode}-${ep.filename}`}
                              onClick={() => handlePlayEpisode(ep)}
                              className="w-full text-left p-2 bg-dark-bg/50 rounded hover:bg-dark-accent/20 transition-colors text-sm"
                            >
                              <div className="flex items-center justify-between">
                                <span className="font-semibold">
                                  E{String(ep.episode).padStart(2, '0')}: {ep.title}
                                </span>
                                <span className="text-xs text-dark-text/60 ml-2">
                                  {formatSize(ep.size_bytes)}
                                </span>
                              </div>
                              {ep.progress_pct > 0 && (
                                <div className="mt-1">
                                  <div className="progress-bar">
                                    <div
                                      className="progress-fill"
                                      style={{ width: `${ep.progress_pct}%` }}
                                    />
                                  </div>
                                  <span className="text-xs text-dark-text/50">{ep.progress_pct}% watched</span>
                                </div>
                              )}
                            </button>
                          ))}
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

export default MediaModal;
