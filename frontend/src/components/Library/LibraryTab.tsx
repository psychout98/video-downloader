import { useState, useEffect } from 'react';
import { apiClient, LibraryItem } from '../../api/client';
import { formatSize, hashColor } from '../../utils/format';
import MediaModal from './MediaModal';

interface Props {
  showToast: (message: string, type?: 'success' | 'error' | 'info') => void;
  onPlay: () => void;
}

type MediaType = 'all' | 'movies' | 'tv' | 'anime';

function LibraryTab({ showToast, onPlay }: Props) {
  const [library, setLibrary] = useState<LibraryItem[]>([]);
  const [filteredLibrary, setFilteredLibrary] = useState<LibraryItem[]>([]);
  const [filter, setFilter] = useState<MediaType>('all');
  const [searchInput, setSearchInput] = useState('');
  const [selectedItem, setSelectedItem] = useState<LibraryItem | null>(null);
  const [loading, setLoading] = useState(true);

  // Load library on mount
  useEffect(() => {
    const loadLibrary = async () => {
      try {
        setLoading(true);
        const data = await apiClient.getLibrary();
        setLibrary(data);
      } catch (error) {
        showToast('Failed to load library', 'error');
        console.error('Library error:', error);
      } finally {
        setLoading(false);
      }
    };

    loadLibrary();
  }, [showToast]);

  // Apply filters
  useEffect(() => {
    let result = library;

    if (filter !== 'all') {
      const typeMap: Record<string, string> = {
        movies: 'movie',
        tv: 'tv',
        anime: 'anime',
      };
      result = result.filter((item) => item.type === typeMap[filter]);
    }

    if (searchInput.trim()) {
      const query = searchInput.toLowerCase();
      result = result.filter((item) => item.title.toLowerCase().includes(query));
    }

    setFilteredLibrary(result);
  }, [library, filter, searchInput]);

  const handleRefresh = async () => {
    try {
      setLoading(true);
      const summary = await apiClient.refreshLibrary();
      const data = await apiClient.getLibrary(true);
      setLibrary(data);
      const msg = `Refreshed: ${summary.renamed} renamed, ${summary.posters_fetched} posters fetched`;
      showToast(msg, 'success');
    } catch (error) {
      showToast('Failed to refresh library', 'error');
      console.error('Refresh error:', error);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="space-y-6">
      {/* Controls */}
      <div className="card">
        <div className="flex items-center justify-between gap-4 flex-wrap">
          <input
            type="text"
            value={searchInput}
            onChange={(e) => setSearchInput(e.target.value)}
            placeholder="Search library..."
            className="input flex-1 min-w-48"
          />
          <div className="flex gap-2">
            {(['all', 'movies', 'tv', 'anime'] as const).map((type) => (
              <button
                key={type}
                onClick={() => setFilter(type)}
                className={`btn-sm capitalize ${
                  filter === type ? 'btn-sm-primary' : 'btn-sm-secondary'
                }`}
              >
                {type}
              </button>
            ))}
          </div>
          <button
            onClick={handleRefresh}
            disabled={loading}
            className="btn-primary disabled:opacity-50 disabled:cursor-not-allowed whitespace-nowrap"
          >
            {loading ? 'Refreshing...' : 'Refresh Library'}
          </button>
        </div>
      </div>

      {/* Media Grid */}
      {filteredLibrary.length === 0 ? (
        <div className="text-center py-12">
          <p className="text-dark-text/60">
            {library.length === 0
              ? 'Library is empty. Refresh to load media.'
              : 'No results found.'}
          </p>
        </div>
      ) : (
        <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 gap-4">
          {filteredLibrary.map((item) => (
            <button
              key={item.folder}
              onClick={() => setSelectedItem(item)}
              className="card-hover flex flex-col text-left"
            >
              {/* Poster Image */}
              <div className="mb-3 aspect-[2/3] rounded overflow-hidden bg-dark-bg">
                {item.poster ? (
                  <img
                    src={apiClient.getPosterUrl(item.poster)}
                    alt={item.title}
                    className="w-full h-full object-cover"
                  />
                ) : (
                  <div
                    className="w-full h-full flex items-center justify-center text-dark-bg font-bold text-2xl"
                    style={{ backgroundColor: hashColor(item.title) }}
                  >
                    {item.title.charAt(0).toUpperCase()}
                  </div>
                )}
              </div>

              {/* Info */}
              <div className="flex-1 min-w-0">
                <p className="font-semibold text-sm truncate text-dark-text">{item.title}</p>
                <div className="flex items-center gap-2 mt-1">
                  <span className="badge badge-accent text-xs capitalize">{item.type}</span>
                  {item.year && (
                    <span className="text-xs text-dark-text/60">{item.year}</span>
                  )}
                </div>
                <p className="text-xs text-dark-text/60 mt-1">
                  {item.file_count} file{item.file_count !== 1 ? 's' : ''} • {formatSize(item.size_bytes)}
                </p>
              </div>
            </button>
          ))}
        </div>
      )}

      {/* Media Detail Modal */}
      {selectedItem && (
        <MediaModal
          item={selectedItem}
          onClose={() => setSelectedItem(null)}
          onPlay={onPlay}
          showToast={showToast}
        />
      )}
    </div>
  );
}

export default LibraryTab;
