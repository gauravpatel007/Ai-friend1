/**
 * Movie Hub API Client
 * Connects frontend UI to the FastAPI movie service endpoints (/api/movies/*).
 * Implements request deduplication, in-memory caching, stale response protection,
 * and error normalization.
 */

export interface MediaItemSummary {
  id: number;
  title: string;
  original_title?: string | null;
  media_type: 'movie' | 'tv';
  overview: string;
  poster_path?: string | null;
  backdrop_path?: string | null;
  poster_url?: string | null;
  backdrop_url?: string | null;
  release_date?: string | null;
  release_year?: number | null;
  original_language?: string | null;
  genre_ids: number[];
  genre_names?: string[];
  keywords?: string[];
  vote_average: number;
  vote_count: number;
  popularity: number;
}

export interface PagedMovieResult {
  page: number;
  total_pages: number;
  total_results: number;
  results: MediaItemSummary[];
  is_stale?: boolean;
}

export interface GenreModel {
  id: number;
  name: string;
}

export interface CastMemberModel {
  id: number;
  name: string;
  character?: string | null;
  profile_path?: string | null;
  profile_url?: string | null;
  order?: number;
}

export interface VideoModel {
  id: string;
  key: string;
  name: string;
  site: string;
  type: string;
  official: boolean;
  url?: string | null;
}

export interface MediaDetailsModel extends MediaItemSummary {
  tagline?: string | null;
  runtime_minutes?: number | null;
  status?: string | null;
  genres: GenreModel[];
  cast: CastMemberModel[];
  directors: string[];
  trailers: VideoModel[];
  similar: MediaItemSummary[];
  number_of_seasons?: number | null;
  number_of_episodes?: number | null;
}

export interface WatchProviderItem {
  provider_id: number;
  provider_name: string;
  logo_path?: string | null;
  logo_url?: string | null;
  display_priority: number;
}

export interface WatchProvidersModel {
  id: number;
  region: string;
  tmdb_link?: string | null;
  flatrate: WatchProviderItem[];
  rent: WatchProviderItem[];
  buy: WatchProviderItem[];
  attribution: string;
}

export interface WatchProviderConfigItem {
  key: string;
  label: string;
  template: string;
  default_template: string;
  is_custom: boolean;
  description: string;
  sample_preview?: string;
}

export interface WatchProviderTemplatesResponse {
  providers: WatchProviderConfigItem[];
  sample_title: string;
  custom_count: number;
}

export interface TMDBConfigStatus {
  configured: boolean;
  image_base_url: string;
}

export interface DiscoverParams {
  content_type?: 'all' | 'movies' | 'series';
  region?: string;
  language?: string;
  genre?: string;
  year?: string;
  sort_by?: string;
  page?: number;
  page_size?: number;
}

export interface SearchParams {
  query: string;
  content_type?: 'all' | 'movies' | 'series';
  language?: string;
  year?: string;
  page?: number;
  page_size?: number;
}

const BASE_URL = '/api/movies';
const CACHE_TTL_MS = 5 * 60 * 1000; // 5 minutes frontend memory cache

interface CacheEntry {
  timestamp: number;
  data: PagedMovieResult;
}

const resultCache = new Map<string, CacheEntry>();
const detailsCache = new Map<string, { timestamp: number; data: MediaDetailsModel }>();
const providersCache = new Map<string, { timestamp: number; data: WatchProvidersModel }>();

// Phase 10: In-flight request deduplication map to prevent redundant concurrent fetches
const inFlightRequests = new Map<string, Promise<any>>();

function deduplicatedFetch<T>(key: string, fetchFn: () => Promise<T>): Promise<T> {
  const existing = inFlightRequests.get(key);
  if (existing) {
    return existing as Promise<T>;
  }
  const promise = fetchFn().finally(() => {
    inFlightRequests.delete(key);
  });
  inFlightRequests.set(key, promise);
  return promise;
}

/**
 * Generate a deterministic cache key from parameters.
 */
function buildCacheKey(prefix: string, params: Record<string, any>): string {
  const sortedKeys = Object.keys(params).sort();
  const serialized = sortedKeys.map((k) => `${k}=${encodeURIComponent(String(params[k] ?? ''))}`).join('&');
  return `${prefix}:${serialized}`;
}

/**
 * Cleanly resolve full image URL or relative path, correcting double-prefix anomalies.
 */
export function normalizePosterUrl(urlOrPath?: string | null, size: string = 'w500'): string | null {
  if (!urlOrPath) return null;
  let str = urlOrPath.trim();
  if (!str) return null;

  // Clean duplicate http prefixes if present (e.g. https://image.tmdb.org/t/p/w500https://...)
  while (str.includes('http://') && str.indexOf('http://') !== str.lastIndexOf('http://')) {
    str = str.slice(str.lastIndexOf('http://'));
  }
  while (str.includes('https://') && str.indexOf('https://') !== str.lastIndexOf('https://')) {
    str = str.slice(str.lastIndexOf('https://'));
  }

  if (str.startsWith('http://') || str.startsWith('https://') || str.startsWith('/api/')) {
    return str;
  }

  const clean = str.replace(/^\/+/, '');
  return `https://image.tmdb.org/t/p/${size}/${clean}`;
}

export function normalizeBackdropUrl(urlOrPath?: string | null, size: string = 'w1280'): string | null {
  return normalizePosterUrl(urlOrPath, size);
}

/**
 * Phase 10: Convert TMDB image path or URL to local caching image proxy.
 * Ensures images load offline from bounded disk cache and avoid redundant downloads.
 */
