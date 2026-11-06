import React, { useState, useEffect, useRef, useCallback } from 'react';
import {
  Film,
  Sparkles,
  Layers,
  SlidersHorizontal,
  RotateCcw,
  Eye,
  Loader2,
  AlertCircle,
  HelpCircle,
  KeyRound,
  Bookmark,
  Heart,
  CheckCircle2,
} from 'lucide-react';
import { ContentTypeSelector, ContentType } from './ContentTypeSelector';
import { RegionFilter, RegionalCategory } from './RegionFilter';
import { FilterControls, FilterState } from './FilterControls';
import { SearchBar } from './SearchBar';
import { MovieGrid, GridViewStatus } from './MovieGrid';
import { MovieCard, MovieItemModel } from './MovieCard';
import { MovieDetailsModal } from './MovieDetailsModal';
import { MovieComparisonModal } from './MovieComparisonModal';
import { PreferencesModal } from './PreferencesModal';
import { AIRecommendationSection } from './AIRecommendationSection';
import { FullScreenPosterModal } from './FullScreenPosterModal';
import { OfflineBanner } from './OfflineBanner';
import { PaginationControls } from './PaginationControls';
import { useChatStore } from '../../store/useChatStore';
import { wsClient } from '../../api/websocket';
import {
  discoverMedia,
  searchMedia,
  fetchMovieConfig,
  clearMovieResultCache,
  checkNetworkStatus,
  MediaItemSummary,
  fetchTrackingSummary,
  TrackingSummary,
  fetchStoredEntries,
  addToWatchlist,
  removeFromWatchlist,
  setFavorite,
  markAsWatched,
  updateEntryStatus,
  normalizePosterUrl,
  normalizeBackdropUrl,
} from '../../api/movieApi';
import './MovieHubWorkspace.css';

export type HubMainTab = 'discover' | 'recommendations' | 'watchlist' | 'favorites' | 'watched';

const DEFAULT_FILTERS: FilterState = {
  language: 'all',
  genre: 'all',
  releaseYear: 'all',
  sortBy: 'popularity.desc',
};

const GENRE_KEYWORD_MAP: Record<string, string[]> = {
  '28': ['action'],
  '12': ['adventure'],
  '16': ['animation', 'animated', 'anime'],
  '35': ['comedy', 'comic', 'humor', 'sitcom', 'funny'],
  '80': ['crime', 'gangster', 'mafia', 'caper'],
  '99': ['documentary'],
  '18': ['drama', 'biopic', 'historical'],
  '14': ['fantasy', 'magic', 'mythological'],
  '27': ['horror', 'haunted', 'slasher', 'spooky', 'supernatural'],
  '9648': ['mystery', 'detective', 'whodunit', 'investigation'],
  '10749': ['romance', 'romantic', 'love', 'dating', 'marriage'],
  '878': ['sci-fi', 'science fiction', 'space', 'alien', 'cyberpunk', 'futuristic'],
  '53': ['thriller', 'suspense', 'psychological thriller'],
  '28|878': ['action', 'sci-fi', 'science fiction'],
  '80|53': ['crime', 'thriller', 'suspense'],
  '35|10749': ['rom-com', 'romantic comedy', 'romance', 'comedy'],
};

const matchesGenreFilter = (item: MovieItemModel, genreFilter: string): boolean => {
  if (!genreFilter || genreFilter === 'all') return true;

  const itemGenres = [
    ...(item.genreNames || []),
    ...((item as any).genres ? String((item as any).genres).split(/[,|]/).map((s: string) => s.trim()) : []),
  ].map((g) => g.toLowerCase());

  const searchHaystack = `${item.title} ${item.overview || ''} ${itemGenres.join(' ')}`.toLowerCase();

  if (genreFilter.includes('|')) {
    const parts = genreFilter.split('|');
    return parts.every((p) => {
      const words = GENRE_KEYWORD_MAP[p] || [p];
      return words.some((w) => itemGenres.some((g) => g.includes(w)) || searchHaystack.includes(w));
    });
  }

  const words = GENRE_KEYWORD_MAP[genreFilter] || [genreFilter.toLowerCase()];
  return words.some((w) => itemGenres.some((g) => g.includes(w)) || searchHaystack.includes(w));
};

const matchesRegionFilter = (itemLang: string | undefined, reg: RegionalCategory): boolean => {
  if (!reg || reg === 'all') return true;
  const lang = (itemLang || '').toLowerCase().trim();
  const indianLangs = ['hi', 'te', 'ta', 'ml', 'kn', 'bn', 'mr', 'pa', 'gu', 'or', 'as', 'ur'];
  const southIndianLangs = ['te', 'ta', 'ml', 'kn'];

  if (reg === 'indian') {
    return indianLangs.includes(lang);
  }
  if (reg === 'bollywood') {
    return lang === 'hi';
  }
  if (reg === 'south_indian') {
    return southIndianLangs.includes(lang);
  }
  if (reg === 'hollywood') {
    return lang === 'en';
  }
  if (reg === 'international') {
    return lang !== 'en' && !indianLangs.includes(lang);
  }
  return true;
};