export function getProxiedImageUrl(
  imagePath: string | null | undefined,
  size: 'w185' | 'w342' | 'w500' | 'w780' | 'w1280' | 'original' = 'w500'
): string | null {
  if (!imagePath) return null;
  let clean = imagePath.trim();
  if (!clean) return null;

  // Clean duplicate prefixes
  while (clean.includes('http://') && clean.indexOf('http://') !== clean.lastIndexOf('http://')) {
    clean = clean.slice(clean.lastIndexOf('http://'));
  }
  while (clean.includes('https://') && clean.indexOf('https://') !== clean.lastIndexOf('https://')) {
    clean = clean.slice(clean.lastIndexOf('https://'));
  }

  if (clean.startsWith('/api/movies/images')) return clean;

  if (clean.includes('/t/p/')) {
    const parts = clean.split('/t/p/');
    const pathAfterSize = parts[1].replace(/^w\d+\//, '').replace(/^original\//, '');
    clean = pathAfterSize;
  } else if (clean.startsWith('http://') || clean.startsWith('https://')) {
    return clean;
  }

  clean = clean.replace(/^\/+/, '');
  return `${BASE_URL}/images/${size}/${clean}`;
}

/**
 * Check if the backend TMDB integration is configured with an active API key.
 */
export async function fetchMovieConfig(signal?: AbortSignal): Promise<TMDBConfigStatus> {
  const res = await fetch(`${BASE_URL}/config`, { signal });
  if (!res.ok) {
    throw new Error(`Failed to check TMDB configuration: HTTP ${res.status}`);
  }
  return res.json();
}

/**
 * Discover movies, series, or combined catalog using backend filters and pagination.
 * Results are cached in memory and request deduplication prevents duplicate in-flight requests.
 */
export async function discoverMedia(
  params: DiscoverParams,
  options?: { signal?: AbortSignal; bypassCache?: boolean }
): Promise<PagedMovieResult> {
  const cacheKey = buildCacheKey('discover', params);

  if (!options?.bypassCache) {
    const cached = resultCache.get(cacheKey);
    if (cached && Date.now() - cached.timestamp < CACHE_TTL_MS) {
      return cached.data;
    }
  }

  return deduplicatedFetch(cacheKey, async () => {
    const queryParams = new URLSearchParams();
    if (params.content_type) queryParams.set('content_type', params.content_type);
    if (params.region) queryParams.set('region', params.region);
    if (params.language) queryParams.set('language', params.language);
    if (params.genre) queryParams.set('genre', params.genre);
    if (params.year) queryParams.set('year', params.year);
    if (params.sort_by) queryParams.set('sort_by', params.sort_by);
    if (params.page) queryParams.set('page', String(params.page));
    queryParams.set('page_size', String(params.page_size ?? 49));

    const res = await fetch(`${BASE_URL}/discover?${queryParams.toString()}`, {
      signal: options?.signal,
    });

    if (!res.ok) {
      let detail = '';
      try {
        const errJson = await res.json();
        detail = errJson.detail || '';
      } catch {
        detail = await res.text();
      }
      throw new Error(detail || `HTTP ${res.status}: ${res.statusText}`);
    }

    const data: PagedMovieResult = await res.json();
    if ((data as any)._is_stale) {
      data.is_stale = true;
    }
    resultCache.set(cacheKey, { timestamp: Date.now(), data });
    return data;
  });
}

/**
 * Search movies, TV series, or combined titles matching query.
 * Results are cached in memory and in-flight calls are deduplicated.
 */
export async function searchMedia(
  params: SearchParams,
  options?: { signal?: AbortSignal; bypassCache?: boolean }
): Promise<PagedMovieResult> {
  if (!params.query.trim()) {
    return { page: 1, total_pages: 1, total_results: 0, results: [] };
  }

  const cacheKey = buildCacheKey('search', params);

  if (!options?.bypassCache) {
    const cached = resultCache.get(cacheKey);
    if (cached && Date.now() - cached.timestamp < CACHE_TTL_MS) {
      return cached.data;
    }
  }

  return deduplicatedFetch(cacheKey, async () => {
    const queryParams = new URLSearchParams();
    queryParams.set('query', params.query.trim());
    if (params.content_type) queryParams.set('content_type', params.content_type);
    if (params.language) queryParams.set('language', params.language);
    if (params.year) queryParams.set('year', params.year);
    if (params.page) queryParams.set('page', String(params.page));
    queryParams.set('page_size', String(params.page_size ?? 49));

    const res = await fetch(`${BASE_URL}/search?${queryParams.toString()}`, {
      signal: options?.signal,
    });

    if (!res.ok) {
      let detail = '';
      try {
        const errJson = await res.json();
        detail = errJson.detail || '';
      } catch {
        detail = await res.text();
      }
      throw new Error(detail || `HTTP ${res.status}: ${res.statusText}`);
    }

    const data: PagedMovieResult = await res.json();
    if ((data as any)._is_stale) {
      data.is_stale = true;
    }
    resultCache.set(cacheKey, { timestamp: Date.now(), data });
    return data;
  });
}

/**
 * Fetch rich details for a movie or TV series including cast, directors, trailers, and similar titles.
 */
export async function fetchMediaDetails(
  mediaType: 'movie' | 'tv',
  itemId: number | string,
  options?: { signal?: AbortSignal; bypassCache?: boolean }
): Promise<MediaDetailsModel> {
  const normType = mediaType === 'tv' ? 'tv' : 'movie';
  const cacheKey = `details:${normType}:${itemId}`;

  if (!options?.bypassCache) {
    const cached = detailsCache.get(cacheKey);
    if (cached && Date.now() - cached.timestamp < CACHE_TTL_MS) {
      return cached.data;
    }
  }

  return deduplicatedFetch(cacheKey, async () => {
    const res = await fetch(`${BASE_URL}/${normType}/${itemId}`, {
      signal: options?.signal,
    });

    if (!res.ok) {
      let detail = '';
      try {
        const errJson = await res.json();
        detail = errJson.detail || '';
      } catch {
        detail = await res.text();
      }
      throw new Error(detail || `Failed to fetch ${normType} details: HTTP ${res.status}`);
    }

    const data: MediaDetailsModel = await res.json();
    detailsCache.set(cacheKey, { timestamp: Date.now(), data });
    return data;
  });
}

/**
 * Fetch streaming, rental, and buy availability powered by JustWatch via TMDB.
 */
export async function fetchWatchProviders(
  mediaType: 'movie' | 'tv',
  itemId: number | string,
  region: string = 'IN',
  options?: { signal?: AbortSignal; bypassCache?: boolean }
): Promise<WatchProvidersModel> {
  const normType = mediaType === 'tv' ? 'tv' : 'movie';
  const cacheKey = `providers:${normType}:${itemId}:${region}`;

  if (!options?.bypassCache) {
    const cached = providersCache.get(cacheKey);
    if (cached && Date.now() - cached.timestamp < CACHE_TTL_MS) {
      return cached.data;
    }
  }

  return deduplicatedFetch(cacheKey, async () => {
    const res = await fetch(
      `${BASE_URL}/${normType}/${itemId}/watch-providers?region=${encodeURIComponent(region)}`,
      { signal: options?.signal }
    );
    if (!res.ok) {
      return {
        id: Number(itemId),
        region,
        flatrate: [],
        rent: [],
        buy: [],
        attribution: 'Streaming availability data provided by JustWatch via TMDB.',
      };
    }
    const data: WatchProvidersModel = await res.json();
    providersCache.set(cacheKey, { timestamp: Date.now(), data });
    return data;
  });
}

/**
 * Clear both frontend memory caches and backend persistent caches.
 */
export async function clearMovieResultCache(clearBackend = false): Promise<void> {
  resultCache.clear();
  detailsCache.clear();
  providersCache.clear();
  if (clearBackend) {
    try {
      await fetch(`${BASE_URL}/cache/clear`, { method: 'POST' });
    } catch {
      // Backend clear failure is non-fatal
    }
  }
}

/**
 * Phase 10: Probe network connectivity and TMDB reachability.
 */
export interface NetworkStatus {
  online: boolean;
  configured: boolean;
  latency_ms?: number | null;
  error?: string | null;
  cached_metadata_count?: number;
  cached_images_count?: number;
}

export async function checkNetworkStatus(): Promise<NetworkStatus> {
  try {
    const res = await fetch(`${BASE_URL}/network-status`);
    if (res.ok) {
      return res.json();
    }
    return { online: false, configured: true, error: `HTTP ${res.status}` };
  } catch (err: any) {
    return { online: false, configured: true, error: err?.message || 'Network unreachable' };
  }
}

export async function fetchCacheMetrics(): Promise<Record<string, any>> {
  try {
    const res = await fetch(`${BASE_URL}/cache/status`);
    if (res.ok) {
      return res.json();
    }
  } catch {}
  return {};
}

// =============================================================================
// Phase 8: Persistent Local Storage API (Watchlist, Favorites, Ratings, Preferences)
// =============================================================================

export interface UserMediaEntry {
  id?: number;
  tmdb_id: number;
  media_type: 'movie' | 'tv';
  title: string;
  poster_path?: string | null;
  poster_url?: string | null;
  backdrop_path?: string | null;
  backdrop_url?: string | null;
  release_year?: number | null;
  release_date?: string | null;
  original_language?: string | null;
  vote_average: number;
  overview: string;
  status: 'watchlist' | 'watching' | 'watched' | 'dropped' | 'plan_to_watch' | 'none';
  is_favorite: boolean;
  user_rating?: number | null;
  user_notes?: string;
  created_at?: string;
  updated_at?: string;
  watched_at?: string | null;
  genres?: string | null;
}

export interface TrackingSummary {
  watchlist_ids: number[];
  favorite_ids: number[];
  watched_ids: number[];
  user_ratings: Record<string, number>;
}

export interface MovieUserPreferences {
  preferred_genres: string[];
  preferred_languages: string[];
  preferred_regions: string[];
  disliked_genres?: string[];
  exclude_watched?: boolean;
  prefer_underrated?: boolean;
  prefer_highly_rated?: boolean;
  prefer_newer?: boolean;
  prefer_classic?: boolean;
  recommendation_settings: {
    min_rating?: number;
    include_watched?: boolean;
    [key: string]: any;
  };
  updated_at?: string;
}

export interface MovieFeedbackItem {
  id?: number;
  tmdb_id: number;
  media_type: string;
  feedback_type: 'more_like_this' | 'not_interested' | 'already_watched' | 'not_my_taste';
  title?: string;
  genres?: string;
  created_at?: string;
  updated_at?: string;
}

export interface UserMovieProfile {
  preferred_genres: string[];
  disliked_genres: string[];
  preferred_languages: string[];
  exclude_watched: boolean;
  prefer_underrated: boolean;
  prefer_highly_rated: boolean;
  prefer_newer: boolean;
  prefer_classic: boolean;
  favorite_ids: number[];
  watched_ids: number[];
  watchlist_ids: number[];
  liked_ids: number[];
  disliked_ids: number[];
  genre_affinities: Record<string, number>;
}

/**
 * Fetch fast tracking summary for badges and button states.
 */
export async function fetchTrackingSummary(): Promise<TrackingSummary> {
  const res = await fetch(`${BASE_URL}/storage/summary`);
  if (!res.ok) {
    throw new Error(`Failed to fetch tracking summary: HTTP ${res.status}`);
  }
  return res.json();
}

/**
 * Fetch stored entries with optional filters.
 */
export async function fetchStoredEntries(params?: {
  status?: string;
  media_type?: string;
  is_favorite?: boolean;
  min_rating?: number;
  sort_by?: string;
  desc?: boolean;
  limit?: number;
  offset?: number;
}): Promise<UserMediaEntry[]> {
  const q = new URLSearchParams();
  if (params?.status) q.set('status', params.status);
  if (params?.media_type) q.set('media_type', params.media_type);
  if (params?.is_favorite !== undefined) q.set('is_favorite', String(params.is_favorite));
  if (params?.min_rating !== undefined) q.set('min_rating', String(params.min_rating));
  if (params?.sort_by) q.set('sort_by', params.sort_by);
  if (params?.desc !== undefined) q.set('desc', String(params.desc));
  if (params?.limit) q.set('limit', String(params.limit));
  if (params?.offset) q.set('offset', String(params.offset));

  const res = await fetch(`${BASE_URL}/storage/entries?${q.toString()}`);
  if (!res.ok) {
    throw new Error(`Failed to list stored entries: HTTP ${res.status}`);
  }
  return res.json();
}

/**
 * Add or update title in watchlist.
 */
export async function addToWatchlist(item: {
  tmdb_id: number;
  title: string;
  media_type?: 'movie' | 'tv';
  poster_path?: string | null;
  release_year?: number | null;
  original_language?: string | null;
  vote_average?: number;
  overview?: string;
  status?: string;
  is_favorite?: boolean;
  user_rating?: number | null;
  genres?: string | null;
}): Promise<UserMediaEntry> {
  const payload: Record<string, any> = {
    tmdb_id: item.tmdb_id,
    title: item.title,
    media_type: item.media_type || 'movie',
    poster_path: item.poster_path,
    release_year: item.release_year,
    original_language: item.original_language,
    vote_average: item.vote_average || 0.0,
    overview: item.overview || '',
    status: item.status || 'watchlist',
    user_rating: item.user_rating,
    genres: item.genres,
  };
  if (item.is_favorite !== undefined) {
    payload.is_favorite = item.is_favorite;
  }

  const res = await fetch(`${BASE_URL}/storage/watchlist`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    const err = await res.text();
    throw new Error(err || `Failed to add to watchlist: HTTP ${res.status}`);
  }
  return res.json();
}

/**
 * Remove title from watchlist.
 */
export async function removeFromWatchlist(
  mediaType: 'movie' | 'tv',
  itemId: number | string
): Promise<void> {
  const normType = mediaType === 'tv' ? 'tv' : 'movie';
  const res = await fetch(`${BASE_URL}/storage/watchlist/${normType}/${itemId}`, {
    method: 'DELETE',
  });
  if (!res.ok) {
    throw new Error(`Failed to remove from watchlist: HTTP ${res.status}`);
  }
}

/**
 * Mark a title as watched. Accepts optional metadata to populate newly created entries.
 */
export async function markAsWatched(
  mediaType: 'movie' | 'tv',
  itemId: number | string,
  metadata?: Partial<UserMediaEntry>
): Promise<UserMediaEntry> {
  const normType = mediaType === 'tv' ? 'tv' : 'movie';
  const body = metadata
    ? JSON.stringify({
        title: metadata.title,
        poster_path: metadata.poster_path,
        poster_url: metadata.poster_url,
        backdrop_path: metadata.backdrop_path,
        backdrop_url: metadata.backdrop_url,
        release_year:
          typeof metadata.release_year === 'number'
            ? metadata.release_year
            : metadata.release_year
            ? parseInt(String(metadata.release_year), 10)
            : undefined,
        release_date: metadata.release_date,
        original_language: metadata.original_language,
        vote_average: metadata.vote_average,
        overview: metadata.overview,
      })
    : undefined;

  const res = await fetch(`${BASE_URL}/storage/watched/${normType}/${itemId}`, {
    method: 'POST',
    headers: body ? { 'Content-Type': 'application/json' } : undefined,
    body,
  });
  if (!res.ok) {
    throw new Error(`Failed to mark as watched: HTTP ${res.status}`);
  }
  return res.json();
}

/**
 * Update tracking status (e.g. watchlist, watching, watched, dropped, none).
 */
export async function updateEntryStatus(
  mediaType: 'movie' | 'tv',
  itemId: number | string,
  status: string
): Promise<UserMediaEntry> {
  const normType = mediaType === 'tv' ? 'tv' : 'movie';
  const res = await fetch(`${BASE_URL}/storage/status/${normType}/${itemId}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ status }),
  });
  if (!res.ok) {
    throw new Error(`Failed to update status: HTTP ${res.status}`);
  }
  return res.json();
}

/**
 * Toggle favorite state for a title.
 */
export async function setFavorite(
  mediaType: 'movie' | 'tv',
  itemId: number | string,
  isFavorite: boolean,
  metadata?: Partial<UserMediaEntry>
): Promise<UserMediaEntry> {
  const normType = mediaType === 'tv' ? 'tv' : 'movie';
  const res = await fetch(`${BASE_URL}/storage/favorite/${normType}/${itemId}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      is_favorite: isFavorite,
      title: metadata?.title,
      poster_path: metadata?.poster_path,
      poster_url: metadata?.poster_url,
      backdrop_path: metadata?.backdrop_path,
      backdrop_url: metadata?.backdrop_url,
      release_year:
        typeof metadata?.release_year === 'number'
          ? metadata.release_year
          : metadata?.release_year
          ? parseInt(String(metadata.release_year), 10)
          : undefined,
      release_date: metadata?.release_date,
      original_language: metadata?.original_language,
      vote_average: metadata?.vote_average,
      overview: metadata?.overview,
    }),
  });
  if (!res.ok) {
    throw new Error(`Failed to set favorite: HTTP ${res.status}`);
  }
  return res.json();
}

/**
 * Assign or clear personal local user rating (1-10).
 */
export async function setLocalRating(
  mediaType: 'movie' | 'tv',
  itemId: number | string,
  rating: number | null,
  metadata?: Partial<UserMediaEntry>
): Promise<UserMediaEntry> {
  const normType = mediaType === 'tv' ? 'tv' : 'movie';
  const res = await fetch(`${BASE_URL}/storage/rating/${normType}/${itemId}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      rating: rating,
      title: metadata?.title,
      poster_path: metadata?.poster_path,
      release_year: metadata?.release_year,
    }),
  });
  if (!res.ok) {
    throw new Error(`Failed to set rating: HTTP ${res.status}`);
  }
  return res.json();
}

/**
 * Get tracking status for a specific title.
 */
export async function fetchEntryStatus(
  mediaType: 'movie' | 'tv',
  itemId: number | string
): Promise<UserMediaEntry | null> {
  const normType = mediaType === 'tv' ? 'tv' : 'movie';
  const res = await fetch(`${BASE_URL}/storage/entry/${normType}/${itemId}`);
  if (!res.ok) return null;
  return res.json();
}

/**
 * Retrieve user entertainment preferences.
 */
export async function fetchMoviePreferences(): Promise<MovieUserPreferences> {
  const res = await fetch(`${BASE_URL}/storage/preferences`);
  if (!res.ok) {
    throw new Error(`Failed to fetch preferences: HTTP ${res.status}`);
  }
  return res.json();
}

/**
 * Update user entertainment preferences.
 */
export async function updateMoviePreferences(
  prefs: Partial<MovieUserPreferences>
): Promise<MovieUserPreferences> {
  const res = await fetch(`${BASE_URL}/storage/preferences`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(prefs),
  });
  if (!res.ok) {
    throw new Error(`Failed to update preferences: HTTP ${res.status}`);
  }
  return res.json();
}

/**
 * Reset user entertainment preferences to defaults.
 */
export async function resetMoviePreferences(): Promise<MovieUserPreferences> {
  const res = await fetch(`${BASE_URL}/storage/preferences/reset`, {
    method: 'POST',
  });
  if (!res.ok) {
    throw new Error(`Failed to reset preferences: HTTP ${res.status}`);
  }
  return res.json();
}

/**
 * Retrieve synthesized user taste profile and genre affinities.
 */
export async function fetchUserProfile(): Promise<UserMovieProfile> {
  const res = await fetch(`${BASE_URL}/storage/profile`);
  if (!res.ok) {
    throw new Error(`Failed to fetch user profile: HTTP ${res.status}`);
  }
  return res.json();
}

/**
 * Submit recommendation feedback ('more_like_this', 'not_interested', 'already_watched', 'not_my_taste').
 */
export async function submitMovieFeedback(
  tmdb_id: number,
  media_type: string,
  feedback_type: 'more_like_this' | 'not_interested' | 'already_watched' | 'not_my_taste',
  title = '',
  genres = ''
): Promise<{ status: string; tmdb_id: number; feedback_type: string }> {
  const res = await fetch(`${BASE_URL}/feedback`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ tmdb_id, media_type, feedback_type, title, genres }),
  });
  if (!res.ok) {
    throw new Error(`Failed to submit feedback: HTTP ${res.status}`);
  }
  return res.json();
}

/**
 * Fetch all recorded recommendation feedback.
 */
export async function fetchMovieFeedback(): Promise<MovieFeedbackItem[]> {
  const res = await fetch(`${BASE_URL}/feedback`);
  if (!res.ok) {
    throw new Error(`Failed to fetch movie feedback: HTTP ${res.status}`);
  }
  return res.json();
}

/**
 * Delete feedback for a title.
 */
export async function deleteMovieFeedback(media_type: string, itemId: number): Promise<{ status: string }> {
  const res = await fetch(`${BASE_URL}/feedback/${media_type}/${itemId}`, {
    method: 'DELETE',
  });
  if (!res.ok) {
    throw new Error(`Failed to delete feedback: HTTP ${res.status}`);
  }
  return res.json();
}

// =============================================================================
// AI Search History API (/api/movies/storage/history/*)
// =============================================================================

export interface AISearchHistoryItem {
  id: string;
  query: string;
  timestamp: number;
  created_at?: string;
}

/**
 * Retrieve persistent AI search history from the database.
 */
export async function fetchAISearchHistory(limit = 50): Promise<AISearchHistoryItem[]> {
  const q = new URLSearchParams({ limit: String(limit) });
  const res = await fetch(`${BASE_URL}/storage/history?${q.toString()}`);
  if (!res.ok) {
    throw new Error(`Failed to fetch AI search history: HTTP ${res.status}`);
  }
  return res.json();
}

/**
 * Record an AI search query to the database.
 */
export async function saveAISearchQuery(query: string): Promise<AISearchHistoryItem> {
  const res = await fetch(`${BASE_URL}/storage/history`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ query: query.trim() }),
  });
  if (!res.ok) {
    throw new Error(`Failed to save AI search query: HTTP ${res.status}`);
  }
  return res.json();
}

/**
 * Delete an individual AI search query from the database.
 */
export async function deleteAISearchHistoryItem(id: string): Promise<void> {
  const res = await fetch(`${BASE_URL}/storage/history/${encodeURIComponent(id)}`, {
    method: 'DELETE',
  });
  if (!res.ok) {
    throw new Error(`Failed to delete AI search query: HTTP ${res.status}`);
  }
}

/**
 * Clear all AI search history records from the database.
 */
export async function clearAISearchHistory(): Promise<void> {
  const res = await fetch(`${BASE_URL}/storage/history`, {
    method: 'DELETE',
  });
  if (!res.ok) {
    throw new Error(`Failed to clear AI search history: HTTP ${res.status}`);
  }
}

// =============================================================================
// Phase 9: AI-Powered Recommendations API
// =============================================================================

export interface ParsedRecommendationIntent {
  content_type: 'all' | 'movie' | 'tv';
  language?: string | null;
  region?: string | null;
  origin_country?: string | null;
  is_explicit_country?: boolean;
  is_explicit_language?: boolean;
  original_languages?: string[];
  preferred_languages?: string[];
  required_languages?: string[];
  genres: string[];
  genre_ids: number[];
  preferred_genres?: string[];
  required_genres?: string[];
  themes?: string[];
  preferred_themes?: string[];
  moods?: string[];
  preferred_moods?: string[];
  plot_elements?: string[];
  release_year?: number | null;
  release_year_gte?: number | null;
  release_year_lte?: number | null;
  keywords: string[];
  similar_to_title?: string | null;
  reference_title?: string | null;
  reference_year?: number | null;
  intent_type?: string;
  mood?: string | null;
  sort_by: string;
  interpreted_summary: string;
  diagnostics?: Record<string, any>;
}

export interface RecommendationDiagnostics {
  original_query: string;
  intent_type: string;
  reference_title_requested?: string | null;
  reference_resolved?: boolean;
  reference_tmdb_id?: number | null;
  reference_media_title?: string | null;
  retrieval_tiers_used?: string[];
  candidates_per_tier?: Record<string, number>;
  raw_candidates_count?: number;
  eligible_candidates_count?: number;
  rejected_candidates_count?: number;
  final_recommendations_count?: number;
  timings_ms?: {
    intent_parsing?: number;
    reference_resolution?: number;
    candidate_retrieval?: number;
    filtering?: number;
    ranking?: number;
    explanation_generation?: number;
    total_pipeline?: number;
    [key: string]: number | undefined;
  };
  [key: string]: any;
}

export interface RecommendedTitleModel {
  media: MediaItemSummary;
  score: number;
  match_reasons: string[];
  ai_explanation: string;
  is_ai_generated: boolean;
  presentation_section?: string | null;
  relevance_breakdown?: Record<string, number> | null;
}

export interface RecommendationResponse {
  query: string;
  interpreted_intent: ParsedRecommendationIntent;
  recommendations: RecommendedTitleModel[];
  presentation_sections?: Record<string, RecommendedTitleModel[]> | null;
  total_candidates_analyzed: number;
  ai_available: boolean;
  model_used?: string | null;
  history_id?: string | null;
  diagnostics?: RecommendationDiagnostics;
  error_type?: string | null;
  error_message?: string | null;
}

export interface EditedPreference {
  id?: string;
  category: 'genre' | 'mood' | 'theme' | 'plot' | 'lang' | 'year' | 'ref' | 'country' | 'other';
  label: string;
  value: string;
  nature?: 'required' | 'preferred' | 'reference';
}

/**
 * Request natural-language AI movie recommendations.
 */
export async function requestAIRecommendations(
  query: string,
  options?: {
    include_saved_preferences?: boolean;
    limit?: number;
    edited_preferences?: EditedPreference[];
    removed_preferences?: EditedPreference[];
    request_id?: string;
    signal?: AbortSignal;
  }
): Promise<RecommendationResponse> {
  const res = await fetch(`${BASE_URL}/recommendations`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      query: query.trim(),
      include_saved_preferences: options?.include_saved_preferences ?? true,
      limit: options?.limit ?? 6,
      edited_preferences: options?.edited_preferences,
      removed_preferences: options?.removed_preferences,
      request_id: options?.request_id,
    }),
    signal: options?.signal,
  });

  if (!res.ok) {
    let detail = '';
    try {
      const errJson = await res.json();
      detail = errJson.detail || '';
    } catch {
      detail = await res.text();
    }
    throw new Error(detail || `Recommendation request failed: HTTP ${res.status}`);
  }
  return res.json();
}

/**
 * Cancel ongoing AI movie recommendations generation on backend.
 */
export async function cancelAIRecommendations(): Promise<{ status: string; cancelled: boolean }> {
  try {
    const res = await fetch(`${BASE_URL}/recommendations/cancel`, {
      method: 'POST',
      signal: AbortSignal.timeout(3000),
    });
    if (res.ok) {
      return await res.json();
    }
  } catch (err) {
    console.debug('cancelAIRecommendations request completed or timed out:', err);
  }
  return { status: 'ok', cancelled: true };
}

/**
 * Preview natural-language intent parsing.
 */
export async function parseRecommendationIntent(query: string): Promise<ParsedRecommendationIntent> {
  const q = new URLSearchParams({ query: query.trim() });
  const res = await fetch(`${BASE_URL}/recommendations/parse?${q.toString()}`, {
    method: 'POST',
  });
  if (!res.ok) {
    throw new Error(`Failed to parse intent: HTTP ${res.status}`);
  }
  return res.json();
}

/**
 * Start native microphone dictation for movie search.
 */
export async function startVoiceDictation(): Promise<{ status: string; recording: boolean; message?: string }> {
  const res = await fetch('/api/voice/dictate/start', {
    method: 'POST',
  });
  if (!res.ok) {
    throw new Error(`Failed to start dictation: HTTP ${res.status}`);
  }
  return res.json();
}

/**
 * Stop microphone dictation and return recognized search text from local Faster-Whisper.
 */
export async function stopVoiceDictation(): Promise<{ status: string; text: string; message?: string }> {
  const res = await fetch('/api/voice/dictate/stop', {
    method: 'POST',
  });
  if (!res.ok) {
    throw new Error(`Failed to stop dictation: HTTP ${res.status}`);
  }
  return res.json();
}

/**
 * Query current dictation status.
 */
export async function getVoiceDictationStatus(): Promise<{ status: string; is_dictating: boolean }> {
  const res = await fetch('/api/voice/dictate/status');
  if (!res.ok) {
    throw new Error(`Failed to check dictation status: HTTP ${res.status}`);
  }
  return res.json();
}

// =============================================================================
// User-Managed TMDB API Key Operations
// =============================================================================

export interface TMDBKeyHistoryItem {
  id: string;
  masked_key: string;
  label: string;
  source: string;
  created_at: string;
  last_used_at: string;
  is_active: boolean;
}

export interface TMDBKeyStatusResponse {
  configured: boolean;
  source: 'custom' | 'env' | 'none';
  active_key_id: string;
  masked_key: string;
  has_env_fallback: boolean;
  env_masked_key: string;
  history: TMDBKeyHistoryItem[];
}

export interface TMDBTestKeyResult {
  valid: boolean;
  status_code: number;
  message: string;
}

/**
 * Fetch current TMDB API key status and history.
 */
export async function fetchTMDBKeyStatus(): Promise<TMDBKeyStatusResponse> {
  const res = await fetch(`${BASE_URL}/tmdb/key-status`);
  if (!res.ok) {
    throw new Error(`Failed to fetch TMDB key status: HTTP ${res.status}`);
  }
  return res.json();
}

/**
 * Test candidate or active TMDB API key against TMDB API.
 */
export async function testTMDBKey(apiKey?: string, keyId?: string): Promise<TMDBTestKeyResult> {
  const res = await fetch(`${BASE_URL}/tmdb/test-key`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ api_key: apiKey || null, key_id: keyId || null }),
  });
  if (!res.ok) {
    let detail = '';
    try {
      const err = await res.json();
      detail = err.detail || err.message;
    } catch {
      detail = await res.text();
    }
    throw new Error(detail || `Key test failed: HTTP ${res.status}`);
  }
  return res.json();
}

/**
 * Save, encrypt, and immediately activate a new TMDB API key.
 */
export async function saveAndActivateTMDBKey(apiKey: string, label?: string): Promise<TMDBKeyStatusResponse> {
  const res = await fetch(`${BASE_URL}/tmdb/save-key`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ api_key: apiKey.trim(), label: label?.trim() || null }),
  });
  if (!res.ok) {
    let detail = '';
    try {
      const err = await res.json();
      detail = err.detail || err.message;
    } catch {
      detail = await res.text();
    }
    throw new Error(detail || `Failed to save API key: HTTP ${res.status}`);
  }
  return res.json();
}

/**
 * Switch active key to a saved key or 'env' fallback.
 */
export async function activateTMDBKey(keyId: string): Promise<TMDBKeyStatusResponse> {
  const res = await fetch(`${BASE_URL}/tmdb/activate-key`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ key_id: keyId }),
  });
  if (!res.ok) {
    let detail = '';
    try {
      const err = await res.json();
      detail = err.detail || err.message;
    } catch {
      detail = await res.text();
    }
    throw new Error(detail || `Failed to activate key: HTTP ${res.status}`);
  }
  return res.json();
}

/**
 * Remove a previously saved key from history.
 */
export async function deleteTMDBKeyHistory(keyId: string): Promise<TMDBKeyStatusResponse> {
  const res = await fetch(`${BASE_URL}/tmdb/history/${keyId}`, {
    method: 'DELETE',
  });
  if (!res.ok) {
    let detail = '';
    try {
      const err = await res.json();
      detail = err.detail || err.message;
    } catch {
      detail = await res.text();
    }
    throw new Error(detail || `Failed to delete key: HTTP ${res.status}`);
  }
  return res.json();
}

// =============================================================================
// HDHub4u Dynamic Search URL & Mirror Configuration APIs
// =============================================================================

export interface HDHub4uHistoryItem {
  id: string;
  url_template: string;
  label: string;
  is_active: boolean;
  created_at: number;
  last_status: string;
}

export interface HDHub4uStatusResponse {
  active_url: string;
  default_url: string;
  is_custom: boolean;
  active_id: string;
  history: HDHub4uHistoryItem[];
}

export interface HDHub4uTestUrlResult {
  valid: boolean;
  status_code: number;
  message: string;
  preview_url: string;
}

/**
 * Fetch current HDHub4u search URL template and mirror history.
 */
export async function fetchHDHub4uStatus(): Promise<HDHub4uStatusResponse> {
  const res = await fetch(`${BASE_URL}/hdhub4u/status`);
  if (!res.ok) {
    throw new Error(`Failed to fetch HDHub4u status: HTTP ${res.status}`);
  }
  return res.json();
}

/**
 * Test candidate or active HDHub4u search URL against Reachability and Format rules.
 */
export async function testHDHub4uUrl(
  url?: string,
  itemId?: string,
  sampleTitle: string = 'Pixels'
): Promise<HDHub4uTestUrlResult> {
  const res = await fetch(`${BASE_URL}/hdhub4u/test-url`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      url: url || null,
      item_id: itemId || null,
      sample_title: sampleTitle,
    }),
  });
  if (!res.ok) {
    let detail = '';
    try {
      const err = await res.json();
      detail = err.detail || err.message;
    } catch {
      detail = await res.text();
    }
    throw new Error(detail || `HDHub4u URL test failed: HTTP ${res.status}`);
  }
  return res.json();
}

/**
 * Save into mirror history and activate a new HDHub4u search template.
 */
export async function saveAndActivateHDHub4uUrl(
  url: string,
  label?: string
): Promise<HDHub4uStatusResponse> {
  const res = await fetch(`${BASE_URL}/hdhub4u/save-url`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      url: url.trim(),
      label: label?.trim() || null,
    }),
  });
  if (!res.ok) {
    let detail = '';
    try {
      const err = await res.json();
      detail = err.detail || err.message;
    } catch {
      detail = await res.text();
    }
    throw new Error(detail || `Failed to save HDHub4u template: HTTP ${res.status}`);
  }
  return res.json();
}

/**
 * Switch active HDHub4u URL to a saved mirror or 'default'.
 */
export async function activateHDHub4uUrl(id: string): Promise<HDHub4uStatusResponse> {
  const res = await fetch(`${BASE_URL}/hdhub4u/activate-url`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ id }),
  });
  if (!res.ok) {
    let detail = '';
    try {
      const err = await res.json();
      detail = err.detail || err.message;
    } catch {
      detail = await res.text();
    }
    throw new Error(detail || `Failed to activate HDHub4u template: HTTP ${res.status}`);
  }
  return res.json();
}

/**
 * Remove a previously saved mirror from HDHub4u history.
 */
export async function deleteHDHub4uHistory(itemId: string): Promise<HDHub4uStatusResponse> {
  const res = await fetch(`${BASE_URL}/hdhub4u/history/${itemId}`, {
    method: 'DELETE',
  });
  if (!res.ok) {
    let detail = '';
    try {
      const err = await res.json();
      detail = err.detail || err.message;
    } catch {
      detail = await res.text();
    }
    throw new Error(detail || `Failed to delete HDHub4u history: HTTP ${res.status}`);
  }
  return res.json();
}

/**
 * Reset active HDHub4u URL to default template.
 */
export async function resetHDHub4uUrl(): Promise<HDHub4uStatusResponse> {
  const res = await fetch(`${BASE_URL}/hdhub4u/reset`, {
    method: 'POST',
  });
  if (!res.ok) {
    throw new Error(`Failed to reset HDHub4u URL: HTTP ${res.status}`);
  }
  return res.json();
}

/**
 * Sanitize and normalize HDHub4u URL input, eliminating duplicate schemes and bad formats.
 */
export function sanitizeHdHub4uUrl(urlCandidate?: string | null): string {
  let raw = (urlCandidate || '').trim();
  if (!raw) {
    return 'https://new10.hdhub4u.cl/search.html?q=pixels';
  }

  // 1. Detect and strip repeated http:// or https:// occurrences
  const schemeMatches = Array.from(raw.matchAll(/https?:\/\//gi));
  if (schemeMatches.length > 1) {
    const lastMatch = schemeMatches[schemeMatches.length - 1];
    if (lastMatch.index !== undefined) {
      raw = raw.slice(lastMatch.index);
    }
  }

  // 2. Ensure valid scheme prefix
  if (!/^https?:\/\//i.test(raw)) {
    raw = `https://${raw.replace(/^\/+/, '')}`;
  }

  return raw.trim();
}