const matchesYearFilter = (itemYear: string | number | undefined, filterYear: string): boolean => {
  if (!filterYear || filterYear === 'all') return true;
  const y = itemYear ? parseInt(String(itemYear), 10) : null;
  if (y === null || isNaN(y)) return false;

  if (/^\d{4}$/.test(filterYear)) {
    return y === parseInt(filterYear, 10);
  }
  if (filterYear === '2020s') return y >= 2020 && y <= 2029;
  if (filterYear === '2010s') return y >= 2010 && y <= 2019;
  if (filterYear === '2000s') return y >= 2000 && y <= 2009;
  if (filterYear === 'classic') return y < 2000;
  return true;
};

const matchesLanguageFilter = (itemLang: string | undefined, filterLang: string): boolean => {
  if (!filterLang || filterLang === 'all') return true;
  return (itemLang || '').toLowerCase().trim() === filterLang.toLowerCase().trim();
};

const matchesContentTypeFilter = (itemMediaType: 'movie' | 'tv', filterType: ContentType): boolean => {
  if (!filterType || filterType === 'all') return true;
  if (filterType === 'movies') return itemMediaType === 'movie';
  if (filterType === 'series') return itemMediaType === 'tv';
  return true;
};

const sortStoredItems = (storedList: MovieItemModel[], sortBy: string): MovieItemModel[] => {
  const sorted = [...storedList];
  if (sortBy === 'title.asc') {
    sorted.sort((a, b) => a.title.localeCompare(b.title));
  } else if (sortBy === 'vote_average.desc') {
    sorted.sort((a, b) => (b.voteAverage || 0) - (a.voteAverage || 0));
  } else if (sortBy === 'primary_release_date.desc') {
    sorted.sort((a, b) => (Number(b.releaseYear) || 0) - (Number(a.releaseYear) || 0));
  } else if (sortBy === 'primary_release_date.asc') {
    sorted.sort((a, b) => (Number(a.releaseYear) || 0) - (Number(b.releaseYear) || 0));
  } else if (sortBy === 'popularity.desc') {
    sorted.sort((a, b) => (b.voteAverage || 0) - (a.voteAverage || 0));
  }
  return sorted;
};

const SESSION_KEY_HUB_TAB = 'ai_friend_movie_hub_active_subtab';
const SESSION_KEY_CONTENT_TYPE = 'ai_friend_movie_hub_content_type';
const SESSION_KEY_REGION = 'ai_friend_movie_hub_region';
const SESSION_KEY_SEARCH = 'ai_friend_movie_hub_search_query';
const SESSION_KEY_SECONDARY_FILTERS = 'ai_friend_movie_hub_secondary_filters';
const SESSION_KEY_PAGE = 'ai_friend_movie_hub_current_page';

function getSessionItem<T>(key: string, fallback: T): T {
  try {
    const val = sessionStorage.getItem(key);
    if (val === null || val === undefined) return fallback;
    try {
      return JSON.parse(val);
    } catch {
      return val as unknown as T;
    }
  } catch {
    return fallback;
  }
}

function setSessionItem(key: string, val: any): void {
  try {
    if (val === null || val === undefined) {
      sessionStorage.removeItem(key);
    } else if (typeof val === 'string') {
      sessionStorage.setItem(key, val);
    } else {
      sessionStorage.setItem(key, JSON.stringify(val));
    }
  } catch {}
}