/**
 * Format movie title for HDHub4u and web search queries.
 */
export function formatHdHub4uTitle(title?: string | null): string {
  if (!title) return '';
  // Clean punctuation but preserve clean spaces
  const cleaned = title.replace(/[:\-\–—\(\)\[\]\{\}\'\"!?,.]/g, ' ').replace(/\s+/g, ' ').trim().toLowerCase();
  return cleaned || title.trim().toLowerCase().replace(/\s+/g, '');
}

/**
 * Client-side helper to resolve HDHub4u search URL by substituting 'pixels' with movie title.
 * Handles duplicate schemes, space separation, and clean query parameter replacement.
 */
export function resolveHdHub4uUrl(template?: string | null, title?: string | null): string {
  const tmpl = sanitizeHdHub4uUrl(template);
  const formatted = formatHdHub4uTitle(title);
  const encoded = encodeURIComponent(formatted);

  if (!formatted) {
    return tmpl.replace(/pixels|\{query\}|\{title\}|\{movie\}/gi, '');
  }

  // 1. Replace 'pixels' keyword (case-insensitive)
  if (/pixels/i.test(tmpl)) {
    return tmpl.replace(/pixels/gi, encoded);
  }

  // 2. Replace {query}, {title}, or {movie} placeholders
  if (/\{query\}|\{title\}|\{movie\}/i.test(tmpl)) {
    return tmpl.replace(/\{query\}|\{title\}|\{movie\}/gi, encoded);
  }

  // 3. Existing query parameter replacement (q, s, query, search)
  if (/\?/.test(tmpl)) {
    if (/([?&])(q|s|query|search)=([^&]*)/i.test(tmpl)) {
      return tmpl.replace(/([?&](?:q|s|query|search)=)[^&]*/i, `$1${encoded}`);
    }
    const sep = tmpl.endsWith('&') || tmpl.endsWith('?') ? '' : '&';
    return `${tmpl}${sep}q=${encoded}`;
  }

  if (tmpl.endsWith('?')) {
    return `${tmpl}q=${encoded}`;
  }

  // 4. Bare domain or path without query parameter
  const cleanBase = tmpl.replace(/\/+$/, '');
  if (cleanBase.endsWith('.html') || cleanBase.endsWith('.php')) {
    return `${cleanBase}?q=${encoded}`;
  }
  return `${cleanBase}/search.html?q=${encoded}`;
}

// =============================================================================
// Where to Watch - Streaming Provider Search URL APIs & Dynamic Substitution
// =============================================================================

export interface WatchProviderTemplateDef {
  template: string;
  queryPlus: boolean;
  aliases: string[];
}

export const DEFAULT_WATCH_PROVIDER_TEMPLATES: Record<string, WatchProviderTemplateDef> = {
  hotstar: {
    template: 'https://www.hotstar.com/in/explore?search_query={title}',
    queryPlus: false,
    aliases: ['hotstar', 'disney+ hotstar', 'disney plus hotstar', 'jiohotstar', 'jio hotstar'],
  },
  netflix: {
    template: 'https://www.netflix.com/search?q={title}',
    queryPlus: false,
    aliases: ['netflix', 'netflix basic with ads'],
  },
  primevideo: {
    template: 'https://www.primevideo.com/search/ref=atv_nb_sr?phrase={title}',
    queryPlus: false,
    aliases: ['prime video', 'amazon prime video', 'amazon video'],
  },
  jiocinema: {
    template: 'https://www.jiocinema.com/search/{title}',
    queryPlus: false,
    aliases: ['jiocinema', 'jio cinema'],
  },
  appletv: {
    template: 'https://tv.apple.com/search?term={title}',
    queryPlus: false,
    aliases: ['apple tv', 'apple tv plus', 'apple tv+', 'itunes'],
  },
  googleplay: {
    template: 'https://play.google.com/store/search?q={title}&c=movies',
    queryPlus: false,
    aliases: ['google play movies', 'google play', 'google tv'],
  },
  youtube: {
    template: 'https://www.youtube.com/results?search_query={title}',
    queryPlus: false,
    aliases: ['youtube', 'youtube premium'],
  },
  zee5: {
    template: 'https://www.zee5.com/search?q={title}',
    queryPlus: false,
    aliases: ['zee5', 'zee'],
  },
  sonyliv: {
    template: 'https://www.sonyliv.com/search/{title}',
    queryPlus: false,
    aliases: ['sonyliv', 'sony liv'],
  },
  aha: {
    template: 'https://www.aha.video/search?q={title}',
    queryPlus: false,
    aliases: ['aha', 'aha video'],
  },
  lionsgateplay: {
    template: 'https://www.lionsgateplay.com/search?q={title}',
    queryPlus: false,
    aliases: ['lionsgate play', 'lionsgate plus', 'lionsgate'],
  },
  sunnxt: {
    template: 'https://www.sunnxt.com/search?q={title}',
    queryPlus: false,
    aliases: ['sun nxt', 'sunnxt'],
  },
  discoveryplus: {
    template: 'https://www.discoveryplus.in/search?q={title}',
    queryPlus: false,
    aliases: ['discovery+', 'discovery plus', 'discovery'],
  },
  crunchyroll: {
    template: 'https://www.crunchyroll.com/search?q={title}',
    queryPlus: false,
    aliases: ['crunchyroll'],
  },
  hulu: {
    template: 'https://www.hulu.com/search?q={title}',
    queryPlus: false,
    aliases: ['hulu'],
  },
  max: {
    template: 'https://www.max.com/search?q={title}',
    queryPlus: false,
    aliases: ['max', 'hbo max', 'hbo'],
  },
  paramountplus: {
    template: 'https://www.paramountplus.com/search/?q={title}',
    queryPlus: false,
    aliases: ['paramount+', 'paramount plus', 'paramount'],
  },
  peacock: {
    template: 'https://www.peacocktv.com/search?q={title}',
    queryPlus: false,
    aliases: ['peacock', 'peacock premium'],
  },
  bookmyshow: {
    template: 'https://in.bookmyshow.com/explore/movies?q={title}',
    queryPlus: false,
    aliases: ['bookmyshow', 'bookmyshow stream'],
  },
  mxplayer: {
    template: 'https://www.mxplayer.in/search?q={title}',
    queryPlus: false,
    aliases: ['mx player', 'mxplayer'],
  },
  hoichoi: {
    template: 'https://www.hoichoi.tv/search?q={title}',
    queryPlus: false,
    aliases: ['hoichoi'],
  },
  mubi: {
    template: 'https://mubi.com/search?query={title}',
    queryPlus: false,
    aliases: ['mubi'],
  },
  erosnow: {
    template: 'https://erosnow.com/search?q={title}',
    queryPlus: false,
    aliases: ['eros now', 'eros'],
  },
};

/**
 * Dynamically resolve a streaming provider URL with dynamic movie title substitution.
 * e.g. JioHotstar + "Law & Order: Special Victims Unit" ->
 * "https://www.hotstar.com/in/explore?search_query=Law+%26+Order%3A+Special+Victims+Unit"
 */
/**
 * Clean movie/series title for streaming search queries.
 * Replaces colons and plus signs with spaces while preserving apostrophes,
 * hyphens, ampersands, acronyms, and Indian-language Unicode:
 * - "Dhurandhar: The Revenge" -> "Dhurandhar The Revenge"
 * - "Dhurandhar+The+Revenge" -> "Dhurandhar The Revenge"
 * - "Pirates of the Caribbean: The Curse of the Black Pearl" -> "Pirates of the Caribbean The Curse of the Black Pearl"
 * - "Grey's Anatomy" -> "Grey's Anatomy"
 * - "Spider-Man: No Way Home" -> "Spider-Man No Way Home"
 * - "Law & Order: Special Victims Unit" -> "Law & Order Special Victims Unit"
 * - "धुरंधर: द रिवेंज" -> "धुरंधर द रिवेंज"
 */
export function cleanTitleForSearch(title?: string | null): string {
  let raw = (title || '').trim();
  if (!raw) return '';

  // 1. If string is already URL-encoded, safely decode first to prevent double-encoding
  try {
    if (raw.includes('%')) {
      raw = decodeURIComponent(raw);
    }
  } catch {
    // Ignore decode error and proceed with raw
  }

  // 2. Replace pluses and colons with clean spaces
  let t = raw.replace(/[+:]/g, ' ');

  // 3. Remove quotation marks, exclamation, semicolons, question marks,
  // while preserving apostrophes (e.g. Grey's Anatomy), hyphens (e.g. Spider-Man),
  // ampersands (e.g. Law & Order), dots (e.g. K.G.F.), and all Unicode letters
  t = t.replace(/["“”?!;]/g, '');

  // 4. Collapse multiple spaces into single space
  t = t.replace(/\s+/g, ' ').trim();

  return t || raw;
}

export function resolveWatchProviderUrl(
  providerName: string,
  mediaTitle: string,
  customTemplates?: Record<string, string>
): string {
  const title = (mediaTitle || '').trim() || 'Movie';
  const cleanName = (providerName || '').trim();
  const norm = cleanName.toLowerCase().replace(/[^a-z0-9]/g, '');

  let matchedKey: string | null = null;
  let useQueryPlus = false;

  // 1. Exact alias match
  for (const [key, defn] of Object.entries(DEFAULT_WATCH_PROVIDER_TEMPLATES)) {
    if (norm === key || defn.aliases.some((a) => a.toLowerCase().replace(/[^a-z0-9]/g, '') === norm)) {
      matchedKey = key;
      useQueryPlus = defn.queryPlus;
      break;
    }
  }

  // 2. Fuzzy substring match if not matched yet
  if (!matchedKey) {
    for (const [key, defn] of Object.entries(DEFAULT_WATCH_PROVIDER_TEMPLATES)) {
      if (norm.includes(key) || key.includes(norm)) {
        matchedKey = key;
        useQueryPlus = defn.queryPlus;
        break;
      }
    }
  }

  // 3. Retrieve template (custom override takes priority)
  let template: string;
  if (matchedKey && customTemplates && customTemplates[matchedKey]?.trim()) {
    template = customTemplates[matchedKey].trim();
  } else if (matchedKey) {
    template = DEFAULT_WATCH_PROVIDER_TEMPLATES[matchedKey].template;
  } else {
    // Universal Google search fallback for unlisted indie/regional providers
    template = 'https://www.google.com/search?q=watch%20{title}%20on%20{provider}';
    useQueryPlus = false;
  }

  // 4. Clean title (remove colons and search-cluttering punctuation)
  const cleanedTitle = cleanTitleForSearch(title);

  // 5. Always use standard %20 encoding so '+' never appears literally in search boxes!
  const formattedTitle = encodeURIComponent(cleanedTitle);

  let resolved = template;

  // 5. Replace placeholders
  if (resolved.includes('{title}')) {
    resolved = resolved.replace(/\{title\}/g, formattedTitle);
  } else if (resolved.includes('pixels')) {
    resolved = resolved.replace(/pixels/gi, formattedTitle);
  } else {
    const separator = resolved.includes('?') ? '&' : '?';
    resolved = `${resolved}${separator}q=${formattedTitle}`;
  }

  if (resolved.includes('{provider}')) {
    resolved = resolved.replace(/\{provider\}/g, encodeURIComponent(cleanName));
  }

  return resolved;
}

/**
 * Fetch all watch provider URL templates from backend.
 */
export async function fetchWatchProviderTemplates(
  sampleTitle: string = 'Law & Order: Special Victims Unit'
): Promise<WatchProviderTemplatesResponse> {
  const q = new URLSearchParams({ sample_title: sampleTitle });
  const res = await fetch(`${BASE_URL}/watch-providers/templates?${q.toString()}`);
  if (!res.ok) {
    throw new Error(`Failed to fetch watch provider templates: HTTP ${res.status}`);
  }
  return res.json();
}

/**
 * Save user custom overrides for streaming search templates.
 */
export async function saveWatchProviderTemplates(
  templates: Record<string, string>
): Promise<WatchProviderTemplatesResponse> {
  const res = await fetch(`${BASE_URL}/watch-providers/templates`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ templates }),
  });
  if (!res.ok) {
    throw new Error(`Failed to save watch provider templates: HTTP ${res.status}`);
  }
  return res.json();
}

/**
 * Reset all streaming search templates to system defaults.
 */
export async function resetWatchProviderTemplates(): Promise<WatchProviderTemplatesResponse> {
  const res = await fetch(`${BASE_URL}/watch-providers/templates/reset`, {
    method: 'POST',
  });
  if (!res.ok) {
    throw new Error(`Failed to reset watch provider templates: HTTP ${res.status}`);
  }
  return res.json();
}