export const MovieHubWorkspace: React.FC = () => {
  const { openSettings } = useChatStore();
  // 1. Navigation, Format & Filter States with Session Memory Persistence
  const [hubTab, setHubTabState] = useState<HubMainTab>(() => getSessionItem(SESSION_KEY_HUB_TAB, 'discover'));
  const [contentType, setContentTypeState] = useState<ContentType>(() => getSessionItem(SESSION_KEY_CONTENT_TYPE, 'all'));
  const [region, setRegionState] = useState<RegionalCategory>(() => getSessionItem(SESSION_KEY_REGION, 'all'));
  const [searchQuery, setSearchQueryState] = useState<string>(() => getSessionItem(SESSION_KEY_SEARCH, ''));
  const [debouncedQuery, setDebouncedQuery] = useState<string>(() => getSessionItem(SESSION_KEY_SEARCH, ''));
  const [secondaryFilters, setSecondaryFiltersState] = useState<FilterState>(() => getSessionItem(SESSION_KEY_SECONDARY_FILTERS, DEFAULT_FILTERS));

  // 2. Pagination State with Session Memory
  const [currentPage, setCurrentPageState] = useState<number>(() => getSessionItem(SESSION_KEY_PAGE, 1));
  const [totalPages, setTotalPages] = useState<number>(1);
  const [totalResults, setTotalResults] = useState<number>(0);

  // Synchronized State Setters that persist to sessionStorage
  const setHubTab = (tab: HubMainTab) => {
    setHubTabState(tab);
    setSessionItem(SESSION_KEY_HUB_TAB, tab);
  };

  const setContentType = (type: ContentType) => {
    setContentTypeState(type);
    setSessionItem(SESSION_KEY_CONTENT_TYPE, type);
  };

  const setRegion = (newRegion: RegionalCategory) => {
    setRegionState(newRegion);
    setSessionItem(SESSION_KEY_REGION, newRegion);
  };

  const setSearchQuery = (q: string) => {
    setSearchQueryState(q);
    setSessionItem(SESSION_KEY_SEARCH, q);
  };

  const setSecondaryFilters = (val: FilterState | ((prev: FilterState) => FilterState)) => {
    setSecondaryFiltersState((prev) => {
      const next = typeof val === 'function' ? val(prev) : val;
      setSessionItem(SESSION_KEY_SECONDARY_FILTERS, next);
      return next;
    });
  };

  const setCurrentPage = (page: number) => {
    setCurrentPageState(page);
    setSessionItem(SESSION_KEY_PAGE, page);
  };

  // 3. Catalog Data & UI Status States
  const [items, setItems] = useState<MovieItemModel[]>([]);
  const [viewState, setViewState] = useState<GridViewStatus>('loading');
  const [errorMessage, setErrorMessage] = useState<string>('');
  const [isTmdbConfigured, setIsTmdbConfigured] = useState<boolean>(true);
  const [isOffline, setIsOffline] = useState<boolean>(!navigator.onLine);

  // 4. Details, Comparison, Preferences & Full-Screen Poster Modals State
  const [selectedMediaItem, setSelectedMediaItem] = useState<MovieItemModel | null>(null);
  const [isDetailsOpen, setIsDetailsOpen] = useState<boolean>(false);
  const [isPreferencesOpen, setIsPreferencesOpen] = useState<boolean>(false);
  const [isComparisonOpen, setIsComparisonOpen] = useState<boolean>(false);
  const [compareTitleA, setCompareTitleA] = useState<MovieItemModel | null>(null);
  const [compareTitleB, setCompareTitleB] = useState<MovieItemModel | null>(null);

  // Full-Screen Poster Lightbox state
  const [fullScreenPoster, setFullScreenPoster] = useState<{
    url: string | null;
    title: string;
    releaseYear?: string | number | null;
    mediaType?: string;
  } | null>(null);

  const handleOpenFullScreenPoster = (
    url: string | null | undefined,
    title: string,
    releaseYear?: string | number | null,
    mediaType?: string
  ) => {
    if (!url) return;
    setFullScreenPoster({ url, title, releaseYear, mediaType });
  };

  // 5. Persistent Local Storage Tracking State (Phase 8)
  const [trackingSummary, setTrackingSummary] = useState<TrackingSummary>({
    watchlist_ids: [],
    favorite_ids: [],
    watched_ids: [],
    user_ratings: {},
  });

  // 6. Request Concurrency & Race Condition Guards
  const activeRequestIdRef = useRef<number>(0);
  const abortControllerRef = useRef<AbortController | null>(null);

  // Load tracking summary from local SQLite
  const loadTrackingSummary = useCallback(() => {
    fetchTrackingSummary()
      .then((data) => setTrackingSummary(data))
      .catch((err) => console.debug('Tracking summary unavailable:', err));
  }, []);

  useEffect(() => {
    loadTrackingSummary();
  }, [loadTrackingSummary]);

  // Debounce search input to avoid flood during typing
  useEffect(() => {
    const timer = setTimeout(() => {
      setDebouncedQuery(searchQuery.trim());
    }, 350);
    return () => clearTimeout(timer);
  }, [searchQuery]);

  // Reset page when filter conditions change
  const handleContentTypeChange = (type: ContentType) => {
    setContentType(type);
    setCurrentPage(1);
  };

  const handleRegionChange = (newRegion: RegionalCategory) => {
    setRegion(newRegion);
    setCurrentPage(1);
  };

  const handleSecondaryFilterChange = (updated: Partial<FilterState>) => {
    setSecondaryFilters((prev) => ({ ...prev, ...updated }));
    setCurrentPage(1);
  };

  const handleResetAll = () => {
    setContentType('all');
    setRegion('all');
    setSearchQuery('');
    setDebouncedQuery('');
    setSecondaryFilters(DEFAULT_FILTERS);
    setCurrentPage(1);
  };

  const handleOpenDetails = (item: MovieItemModel) => {
    setSelectedMediaItem(item);
    setIsDetailsOpen(true);
  };

  const handleCloseDetails = () => {
    setIsDetailsOpen(false);
  };

  const handleStartCompare = (item: MovieItemModel) => {
    setCompareTitleA(item);
    setCompareTitleB(null);
    setIsComparisonOpen(true);
  };

  const handleSelectRelated = (item: MovieItemModel) => {
    setSelectedMediaItem(item);
  };

  // Card Bookmark Toggle Handler (Phase 8)
  const handleToggleWatchlistOnCard = async (item: MovieItemModel) => {
    const isWatchlisted = trackingSummary.watchlist_ids.includes(Number(item.id));
    try {
      if (isWatchlisted) {
        await removeFromWatchlist(item.mediaType, item.id);
      } else {
        await addToWatchlist({
          tmdb_id: Number(item.id),
          title: item.title,
          media_type: item.mediaType,
          poster_path: item.posterPath,
          release_year: typeof item.releaseYear === 'number' ? item.releaseYear : undefined,
          original_language: item.originalLanguage,
          vote_average: item.voteAverage,
          overview: item.overview,
          genres: item.genreNames?.join(', ') || item.genres || '',
        });
      }
      loadTrackingSummary();
      if (hubTab !== 'discover') {
        fetchCatalogData(true);
      }
    } catch (err) {
      console.error('Failed to toggle watchlist:', err);
    }
  };

  // Card Favorite Toggle Handler
  const handleToggleFavoriteOnCard = async (item: MovieItemModel) => {
    const isFavorited = trackingSummary.favorite_ids.includes(Number(item.id));
    try {
      const parsedYear =
        typeof item.releaseYear === 'number'
          ? item.releaseYear
          : item.releaseYear
          ? parseInt(String(item.releaseYear), 10)
          : undefined;

      await setFavorite(item.mediaType, item.id, !isFavorited, {
        title: item.title,
        poster_path: item.posterPath,
        backdrop_path: item.backdropPath,
        release_year: parsedYear,
        original_language: item.originalLanguage,
        vote_average: item.voteAverage,
        overview: item.overview,
        genres: item.genreNames?.join(', ') || item.genres || '',
      });
      loadTrackingSummary();
      if (hubTab !== 'discover') {
        fetchCatalogData(true);
      }
    } catch (err) {
      console.error('Failed to toggle favorite on card:', err);
    }
  };

  // Card Watched Toggle Handler
  const handleToggleWatchedOnCard = async (item: MovieItemModel) => {
    const isWatched = trackingSummary.watched_ids.includes(Number(item.id));
    try {
      if (isWatched) {
        await updateEntryStatus(item.mediaType, item.id, 'none');
      } else {
        const parsedYear =
          typeof item.releaseYear === 'number'
            ? item.releaseYear
            : item.releaseYear
            ? parseInt(String(item.releaseYear), 10)
            : undefined;

        await markAsWatched(item.mediaType, item.id, {
          title: item.title,
          poster_path: item.posterPath,
          backdrop_path: item.backdropPath,
          release_year: parsedYear,
          original_language: item.originalLanguage,
          vote_average: item.voteAverage,
          overview: item.overview,
          genres: item.genreNames?.join(', ') || item.genres || '',
        });
      }
      loadTrackingSummary();
      if (hubTab !== 'discover') {
        fetchCatalogData(true);
      }
    } catch (err) {
      console.error('Failed to toggle watched on card:', err);
    }
  };

  // Check if any filter is modified from defaults
  const isFiltersModified =
    contentType !== 'all' ||
    region !== 'all' ||
    searchQuery.trim() !== '' ||
    secondaryFilters.language !== 'all' ||
    secondaryFilters.genre !== 'all' ||
    secondaryFilters.releaseYear !== 'all' ||
    secondaryFilters.sortBy !== 'popularity.desc';

  // Core Data Fetching Procedure
  const fetchCatalogData = useCallback(
    async (bypassCache = false) => {
      // Cancel any ongoing in-flight request
      if (abortControllerRef.current) {
        abortControllerRef.current.abort();
      }
      const controller = new AbortController();
      abortControllerRef.current = controller;

      const requestId = ++activeRequestIdRef.current;
      setViewState('loading');
      setErrorMessage('');

      try {
        // Phase 9: AI Recommendations tab has its own dedicated interactive engine
        if (hubTab === 'recommendations') {
          setViewState('ready');
          return;
        }

        // Phase 8: Persistent Local Storage Tracking Views
        if (hubTab === 'watchlist' || hubTab === 'favorites' || hubTab === 'watched') {
          const stored = await fetchStoredEntries({
            status: hubTab === 'watchlist' ? 'watchlist' : hubTab === 'watched' ? 'watched' : undefined,
            is_favorite: hubTab === 'favorites' ? true : undefined,
          });

          if (requestId !== activeRequestIdRef.current) return;

          let mappedStored: MovieItemModel[] = stored.map((e) => ({
            id: e.tmdb_id,
            title: e.title,
            mediaType: e.media_type,
            posterPath: normalizePosterUrl(e.poster_url || e.poster_path, 'w500'),
            backdropPath: normalizeBackdropUrl(e.backdrop_url || e.backdrop_path, 'w1280'),
            releaseYear: e.release_year ?? undefined,
            voteAverage: e.user_rating ? e.user_rating : e.vote_average,
            overview: e.overview,
            originalLanguage: e.original_language ?? undefined,
            genres: (e as any).genres || '',
          }));

          // 1. Content format filter (ALL, ONLY MOVIES, ONLY SERIES)
          mappedStored = mappedStored.filter((item) => matchesContentTypeFilter(item.mediaType, contentType));

          // 2. Regional cinema filter (All Regions, Indian, Bollywood, South Indian, Hollywood, International)
          mappedStored = mappedStored.filter((item) => matchesRegionFilter(item.originalLanguage, region));

          // 3. Language dropdown filter
          mappedStored = mappedStored.filter((item) => matchesLanguageFilter(item.originalLanguage, secondaryFilters.language));

          // 4. Release year dropdown filter
          mappedStored = mappedStored.filter((item) => matchesYearFilter(item.releaseYear, secondaryFilters.releaseYear));

          // 5. Genre dropdown filter
          mappedStored = mappedStored.filter((item) => matchesGenreFilter(item, secondaryFilters.genre));

          // 6. Search query
          if (debouncedQuery) {
            const q = debouncedQuery.toLowerCase();
            mappedStored = mappedStored.filter(
              (item) =>
                item.title.toLowerCase().includes(q) ||
                (item.overview && item.overview.toLowerCase().includes(q))
            );
          }

          // 7. Sort
          mappedStored = sortStoredItems(mappedStored, secondaryFilters.sortBy);

          // 8. Pagination calculation
          const totalCount = mappedStored.length;
          const PAGE_SIZE = 49;
          const calculatedTotalPages = Math.max(1, Math.ceil(totalCount / PAGE_SIZE));
          const safePage = Math.min(Math.max(1, currentPage), calculatedTotalPages);
          const paginatedItems = mappedStored.slice((safePage - 1) * PAGE_SIZE, safePage * PAGE_SIZE);

          setItems(paginatedItems);
          setTotalPages(calculatedTotalPages);
          setTotalResults(totalCount);
          setViewState(totalCount === 0 ? 'empty' : 'ready');
          return;
        }

        let rawResults: MediaItemSummary[] = [];
        let fetchedTotalPages = 1;
        let fetchedTotalResults = 0;

        let isResponseStale = false;
        if (debouncedQuery) {
          // Search Mode (combined with compatible filters)
          const searchRes = await searchMedia(
            {
              query: debouncedQuery,
              content_type: contentType,
              language: secondaryFilters.language !== 'all' ? secondaryFilters.language : undefined,
              year: secondaryFilters.releaseYear !== 'all' ? secondaryFilters.releaseYear : undefined,
              page: currentPage,
              page_size: 49,
            },
            { signal: controller.signal, bypassCache }
          );

          if (requestId !== activeRequestIdRef.current) return; // Stale response discarded

          rawResults = searchRes.results || [];
          fetchedTotalPages = searchRes.total_pages || 1;
          fetchedTotalResults = searchRes.total_results || 0;
          if (searchRes.is_stale) isResponseStale = true;
        } else {
          // Discover Mode
          const discoverRes = await discoverMedia(
            {
              content_type: contentType,
              region: region,
              language: secondaryFilters.language,
              genre: secondaryFilters.genre,
              year: secondaryFilters.releaseYear,
              sort_by: secondaryFilters.sortBy,
              page: currentPage,
              page_size: 49,
            },
            { signal: controller.signal, bypassCache }
          );

          if (requestId !== activeRequestIdRef.current) return; // Stale response discarded

          rawResults = discoverRes.results || [];
          fetchedTotalPages = discoverRes.total_pages || 1;
          fetchedTotalResults = discoverRes.total_results || 0;
          if (discoverRes.is_stale) isResponseStale = true;
        }

        if (isResponseStale) {
          setIsOffline(true);
        }

        // Map and validate MediaItemSummary to UI MovieItemModel
        let mapped: MovieItemModel[] = rawResults.map((m) => ({
          id: m.id,
          title: m.title,
          mediaType: m.media_type,
          posterPath: m.poster_url || (m.poster_path ? `https://image.tmdb.org/t/p/w500${m.poster_path}` : null),
          backdropPath: m.backdrop_url || (m.backdrop_path ? `https://image.tmdb.org/t/p/w1280${m.backdrop_path}` : null),
          releaseYear: m.release_year || (m.release_date ? m.release_date.slice(0, 4) : undefined),
          voteAverage: m.vote_average,
          overview: m.overview,
          originalLanguage: m.original_language || undefined,
          isStale: isResponseStale || (m as any).is_stale || false,
        }));

        // Strict content-type defensive filtering
        if (contentType === 'movies') {
          mapped = mapped.filter((item) => item.mediaType === 'movie');
        } else if (contentType === 'series') {
          mapped = mapped.filter((item) => item.mediaType === 'tv');
        }

        // Local sorting strategy for search results or title sort
        if (secondaryFilters.sortBy === 'title.asc') {
          mapped.sort((a, b) => a.title.localeCompare(b.title));
        } else if (debouncedQuery && secondaryFilters.sortBy === 'vote_average.desc') {
          mapped.sort((a, b) => (b.voteAverage || 0) - (a.voteAverage || 0));
        } else if (debouncedQuery && secondaryFilters.sortBy.includes('release_date')) {
          mapped.sort((a, b) => String(b.releaseYear || '').localeCompare(String(a.releaseYear || '')));
        }

        if (requestId === activeRequestIdRef.current) {
          setItems(mapped);
          setTotalPages(fetchedTotalPages);
          setTotalResults(fetchedTotalResults);
          setIsTmdbConfigured(true);

          if (mapped.length === 0) {
            setViewState('empty');
          } else {
            setViewState('ready');
          }
        }
      } catch (err: any) {
        if (err.name === 'AbortError') {
          return; // Intentionally aborted; do not show error
        }
        if (requestId === activeRequestIdRef.current) {
          const errMsg = err?.message || 'Failed to retrieve media catalog from API.';
          setErrorMessage(errMsg);
          if (errMsg.includes('401') || errMsg.toLowerCase().includes('api key')) {
            setIsTmdbConfigured(false);
          }
          setViewState('error');
        }
      }
    },
    [
      hubTab,
      contentType,
      region,
      debouncedQuery,
      secondaryFilters.language,
      secondaryFilters.genre,
      secondaryFilters.releaseYear,
      secondaryFilters.sortBy,
      currentPage,
    ]
  );

  // Trigger data fetch on relevant dependencies change
  useEffect(() => {
    fetchCatalogData();
    return () => {
      if (abortControllerRef.current) {
        abortControllerRef.current.abort();
      }
    };
  }, [fetchCatalogData]);

  // Phase 10: Online / Offline Network Monitoring & Dynamic Probing
  useEffect(() => {
    const handleOnline = () => {
      setIsOffline(false);
      fetchCatalogData(true);
    };
    const handleOffline = () => {
      setIsOffline(true);
    };

    window.addEventListener('online', handleOnline);
    window.addEventListener('offline', handleOffline);

    // Initial low-overhead network status probe
    checkNetworkStatus()
      .then((status) => {
        setIsOffline(!status.online);
        setIsTmdbConfigured(status.configured);
      })
      .catch(() => {
        setIsOffline(!navigator.onLine);
      });

    return () => {
      window.removeEventListener('online', handleOnline);
      window.removeEventListener('offline', handleOffline);
    };
  }, [fetchCatalogData]);

  // Phase 11.3: Voice-Powered Discovery & System Event Interception
  useEffect(() => {
    const unsubscribe = wsClient.subscribe((type, data) => {
      if (type === 'movie_voice_search' && data?.query) {
        setHubTab('discover');
        setSearchQuery(data.query);
        setCurrentPage(1);
      } else if (type === 'open_movie_hub') {
        if (typeof window !== 'undefined' && (window as any).openMovieHub) {
          (window as any).openMovieHub();
        }
      }
    });

    const handleCustomVoiceSearch = (e: any) => {
      if (e?.detail?.query) {
        setHubTab('discover');
        setSearchQuery(e.detail.query);
        setCurrentPage(1);
      }
    };

    window.addEventListener('movie-voice-search', handleCustomVoiceSearch);

    return () => {
      unsubscribe();
      window.removeEventListener('movie-voice-search', handleCustomVoiceSearch);
    };
  }, []);

  // Handle retry action
  const handleRetry = () => {
    fetchCatalogData(true);
  };

  return (
    <div className="movie-hub-container" role="region" aria-label="Movie Hub Discovery Workspace">
      {/* ===================================================================
          1. Workspace Header: Title, Icon Badge & Accessible Search Bar
          =================================================================== */}
      <header className="movie-hub-header">
        <div className="movie-hub-title-block">
          <div className="movie-hub-icon-badge" aria-hidden="true">
            <Film size={18} className="hub-badge-glyph" />
          </div>
          <div className="movie-hub-title-meta">
            <div className="hub-title-row">
              <h1 className="movie-hub-main-title">Movie Hub</h1>
              <span className="hub-shell-tag">Real TMDB</span>
            </div>
          </div>
        </div>

        {/* Phase 8: Hub Navigation View Switcher (Discover vs Watchlist vs Favorites vs Watched) & Preferences */}
        <div className="hub-header-tabs-group">
          <div className="hub-view-tabs" role="tablist" aria-label="Library & Discovery views">
            <button
              type="button"
              className={`hub-view-tab-btn ${hubTab === 'discover' ? 'active' : ''}`}
              onClick={() => {
                setHubTab('discover');
                setCurrentPage(1);
              }}
              role="tab"
              aria-selected={hubTab === 'discover'}
            >
              <Film size={13} />
              <span>Discover</span>
            </button>
            <button
              type="button"
              className={`hub-view-tab-btn hub-ai-tab-btn ${hubTab === 'recommendations' ? 'active-ai' : ''}`}
              onClick={() => {
                setHubTab('recommendations');
              }}
              role="tab"
              aria-selected={hubTab === 'recommendations'}
            >
              <Sparkles size={13} style={{ color: hubTab === 'recommendations' ? '#BF5AF2' : 'inherit' }} />
              <span>AI Recommendations</span>
            </button>
            <button
              type="button"
              className={`hub-view-tab-btn ${hubTab === 'watchlist' ? 'active' : ''}`}
              onClick={() => {
                setHubTab('watchlist');
                setCurrentPage(1);
              }}
              role="tab"
              aria-selected={hubTab === 'watchlist'}
            >
              <Bookmark size={13} />
              <span>Watchlist</span>
              {trackingSummary.watchlist_ids.length > 0 && (
                <span className="hub-tab-badge">{trackingSummary.watchlist_ids.length}</span>
              )}
            </button>
            <button
              type="button"
              className={`hub-view-tab-btn ${hubTab === 'favorites' ? 'active' : ''}`}
              onClick={() => {
                setHubTab('favorites');
                setCurrentPage(1);
              }}
              role="tab"
              aria-selected={hubTab === 'favorites'}
            >
              <Heart size={13} />
              <span>Favorites</span>
              {trackingSummary.favorite_ids.length > 0 && (
                <span className="hub-tab-badge">{trackingSummary.favorite_ids.length}</span>
              )}
            </button>
            <button
              type="button"
              className={`hub-view-tab-btn ${hubTab === 'watched' ? 'active' : ''}`}
              onClick={() => {
                setHubTab('watched');
                setCurrentPage(1);
              }}
              role="tab"
              aria-selected={hubTab === 'watched'}
            >
              <CheckCircle2 size={13} />
              <span>Watched</span>
              {trackingSummary.watched_ids.length > 0 && (
                <span className="hub-tab-badge">{trackingSummary.watched_ids.length}</span>
              )}
            </button>
          </div>

          <button
            type="button"
            className="hub-preferences-trigger-btn"
            onClick={() => setIsPreferencesOpen(true)}
            title="Configure Entertainment Preferences"
          >
            <SlidersHorizontal size={13} />
            <span className="hub-preferences-text">Preferences</span>
          </button>
        </div>

        {/* Search Bar Reusable Component */}
        <div className="hub-search-slot">
          <SearchBar
            value={searchQuery}
            onChange={(val) => {
              setSearchQuery(val);
              setCurrentPage(1);
            }}
            onClear={() => {
              setSearchQuery('');
              setDebouncedQuery('');
              setCurrentPage(1);
            }}
            onSubmit={(val) => {
              setDebouncedQuery(val.trim());
              setCurrentPage(1);
            }}
            placeholder="Search titles, directors, actors across movies & TV..."
          />
        </div>
      </header>

      {/* ===================================================================
          2. Primary & Regional Filter Controls
          =================================================================== */}
      {hubTab !== 'recommendations' && (
        <section className="movie-hub-filter-shelf" aria-label="Catalog Filters">
          <div className="hub-filter-row-primary">
            {/* Format Selector: ALL, ONLY MOVIES, ONLY SERIES */}
            <div className="hub-control-unit">
              <ContentTypeSelector value={contentType} onChange={handleContentTypeChange} />
            </div>

            <div className="hub-shelf-divider" aria-hidden="true" />

            {/* Regional Cinema Category Selector */}
            <div className="hub-control-unit hub-region-unit">
              <RegionFilter value={region} onChange={handleRegionChange} />
            </div>
          </div>

          {/* Secondary Compact Filters: Language, Genre, Year, Sort & Reset */}
          <div className="hub-filter-row-secondary">
            <FilterControls
              filters={secondaryFilters}
              onChange={handleSecondaryFilterChange}
              onReset={handleResetAll}
              isModified={isFiltersModified}
            />
          </div>
        </section>
      )}

      {/* ===================================================================
          3. Main Scrollable Content Viewport
          =================================================================== */}
      <main className="movie-hub-content-viewport">
        {/* Phase 10: Proactive Offline State Banner with Retry */}
        <OfflineBanner
          isOffline={isOffline}
          onRetry={async () => {
            const status = await checkNetworkStatus();
            if (status.online) {
              setIsOffline(false);
            }
            await fetchCatalogData(true);
          }}
          cachedCount={items.length}
        />

        {/* Destination 1: AI Recommendations Section (Retained in DOM across tab switches to preserve user drafts) */}
        <div
          className="hub-recommendations-wrapper"
          style={{ display: hubTab === 'recommendations' ? 'block' : 'none' }}
          aria-hidden={hubTab !== 'recommendations'}
        >
          <AIRecommendationSection
            onOpenDetails={handleOpenDetails}
            onToggleWatchlist={handleToggleWatchlistOnCard}
            onToggleFavorite={handleToggleFavoriteOnCard}
            onToggleWatched={handleToggleWatchedOnCard}
            onOpenPoster={(item) =>
              handleOpenFullScreenPoster(item.posterPath, item.title, item.releaseYear, item.mediaType)
            }
            watchlistIds={new Set(trackingSummary.watchlist_ids)}
            favoriteIds={new Set(trackingSummary.favorite_ids)}
            watchedIds={new Set(trackingSummary.watched_ids)}
          />
        </div>

        {/* Destination 2: Standard Catalog View (Discover, Watchlist, Favorites, Watched) */}
        <div
          className="hub-catalog-wrapper"
          style={{ display: hubTab !== 'recommendations' ? 'contents' : 'none' }}
          aria-hidden={hubTab === 'recommendations'}
        >
          {/* Unconfigured TMDB API Key Warning Banner if applicable */}
          {!isTmdbConfigured && (
            <section className="hub-ai-teaser-banner" style={{ borderColor: 'rgba(255, 159, 10, 0.4)', background: 'linear-gradient(135deg, rgba(255, 159, 10, 0.12) 0%, rgba(255, 69, 58, 0.08) 100%)' }} aria-label="Configuration Banner">
              <div className="hub-ai-teaser-icon" style={{ background: 'rgba(255, 159, 10, 0.2)', borderColor: 'rgba(255, 159, 10, 0.4)' }}>
                <KeyRound size={18} style={{ color: '#FF9F0A' }} />
              </div>
              <div className="hub-ai-teaser-content">
                <span className="hub-ai-teaser-title" style={{ color: '#FF9F0A' }}>TMDB API Key Required</span>
                <p className="hub-ai-teaser-desc">
                  To discover live movies, television series, and streaming availability, configure your TMDB API key in Settings &rarr; Movie Hub.
                </p>
                <button
                  type="button"
                  className="hub-preferences-trigger-btn"
                  style={{ marginTop: '8px' }}
                  onClick={() => openSettings('movie_hub')}
                >
                  <KeyRound size={13} />
                  <span>Configure Key in Settings</span>
                </button>
              </div>
            </section>
          )}

          {/* Featured Showcase Section */}
          <section className="hub-featured-container" aria-label="Featured Media Highlights">
            <div className="hub-featured-card">
              <div className="hub-featured-meta">
                <span className="hub-featured-badge">Featured Showcase</span>
                <h2 className="hub-featured-headline">Cinematic Horizons</h2>
                <p className="hub-featured-description">
                  Explore thousands of verified titles across Bollywood, Tollywood, Kollywood, Mollywood, Sandalwood, Hollywood, and global cinema with personalized Ollama recommendations.
                </p>
              </div>
              <div className="hub-featured-ambient" aria-hidden="true" />
            </div>
          </section>

          {/* Media Catalog Section */}
          <section className="hub-catalog-section" aria-label="Media Results Catalog">
            <div className="hub-catalog-header-bar">
              <div className="hub-catalog-title-group">
                <h3 className="hub-catalog-heading">
                  {debouncedQuery ? `Search Results for "${debouncedQuery}"` : 'Browse Catalog'}
                </h3>
                <div className="hub-active-filter-tags">
                  <span className="hub-filter-tag tag-format">
                    Format: {contentType.toUpperCase()}
                  </span>
                  <span className="hub-filter-tag tag-region">
                    Region: {region.replace('_', ' ').toUpperCase()}
                  </span>
                  {secondaryFilters.language !== 'all' && (
                    <span className="hub-filter-tag tag-lang">
                      Lang: {secondaryFilters.language.toUpperCase()}
                    </span>
                  )}
                  {secondaryFilters.genre !== 'all' && (
                    <span className="hub-filter-tag tag-genre">
                      Genre: {secondaryFilters.genre}
                    </span>
                  )}
                  {secondaryFilters.releaseYear !== 'all' && (
                    <span className="hub-filter-tag tag-year">
                      Year: {secondaryFilters.releaseYear}
                    </span>
                  )}
                  <span className="hub-filter-tag tag-sort">
                    Sort: {secondaryFilters.sortBy.replace('.desc', ' ↓').replace('.asc', ' ↑')}
                  </span>
                </div>
              </div>
            </div>

            {/* Reusable Movie Grid delegating to MovieCard / LoadingSkeleton / EmptyState / ErrorState */}
            <div className="hub-catalog-grid-wrapper">
              <MovieGrid
                status={viewState}
                items={items}
                errorMessage={errorMessage}
                onRetry={handleRetry}
                onResetFilters={handleResetAll}
                onOpenDetails={handleOpenDetails}
                onOpenPoster={(item) =>
                  handleOpenFullScreenPoster(item.posterPath, item.title, item.releaseYear, item.mediaType)
                }
                onToggleWatchlist={handleToggleWatchlistOnCard}
                onToggleFavorite={handleToggleFavoriteOnCard}
                onToggleWatched={handleToggleWatchedOnCard}
                onCompare={handleStartCompare}
                watchlistIds={new Set(trackingSummary.watchlist_ids)}
                favoriteIds={new Set(trackingSummary.favorite_ids)}
                watchedIds={new Set(trackingSummary.watched_ids)}
                emptyTitle={
                  debouncedQuery
                    ? `No titles found matching "${debouncedQuery}"`
                    : isFiltersModified
                      ? 'No titles match current filter criteria'
                      : hubTab === 'watchlist'
                        ? 'Your Watchlist is Empty'
                        : hubTab === 'favorites'
                          ? 'No Favorite Titles Saved'
                          : hubTab === 'watched'
                            ? 'No Watched Titles Recorded'
                            : 'Ready for Catalog Discovery'
                }
                emptyDescription={
                  debouncedQuery || isFiltersModified
                    ? 'Try selecting "ALL" format, choosing different regions, or clearing specific genre/year filters to broaden results.'
                    : hubTab === 'watchlist'
                      ? 'Browse the catalog and click the bookmark button on any title or inside details to save it to your local watchlist.'
                      : hubTab === 'favorites'
                        ? 'Mark any title as a favorite from its details view to quickly find your top entertainment.'
                        : hubTab === 'watched'
                          ? 'Mark titles as watched to keep track of movies and series you have completed.'
                          : 'Select a content format, regional cinema industry, or search query to explore titles.'
                }
              />

              {/* Pagination Controls */}
              {viewState === 'ready' && items.length > 0 && totalPages > 1 && (
                <PaginationControls
                  currentPage={currentPage}
                  totalPages={totalPages}
                  totalResults={totalResults}
                  onPageChange={(page) => setCurrentPage(page)}
                  isLoading={false}
                />
              )}
            </div>
          </section>
        </div>
      </main>

      {/* ===================================================================
          4. Footer: Legal Attribution & Compliance
          =================================================================== */}
      <footer className="movie-hub-footer">
        <span className="hub-footer-text">
          Movie Hub &bull; Powered by TMDB Metadata & Local Ollama AI
        </span>
        <span className="hub-footer-disclaimer">
          This product uses the TMDB API but is not endorsed or certified by TMDB.
        </span>
      </footer>

      {/* ===================================================================
          5. Movie / Series Details Modal (Phase 7 & 8)
          =================================================================== */}
      <MovieDetailsModal
        item={selectedMediaItem}
        isOpen={isDetailsOpen}
        onClose={handleCloseDetails}
        onSelectRelated={handleSelectRelated}
        onTrackingChanged={() => {
          loadTrackingSummary();
          if (hubTab !== 'discover') {
            fetchCatalogData(true);
          }
        }}
        onStartCompare={handleStartCompare}
      />

      {/* ===================================================================
          6. Entertainment Preferences Modal (Phase 8)
          =================================================================== */}
      <PreferencesModal
        isOpen={isPreferencesOpen}
        onClose={() => setIsPreferencesOpen(false)}
        onPreferencesSaved={() => {
          loadTrackingSummary();
          fetchCatalogData(true);
        }}
      />

      {/* ===================================================================
          7. Movie Comparison Modal (Phase 11.5)
          =================================================================== */}
      <MovieComparisonModal
        isOpen={isComparisonOpen}
        onClose={() => setIsComparisonOpen(false)}
        initialTitleA={compareTitleA}
        initialTitleB={compareTitleB}
        onOpenDetails={handleOpenDetails}
      />

      {/* ===================================================================
          8. Full-Screen Poster Viewer Lightbox
          =================================================================== */}
      <FullScreenPosterModal
        isOpen={Boolean(fullScreenPoster)}
        posterUrl={fullScreenPoster?.url || null}
        title={fullScreenPoster?.title || ''}
        releaseYear={fullScreenPoster?.releaseYear}
        mediaType={fullScreenPoster?.mediaType}
        onClose={() => setFullScreenPoster(null)}
      />
    </div>
  );
};

export default MovieHubWorkspace;
