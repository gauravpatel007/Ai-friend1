import React, { useState, useRef, useEffect, useMemo } from 'react';
import {
  Sparkles,
  Send,
  Loader2,
  Bookmark,
  Heart,
  Info,
  Star,
  Film,
  Tv,
  RotateCcw,
  Sliders,
  CheckCircle2,
  AlertCircle,
  HelpCircle,
  Compass,
  History,
  X,
  Plus,
  ArrowUpRight,
  ChevronDown,
  ChevronUp,
  Layers,
  Activity,
  Check,
  Tag,
  Globe,
  Calendar,
  Filter,
  ArrowRight,
  Flame,
  ThumbsUp,
  ThumbsDown,
  Eye,
  Ban,
  Clock,
} from 'lucide-react';
import { MovieItemModel } from './MovieCard';
import {
  requestAIRecommendations,
  cancelAIRecommendations,
  RecommendationResponse,
  RecommendedTitleModel,
  fetchAISearchHistory,
  deleteAISearchHistoryItem,
  clearAISearchHistory,
  submitMovieFeedback,
  fetchMovieFeedback,
} from '../../api/movieApi';
import { AIHistoryModal, AIHistoryItem } from './AIHistoryModal';
import './AIRecommendationSection.css';

interface AIRecommendationSectionProps {
  onOpenDetails: (item: MovieItemModel) => void;
  onToggleWatchlist: (item: MovieItemModel) => void;
  onToggleFavorite?: (item: MovieItemModel) => void;
  onToggleWatched?: (item: MovieItemModel) => void;
  onOpenPoster?: (item: MovieItemModel) => void;
  watchlistIds: Set<string | number>;
  favoriteIds?: Set<string | number>;
  watchedIds?: Set<string | number>;
}

const QUICK_PROMPTS = [
  'Underrated Malayalam thriller',
  'Feel-good Hindi comedy',
  'Mind-bending sci-fi series',
  'Movies like Interstellar',
  '90s Hollywood action classic',
  'Telugu period action drama',
];

const MOOD_CHIPS = [
  { id: 'feel_good', label: '🌟 Feel-Good', query: 'Recommend a heartwarming, uplifting feel-good movie or series' },
  { id: 'dark_gritty', label: '🌑 Dark & Gritty', query: 'Recommend a dark and gritty crime thriller or neo-noir series' },
  { id: 'adrenaline', label: '⚡ Adrenaline Rush', query: 'Recommend a fast-paced high-stakes action movie' },
  { id: 'mind_bending', label: '🌀 Mind-Bending', query: 'Recommend a mind-bending sci-fi or psychological mystery with plot twists' },
  { id: 'tearjerker', label: '💧 Tearjerker', query: 'Recommend an emotional drama that will touch my heart' },
  { id: 'spine_chilling', label: '👻 Spine-Chilling', query: 'Recommend an atmospheric, terrifying horror or supernatural thriller' },
  { id: 'cozy', label: '☕ Cozy Evening', query: 'Recommend a comforting, cozy and relaxing title' },
];

const REFINEMENT_SUGGESTIONS = [
  {
    id: 'romantic',
    label: '💖 More romantic',
    prefCategory: 'genre' as const,
    prefLabel: 'Romance',
    prefValue: 'Romance',
  },
  {
    id: 'comedy',
    label: '😂 More comedy',
    prefCategory: 'genre' as const,
    prefLabel: 'Comedy',
    prefValue: 'Comedy',
  },
  {
    id: 'emotional',
    label: '💧 More emotional',
    prefCategory: 'mood' as const,
    prefLabel: 'Emotional',
    prefValue: 'Emotional',
  },
  {
    id: 'underrated',
    label: '💎 More underrated',
    prefCategory: 'other' as const,
    prefLabel: 'Underrated',
    prefValue: 'Underrated',
  },
  {
    id: 'recent',
    label: '⏱️ More recent (2020+)',
    prefCategory: 'other' as const,
    prefLabel: 'Recent (2020+)',
    prefValue: 'Recent (2020+)',
  },
  {
    id: 'malayalam',
    label: '🌴 More Malayalam',
    prefCategory: 'lang' as const,
    prefLabel: 'Malayalam',
    prefValue: 'Malayalam',
  },
  {
    id: 'tamil',
    label: '🪔 More Tamil',
    prefCategory: 'lang' as const,
    prefLabel: 'Tamil',
    prefValue: 'Tamil',
  },
  {
    id: 'telugu',
    label: '🌶️ More Telugu',
    prefCategory: 'lang' as const,
    prefLabel: 'Telugu',
    prefValue: 'Telugu',
  },
  {
    id: 'hindi',
    label: '🎭 More Hindi',
    prefCategory: 'lang' as const,
    prefLabel: 'Hindi',
    prefValue: 'Hindi',
  },
  {
    id: 'plot_similarity',
    label: '🎯 More plot similarity',
    prefCategory: 'theme' as const,
    prefLabel: 'Plot Similarity',
    prefValue: 'Plot Similarity',
  },
  {
    id: 'psychological',
    label: '🧠 More psychological',
    prefCategory: 'theme' as const,
    prefLabel: 'Psychological',
    prefValue: 'Psychological',
  },
  {
    id: 'scifi',
    label: '🚀 More science fiction',
    prefCategory: 'genre' as const,
    prefLabel: 'Science Fiction',
    prefValue: 'Science Fiction',
  },
  {
    id: 'international',
    label: '🌍 More international',
    prefCategory: 'other' as const,
    prefLabel: 'International',
    prefValue: 'International',
  },
  {
    id: 'twists',
    label: '🔀 More plot twists',
    prefCategory: 'other' as const,
    prefLabel: 'More Plot Twists',
    prefValue: 'More Plot Twists',
  },
  {
    id: 'action',
    label: '⚡ Faster paced',
    prefCategory: 'other' as const,
    prefLabel: 'Fast Paced',
    prefValue: 'Fast Paced',
  },
];

const SEARCH_STAGES = [
  { id: 1, label: 'Understanding your request', detail: 'Parsing narrative semantics and keywords' },
  { id: 2, label: 'Identifying movie preferences', detail: 'Resolving genres, eras, and plot tropes' },
  { id: 3, label: 'Searching TMDB catalog', detail: 'Querying live verified multi-tier sources' },
  { id: 4, label: 'Finding related films', detail: 'Gathering similar and recommended candidates' },
  { id: 5, label: 'Ranking recommendations', detail: 'Applying multi-signal relevance scoring' },
  { id: 6, label: 'Preparing grounded explanations', detail: 'Anchoring insights to verified synopses' },
];

// Fallback genre ID to name dictionary for TMDB
const TMDB_GENRE_NAMES: Record<number, string> = {
  28: 'Action',
  12: 'Adventure',
  16: 'Animation',
  35: 'Comedy',
  80: 'Crime',
  99: 'Documentary',
  18: 'Drama',
  10751: 'Family',
  14: 'Fantasy',
  36: 'History',
  27: 'Horror',
  10402: 'Music',
  9648: 'Mystery',
  10749: 'Romance',
  878: 'Sci-Fi',
  10770: 'TV Movie',
  53: 'Thriller',
  10752: 'War',
  37: 'Western',
  10759: 'Action & Adventure',
  10762: 'Kids',
  10763: 'News',
  10764: 'Reality',
  10765: 'Sci-Fi & Fantasy',
  10766: 'Soap',
  10767: 'Talk',
  10768: 'War & Politics',
};

const STORAGE_KEY_AI_HISTORY = 'ai_friend_movie_hub_ai_history';
const SESSION_KEY_AI_DRAFT = 'ai_friend_movie_hub_ai_draft_prompt';
const SESSION_KEY_AI_RESPONSE = 'ai_friend_movie_hub_ai_last_response';
const MAX_HISTORY_ITEMS = 50;

function loadSessionDraft(): string {
  try {
    return sessionStorage.getItem(SESSION_KEY_AI_DRAFT) || '';
  } catch {
    return '';
  }
}

function loadSessionResponse(): RecommendationResponse | null {
  try {
    const raw = sessionStorage.getItem(SESSION_KEY_AI_RESPONSE);
    if (!raw) return null;
    return JSON.parse(raw);
  } catch {
    return null;
  }
}

function persistSessionDraft(draft: string) {
  try {
    if (draft) {
      sessionStorage.setItem(SESSION_KEY_AI_DRAFT, draft);
    } else {
      sessionStorage.removeItem(SESSION_KEY_AI_DRAFT);
    }
  } catch {}
}

function persistSessionResponse(resp: RecommendationResponse | null) {
  try {
    if (resp) {
      sessionStorage.setItem(SESSION_KEY_AI_RESPONSE, JSON.stringify(resp));
    } else {
      sessionStorage.removeItem(SESSION_KEY_AI_RESPONSE);
    }
  } catch {}
}

function loadStoredHistory(): AIHistoryItem[] {
  try {
    const raw = localStorage.getItem(STORAGE_KEY_AI_HISTORY);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    if (Array.isArray(parsed)) {
      return parsed.filter(
        (item) => item && typeof item.query === 'string' && typeof item.timestamp === 'number'
      );
    }
  } catch (err) {
    console.warn('Failed to load AI search history from localStorage:', err);
  }
  return [];
}

function persistHistory(items: AIHistoryItem[]) {
  try {
    localStorage.setItem(STORAGE_KEY_AI_HISTORY, JSON.stringify(items));
  } catch (err) {
    console.warn('Failed to save AI search history to localStorage:', err);
  }
}

export interface PreferenceChip {
  id: string;
  category: 'genre' | 'mood' | 'theme' | 'plot' | 'lang' | 'year' | 'ref' | 'country' | 'other';
  label: string;
  value: string;
  isCustom?: boolean;
  nature?: 'required' | 'preferred' | 'reference';
}

export function extractChipsFromIntent(intent?: any): PreferenceChip[] {
  if (!intent) return [];
  const chips: PreferenceChip[] = [];

  // 1. Reference title
  if (intent.reference_title || intent.similar_to_title) {
    const val = intent.reference_title || intent.similar_to_title;
    chips.push({
      id: `ref-${val.toLowerCase()}`,
      category: 'ref',
      label: `Like: ${val}`,
      value: val,
      nature: 'reference',
    });
  }

  // 2. Geographic origin / country constraint (Req E)
  if (intent.origin_country || intent.region) {
    const isExplicit = Boolean(intent.is_explicit_country) || Boolean(intent.mandatory_constraints?.origin_country);
    const countryCode = (intent.origin_country || '').toUpperCase();
    const countryName = countryCode === 'IN' || intent.region === 'indian' ? 'India' :
                        countryCode === 'KR' || intent.region === 'korean' ? 'South Korea' :
                        countryCode === 'US' ? 'United States' :
                        countryCode || intent.region;
    chips.push({
      id: `country-${String(countryName).toLowerCase()}`,
      category: 'country',
      label: `Origin: ${countryName}`,
      value: String(countryName),
      nature: isExplicit ? 'required' : 'preferred',
    });
  }

  // 3. Required vs Preferred Genres (Req E)
  const reqGenres: string[] = intent.required_genres || [];
  const prefGenres: string[] = intent.preferred_genres || [];
  const allGenres: string[] = Array.from(new Set([
    ...reqGenres,
    ...prefGenres,
    ...(intent.genres || []),
    ...(intent.genres_any || []),
    ...(intent.genres_all || [])
  ]));

  allGenres.forEach((g: string) => {
    const isReq = reqGenres.includes(g) || (Boolean(intent.is_explicit_genre) && intent.genres?.includes(g));
    chips.push({
      id: `genre-${g.toLowerCase()}`,
      category: 'genre',
      label: g,
      value: g,
      nature: isReq ? 'required' : 'preferred',
    });
  });

  // 4. Themes (Soft / Preferred)
  const themes = intent.themes || intent.preferred_themes || [];
  themes.forEach((t: string) => {
    chips.push({
      id: `theme-${t.toLowerCase()}`,
      category: 'theme',
      label: t,
      value: t,
      nature: 'preferred',
    });
  });

  // 5. Moods (Soft / Preferred)
  const moods = Array.from(new Set([...(intent.moods || []), ...(intent.preferred_moods || []), ...(intent.mood ? [intent.mood] : [])]));
  moods.forEach((m: string) => {
    chips.push({
      id: `mood-${m.toLowerCase()}`,
      category: 'mood',
      label: m,
      value: m,
      nature: 'preferred',
    });
  });

  // 6. Plot elements (Soft / Preferred)
  const plot = intent.plot_elements || [];
  plot.forEach((p: string) => {
    chips.push({
      id: `plot-${p.toLowerCase()}`,
      category: 'plot',
      label: p,
      value: p,
      nature: 'preferred',
    });
  });

  // 7. Explicit vs Inferred Language (Req E)
  const reqLangs: string[] = intent.required_languages || (intent.is_explicit_language && intent.language ? [intent.language] : []) || [];
  const prefLangs: string[] = intent.preferred_languages || (!intent.is_explicit_language && intent.language ? [intent.language] : []) || [];
  const allLangs: string[] = Array.from(new Set([...reqLangs, ...prefLangs, ...(intent.original_languages || [])]));

  allLangs.forEach((l: string) => {
    const name = l === 'ml' ? 'Malayalam' : l === 'hi' ? 'Hindi' : l === 'te' ? 'Telugu' : l === 'ta' ? 'Tamil' : l === 'kn' ? 'Kannada' : l === 'bn' ? 'Bengali' : l === 'en' ? 'English' : l === 'ko' ? 'Korean' : l === 'ja' ? 'Japanese' : l === 'es' ? 'Spanish' : l === 'fr' ? 'French' : l.toUpperCase();
    const isReq = reqLangs.includes(l) || Boolean(intent.is_explicit_language);
    chips.push({
      id: `lang-${l.toLowerCase()}`,
      category: 'lang',
      label: isReq ? `Language: ${name}` : name,
      value: name,
      nature: isReq ? 'required' : 'preferred',
    });
  });

  // 8. Era / Year
  if (intent.release_year) {
    chips.push({
      id: 'year',
      category: 'year',
      label: `Year: ${intent.release_year}`,
      value: String(intent.release_year),
      nature: 'required',
    });
  } else if (intent.release_year_from) {
    chips.push({
      id: 'year-from',
      category: 'year',
      label: `After ${intent.release_year_from}`,
      value: `after ${intent.release_year_from}`,
      nature: 'required',
    });
  }

  return chips;
}

export const SUGGESTED_PREFERENCES = {
  genre: [
    'Romance', 'Comedy', 'Drama', 'Thriller', 'Science Fiction',
    'Action', 'Horror', 'Crime', 'Mystery', 'Adventure', 'Animation', 'Family',
  ],
  lang: [
    { label: 'Malayalam', value: 'Malayalam' },
    { label: 'Hindi', value: 'Hindi' },
    { label: 'Tamil', value: 'Tamil' },
    { label: 'Telugu', value: 'Telugu' },
    { label: 'Kannada', value: 'Kannada' },
    { label: 'Bengali', value: 'Bengali' },
    { label: 'English', value: 'English' },
    { label: 'Korean', value: 'Korean' },
    { label: 'Japanese', value: 'Japanese' },
    { label: 'Spanish', value: 'Spanish' },
    { label: 'French', value: 'French' },
  ],
  theme: [
    'Coming of Age', 'Friendship', 'Family', 'Relationships',
    'Emotional', 'Mystery', 'Slice of Life', 'Revenge', 'Heartwarming', 'Dark & Gritty',
  ],
  other: [
    'Underrated', 'Recent Movies', 'More Plot Twists', 'Fast Paced', 'Feel-Good', 'Mind-Bending',
  ],
};

export const AIRecommendationSection: React.FC<AIRecommendationSectionProps> = ({
  onOpenDetails,
  onToggleWatchlist,
  onToggleFavorite,
  onToggleWatched,
  onOpenPoster,
  watchlistIds,
  favoriteIds = new Set(),
  watchedIds = new Set(),
}) => {
  const [prompt, setPromptInternal] = useState<string>(() => loadSessionDraft());
  const [loading, setLoading] = useState<boolean>(false);
  const [reprocessing, setReprocessing] = useState<boolean>(false);
  const [activeStageIndex, setActiveStageIndex] = useState<number>(0);
  const [response, setResponseInternal] = useState<RecommendationResponse | null>(() => loadSessionResponse());
  const [error, setError] = useState<string | null>(null);
  const [history, setHistory] = useState<AIHistoryItem[]>(() => loadStoredHistory());
  const [isHistoryOpen, setIsHistoryOpen] = useState<boolean>(false);
  const [activeGeneratingPrompt, setActiveGeneratingPrompt] = useState<string>('');
  const [showDiagnostics, setShowDiagnostics] = useState<boolean>(false);
  const [feedbackMap, setFeedbackMap] = useState<Record<number, string>>({});

  // Generation Duration & Live Timer States
  const [totalProcessingTime, setTotalProcessingTime] = useState<string | null>(() => {
    const initResp = loadSessionResponse();
    if (initResp?.diagnostics?.timings_ms?.total_pipeline) {
      return `${(initResp.diagnostics.timings_ms.total_pipeline / 1000).toFixed(1)}s`;
    }
    return null;
  });
  const [reprocessSeconds, setReprocessSeconds] = useState<number>(0);
  const generationStartTimeRef = useRef<number>(0);

  // Phase 1: Separate Preference States
  const [originalPreferences, setOriginalPreferences] = useState<PreferenceChip[]>(() => {
    const initResp = loadSessionResponse();
    return initResp?.interpreted_intent ? extractChipsFromIntent(initResp.interpreted_intent) : [];
  });
  const [activePreferences, setActivePreferences] = useState<PreferenceChip[]>(() => {
    const initResp = loadSessionResponse();
    return initResp?.interpreted_intent ? extractChipsFromIntent(initResp.interpreted_intent) : [];
  });
  const [appliedPreferences, setAppliedPreferences] = useState<PreferenceChip[]>(() => {
    const initResp = loadSessionResponse();
    return initResp?.interpreted_intent ? extractChipsFromIntent(initResp.interpreted_intent) : [];
  });

  // Add Preference Popover State
  const [isAddPrefOpen, setIsAddPrefOpen] = useState<boolean>(false);
  const [customPrefText, setCustomPrefText] = useState<string>('');
  const [selectedCategoryTab, setSelectedCategoryTab] = useState<'genre' | 'lang' | 'theme' | 'other'>('genre');

  const setPrompt = (val: string | ((prev: string) => string)) => {
    setPromptInternal((prev) => {
      const next = typeof val === 'function' ? val(prev) : val;
      persistSessionDraft(next);
      return next;
    });
  };

  const setResponse = (
    val: RecommendationResponse | null | ((prev: RecommendationResponse | null) => RecommendationResponse | null)
  ) => {
    setResponseInternal((prev) => {
      const next = typeof val === 'function' ? val(prev) : val;
      persistSessionResponse(next);
      return next;
    });
  };

  const abortControllerRef = useRef<AbortController | null>(null);
  const activeRequestIdRef = useRef<number>(0);
  const lastCancelledTimeRef = useRef<number>(0);
  const isCancellingRef = useRef<boolean>(false);

  // Sync with persistent SQLite database on mount
  useEffect(() => {
    let isMounted = true;
    fetchAISearchHistory()
      .then((items) => {
        if (isMounted && Array.isArray(items)) {
          setHistory(items);
          persistHistory(items);
        }
      })
      .catch((err) => {
        console.debug('Loaded search history from local storage fallback:', err);
      });
    return () => {
      isMounted = false;
    };
  }, []);

  // Sync recommendation feedback on mount (Requirement 8.3)
  useEffect(() => {
    let isMounted = true;
    fetchMovieFeedback()
      .then((items) => {
        if (isMounted && Array.isArray(items)) {
          const map: Record<number, string> = {};
          items.forEach((it) => {
            map[it.tmdb_id] = it.feedback_type;
          });
          setFeedbackMap(map);
        }
      })
      .catch(() => {});
    return () => {
      isMounted = false;
    };
  }, []);

  // Multi-stage progress indicator animation during search (Requirement 7.1)
  useEffect(() => {
    if (!loading) {
      setActiveStageIndex(0);
      return;
    }

    setActiveStageIndex(0);
    const intervals = [400, 800, 1400, 2000, 2700];
    const timers: any[] = [];

    intervals.forEach((delay, idx) => {
      const t = setTimeout(() => {
        setActiveStageIndex((prev) => Math.max(prev, idx + 1));
      }, delay);
      timers.push(t);
    });

    return () => {
      timers.forEach((t) => clearTimeout(t));
    };
  }, [loading]);

  // Live timer for reprocessing state (1 sec, 2 sec...)
  useEffect(() => {
    if (!reprocessing) {
      setReprocessSeconds(0);
      return;
    }
    setReprocessSeconds(1);
    const interval = setInterval(() => {
      setReprocessSeconds((prev) => prev + 1);
    }, 1000);
    return () => clearInterval(interval);
  }, [reprocessing]);

  const handleDeleteHistoryItem = (id: string) => {
    setHistory((prev) => {
      const updated = prev.filter((item) => item.id !== id);
      persistHistory(updated);
      return updated;
    });
    deleteAISearchHistoryItem(id).catch((err) => {
      console.warn('Failed to delete history item from database:', err);
    });
  };

  const handleClearHistory = () => {
    setHistory([]);
    persistHistory([]);
    clearAISearchHistory().catch((err) => {
      console.warn('Failed to clear search history from database:', err);
    });
  };

  const handleSelectHistoryQuery = (queryText: string) => {
    setPrompt(queryText);
    setIsHistoryOpen(false);
    handleSearch(queryText);
  };

  const handleSearch = async (queryText?: string) => {
    // If the user cancelled recently or is cancelling, drop any synthetic submit / ghost clicks
    if (isCancellingRef.current || Date.now() - lastCancelledTimeRef.current < 500) {
      return;
    }

    const q = (queryText !== undefined ? queryText : prompt).trim();
    if (!q) return;

    // Prevent redundant research of the exact same query if already loading
    if (loading && q.toLowerCase() === activeGeneratingPrompt.trim().toLowerCase()) {
      return;
    }

    // Optimistic local update
    const tempId = `temp-${Date.now()}`;
    const optimisticItem: AIHistoryItem = {
      id: tempId,
      query: q,
      timestamp: Date.now(),
    };
    setHistory((prev) => {
      const filtered = prev.filter((item) => item.query.toLowerCase() !== q.toLowerCase());
      const updated = [optimisticItem, ...filtered].slice(0, MAX_HISTORY_ITEMS);
      persistHistory(updated);
      return updated;
    });

    // Cancel in-flight request on both client fetch and backend engine
    if (abortControllerRef.current) {
      try {
        abortControllerRef.current.abort();
      } catch {}
    }
    cancelAIRecommendations().catch(() => {});

    const controller = new AbortController();
    abortControllerRef.current = controller;
    const reqId = ++activeRequestIdRef.current;

    setLoading(true);
    setActiveGeneratingPrompt(q);
    setError(null);
    generationStartTimeRef.current = Date.now();

    try {
      const result = await requestAIRecommendations(q, {
        include_saved_preferences: true,
        limit: 8,
        signal: controller.signal,
      });
      if (reqId === activeRequestIdRef.current) {
        setResponse(result);
        const elapsedSec = ((Date.now() - generationStartTimeRef.current) / 1000).toFixed(1);
        if (result.diagnostics?.timings_ms?.total_pipeline) {
          setTotalProcessingTime(`${(result.diagnostics.timings_ms.total_pipeline / 1000).toFixed(1)}s`);
        } else {
          setTotalProcessingTime(`${elapsedSec}s`);
        }
        const newChips = extractChipsFromIntent(result.interpreted_intent);
        setOriginalPreferences(newChips);
        setActivePreferences(newChips);
        setAppliedPreferences(newChips);
        setIsAddPrefOpen(false);
        if (result.history_id) {
          const canonicalId = result.history_id;
          const canonicalItem: AIHistoryItem = {
            id: canonicalId,
            query: q,
            timestamp: Date.now(),
          };
          setHistory((prev) => {
            const filtered = prev.filter(
              (item) => item.query.toLowerCase() !== q.toLowerCase() && item.id !== tempId && item.id !== canonicalId
            );
            const updated = [canonicalItem, ...filtered].slice(0, MAX_HISTORY_ITEMS);
            persistHistory(updated);
            return updated;
          });
        }
      }
    } catch (err: any) {
      if (err.name === 'AbortError' || reqId !== activeRequestIdRef.current) return;
      setError(err?.message || 'Failed to generate recommendations.');
    } finally {
      if (reqId === activeRequestIdRef.current) {
        setLoading(false);
        setActiveGeneratingPrompt('');
      }
    }
  };

  const handleCancel = (e?: React.MouseEvent | React.SyntheticEvent) => {
    if (e) {
      e.preventDefault();
      e.stopPropagation();
    }
    isCancellingRef.current = true;
    lastCancelledTimeRef.current = Date.now();
    activeRequestIdRef.current++;
    if (abortControllerRef.current) {
      try {
        abortControllerRef.current.abort();
      } catch {}
      abortControllerRef.current = null;
    }
    cancelAIRecommendations().catch(() => {});
    setLoading(false);
    setReprocessing(false);
    setActiveGeneratingPrompt('');
    setError(null);

    // Release cancellation lock after small debounce window
    setTimeout(() => {
      isCancellingRef.current = false;
    }, 500);
  };

  const isPromptModifiedWhileLoading = loading && prompt.trim() !== activeGeneratingPrompt.trim();
  const showCancelButton = loading && !isPromptModifiedWhileLoading;

  const handleQuickPromptClick = (text: string) => {
    setPrompt(text);
    handleSearch(text);
  };

  // Phase 1: Interactive Preference Management Handlers
  const handleRemovePreference = (chip: PreferenceChip) => {
    setActivePreferences((prev) =>
      prev.filter(
        (p) =>
          p.id !== chip.id &&
          !(p.category === chip.category && p.value.toLowerCase() === chip.value.toLowerCase())
      )
    );
  };

  const handleAddPreference = (
    category: PreferenceChip['category'],
    label: string,
    value: string,
    nature: PreferenceChip['nature'] = 'preferred'
  ) => {
    const cleanLabel = label.trim();
    const cleanValue = value.trim();
    if (!cleanLabel) return;

    // Prevent duplicate preferences (case-insensitive check)
    const exists = activePreferences.some(
      (p) => p.category === category && p.value.toLowerCase() === cleanValue.toLowerCase()
    );
    if (exists) return;

    const newChip: PreferenceChip = {
      id: `custom-${category}-${Date.now()}-${Math.random().toString(36).substring(2, 6)}`,
      category,
      label: cleanLabel,
      value: cleanValue,
      isCustom: true,
      nature,
    };
    setActivePreferences((prev) => [...prev, newChip]);
  };

  // Refine discovery handler: Stage as preference without auto-searching (shows Reprocess & Reset)
  const handleApplyRefinement = (suggestion: typeof REFINEMENT_SUGGESTIONS[0]) => {
    const existing = activePreferences.find(
      (p) =>
        (p.category === suggestion.prefCategory && p.value.toLowerCase() === suggestion.prefValue.toLowerCase()) ||
        p.value.toLowerCase() === suggestion.prefLabel.toLowerCase() ||
        p.label.toLowerCase() === suggestion.prefLabel.toLowerCase()
    );
    if (existing) {
      handleRemovePreference(existing);
    } else {
      handleAddPreference(suggestion.prefCategory, suggestion.prefLabel, suggestion.prefValue, 'preferred');
    }
  };

  const handleAddCustomSubmit = (e?: React.FormEvent) => {
    if (e) e.preventDefault();
    if (!customPrefText.trim()) return;
    handleAddPreference(selectedCategoryTab, customPrefText.trim(), customPrefText.trim());
    setCustomPrefText('');
  };

  const handleResetPreferences = () => {
    setActivePreferences([...originalPreferences]);
  };

  // Track pending changes
  const removedPreferences = useMemo(() => {
    return originalPreferences.filter(
      (orig) =>
        !activePreferences.some(
          (act) => act.category === orig.category && act.value.toLowerCase() === orig.value.toLowerCase()
        )
    );
  }, [originalPreferences, activePreferences]);

  const addedPreferences = useMemo(() => {
    return activePreferences.filter(
      (act) =>
        !originalPreferences.some(
          (orig) => orig.category === act.category && orig.value.toLowerCase() === act.value.toLowerCase()
        )
    );
  }, [originalPreferences, activePreferences]);

  const hasPendingChanges = removedPreferences.length > 0 || addedPreferences.length > 0;

  // Reprocess with updated authoritative preferences (Requirement 4)
  const handleReprocessWithPreferences = async () => {
    const q = (response?.query || prompt).trim();
    if (!q) return;

    const active = [...activePreferences];
    const removed = [...removedPreferences];

    if (reprocessing) return;
    setReprocessing(true);
    setReprocessSeconds(1);
    setError(null);
    generationStartTimeRef.current = Date.now();

    const controller = new AbortController();
    abortControllerRef.current = controller;
    const reqId = ++activeRequestIdRef.current;

    try {
      const result = await requestAIRecommendations(q, {
        include_saved_preferences: true,
        limit: 8,
        edited_preferences: active,
        removed_preferences: removed,
        request_id: String(reqId),
        signal: controller.signal,
      });

      if (reqId === activeRequestIdRef.current) {
        setResponse(result);
        setAppliedPreferences(active);
        const elapsedSec = ((Date.now() - generationStartTimeRef.current) / 1000).toFixed(1);
        if (result.diagnostics?.timings_ms?.total_pipeline) {
          setTotalProcessingTime(`${(result.diagnostics.timings_ms.total_pipeline / 1000).toFixed(1)}s`);
        } else {
          setTotalProcessingTime(`${elapsedSec}s`);
        }
        const newChips = extractChipsFromIntent(result.interpreted_intent);
        setOriginalPreferences(newChips);
        setActivePreferences(newChips);
        setIsAddPrefOpen(false);
      }
    } catch (err: any) {
      if (err.name === 'AbortError' || reqId !== activeRequestIdRef.current) return;
      setError(err?.message || 'Failed to reprocess recommendations with edited preferences.');
    } finally {
      if (reqId === activeRequestIdRef.current) {
        setReprocessing(false);
      }
    }
  };

  const handleFeedback = async (
    item: RecommendedTitleModel['media'],
    feedbackType: 'more_like_this' | 'not_interested' | 'already_watched' | 'not_my_taste'
  ) => {
    const current = feedbackMap[item.id];
    const nextType = current === feedbackType ? '' : feedbackType;
    setFeedbackMap((prev) => {
      const updated = { ...prev };
      if (!nextType) delete updated[item.id];
      else updated[item.id] = nextType;
      return updated;
    });

    try {
      if (nextType) {
        await submitMovieFeedback(
          item.id,
          item.media_type,
          feedbackType,
          item.title,
          item.genre_names ? item.genre_names.join(',') : ''
        );
      }
    } catch (err) {
      console.warn('Failed to submit feedback:', err);
    }
  };

  // Render a movie recommendation card (Requirement 7.3)
  const renderMovieCard = (rec: RecommendedTitleModel) => {
    const item = rec.media;
    const isMovie = item.media_type === 'movie';
    const isSaved = watchlistIds.has(item.id) || watchlistIds.has(Number(item.id));
    const isFav = favoriteIds.has(item.id) || favoriteIds.has(Number(item.id));
    const isWatched = watchedIds.has(item.id) || watchedIds.has(Number(item.id));

    // Resolve verified genres
    const verifiedGenres: string[] = [];
    if (item.genre_names && item.genre_names.length > 0) {
      verifiedGenres.push(...item.genre_names);
    } else if (item.genre_ids && item.genre_ids.length > 0) {
      item.genre_ids.forEach((gid) => {
        if (TMDB_GENRE_NAMES[gid]) verifiedGenres.push(TMDB_GENRE_NAMES[gid]);
      });
    }

    const movieModel: MovieItemModel = {
      id: item.id,
      title: item.title,
      mediaType: item.media_type,
      posterPath: item.poster_url || (item.poster_path ? `https://image.tmdb.org/t/p/w500${item.poster_path}` : null),
      backdropPath: item.backdrop_url || (item.backdrop_path ? `https://image.tmdb.org/t/p/w1280${item.backdrop_path}` : null),
      releaseYear: item.release_year ?? undefined,
      voteAverage: item.vote_average,
      overview: item.overview,
      originalLanguage: item.original_language ?? undefined,
      genreNames: verifiedGenres,
    };

    return (
      <article key={`${item.media_type}-${item.id}`} className="hub-ai-rec-card" tabIndex={0} aria-label={item.title}>
        {/* Poster Frame */}
        <div
          className="hub-ai-card-poster"
          onClick={() => onOpenDetails(movieModel)}
          title="Click to view details"
        >
          {movieModel.posterPath ? (
            <img
              src={movieModel.posterPath}
              alt={item.title}
              loading="lazy"
              className="hub-ai-poster-img"
            />
          ) : (
            <div className="hub-ai-poster-fallback">
              {isMovie ? <Film size={32} /> : <Tv size={32} />}
              <span>{item.title}</span>
            </div>
          )}

          <div className="hub-ai-card-top-badges">
            <span className={`hub-media-type-tag ${isMovie ? 'tag-movie' : 'tag-series'}`}>
              {isMovie ? 'MOVIE' : 'SERIES'}
            </span>
            {item.vote_average > 0 && (
              <span className="hub-rating-pill" title={`Rating: ${item.vote_average.toFixed(1)}/10`}>
                <Star size={11} className="rating-star-icon" />
                <span>{item.vote_average.toFixed(1)}</span>
              </span>
            )}
          </div>
        </div>

        {/* Meta & Grounded AI Explanation */}
        <div className="hub-ai-card-info">
          {/* Title & Year */}
          <div className="hub-ai-title-row">
            <h4
              className="hub-ai-card-title"
              onClick={() => onOpenDetails(movieModel)}
              title={item.title}
            >
              {item.title}
            </h4>
            <div className="hub-ai-card-meta-chips">
              {item.release_year && (
                <span className="hub-ai-card-year">{item.release_year}</span>
              )}
              {item.original_language && (
                <span className="hub-ai-card-lang" title={`Original Language: ${item.original_language.toUpperCase()}`}>
                  {item.original_language.toUpperCase()}
                </span>
              )}
            </div>
          </div>

          {/* Verified TMDB Genres */}
          {verifiedGenres.length > 0 && (
            <div className="hub-ai-genres-row" aria-label="Verified Genres">
              {verifiedGenres.slice(0, 3).map((g) => (
                <span key={g} className="hub-ai-genre-badge">
                  {g}
                </span>
              ))}
            </div>
          )}

          {/* Short Verified TMDB Synopsis */}
          {item.overview && (
            <p className="hub-ai-card-synopsis" title={item.overview}>
              {item.overview}
            </p>
          )}

          {/* Match reasons pills */}
          {rec.match_reasons.length > 0 && (
            <div className="hub-ai-reasons-row">
              {rec.match_reasons.slice(0, 3).map((r, idx) => (
                <span key={idx} className="hub-ai-reason-chip">
                  {r}
                </span>
              ))}
            </div>
          )}

          {/* Grounded Explanation Box */}
          <div className="hub-ai-explanation-box">
            <div className="hub-ai-explanation-header">
              <Sparkles size={12} className="ai-tiny-sparkle" />
              <span>Why Bond Recommended This</span>
            </div>
            <p className="hub-ai-explanation-text">&ldquo;{rec.ai_explanation}&rdquo;</p>
          </div>

          {/* 4-Action Button Bar: Details, Watchlist, Favorite, Watched */}
          <div className="hub-ai-card-actions">
            <button
              type="button"
              className="hub-ai-action-btn action-details"
              onClick={() => onOpenDetails(movieModel)}
              title="View full film details, cast, and trailers"
            >
              <Info size={13} />
              <span>Details</span>
            </button>

            <button
              type="button"
              className={`hub-ai-action-btn action-bookmark ${isSaved ? 'saved' : ''}`}
              onClick={() => onToggleWatchlist(movieModel)}
              title={isSaved ? 'In Watchlist (Click to remove)' : 'Add to Watchlist'}
            >
              <Bookmark size={13} fill={isSaved ? '#0A84FF' : 'none'} />
              <span>{isSaved ? 'Saved' : 'Watchlist'}</span>
            </button>

            {onToggleFavorite && (
              <button
                type="button"
                className={`hub-ai-action-btn action-fav ${isFav ? 'active-fav' : ''}`}
                onClick={() => onToggleFavorite(movieModel)}
                title={isFav ? 'Favorited (Click to remove)' : 'Add to Favorites'}
              >
                <Heart size={13} fill={isFav ? '#FF375F' : 'none'} color={isFav ? '#FF375F' : 'currentColor'} />
                <span>{isFav ? 'Favorited' : 'Favorite'}</span>
              </button>
            )}

            {onToggleWatched && (
              <button
                type="button"
                className={`hub-ai-action-btn action-watched ${isWatched ? 'active-watched' : ''}`}
                onClick={() => onToggleWatched(movieModel)}
                title={isWatched ? 'Watched (Click to mark unwatched)' : 'Mark as Watched'}
              >
                <CheckCircle2 size={13} color={isWatched ? '#30D158' : 'currentColor'} />
                <span>{isWatched ? 'Watched' : 'Watch'}</span>
              </button>
            )}
          </div>

          {/* Phase 8: User Feedback Controls (Requirement 8.3) */}
          <div className="hub-ai-feedback-bar">
            <span className="hub-ai-feedback-label">Feedback:</span>
            <div className="hub-ai-feedback-buttons">
              <button
                type="button"
                className={`hub-ai-feedback-btn ${feedbackMap[item.id] === 'more_like_this' ? 'active-like' : ''}`}
                onClick={() => handleFeedback(item, 'more_like_this')}
                title="Recommend more films like this"
              >
                <ThumbsUp size={11} />
                <span>More like this</span>
              </button>
              <button
                type="button"
                className={`hub-ai-feedback-btn ${feedbackMap[item.id] === 'not_interested' ? 'active-dislike' : ''}`}
                onClick={() => handleFeedback(item, 'not_interested')}
                title="Not interested in this title"
              >
                <Ban size={11} />
                <span>Not interested</span>
              </button>
              <button
                type="button"
                className={`hub-ai-feedback-btn ${feedbackMap[item.id] === 'already_watched' ? 'active-watched' : ''}`}
                onClick={() => handleFeedback(item, 'already_watched')}
                title="Already watched"
              >
                <Eye size={11} />
                <span>Watched</span>
              </button>
              <button
                type="button"
                className={`hub-ai-feedback-btn ${feedbackMap[item.id] === 'not_my_taste' ? 'active-dislike' : ''}`}
                onClick={() => handleFeedback(item, 'not_my_taste')}
                title="Not my taste"
              >
                <ThumbsDown size={11} />
                <span>Not my taste</span>
              </button>
            </div>
          </div>
        </div>
      </article>
    );
  };

  return (
    <section className="hub-ai-rec-container" aria-label="Bond AI Movie Recommendations">
      {/* Top Banner & Prompt Composer */}
      <div className="hub-ai-rec-hero">
        <div className="hub-ai-hero-top-row">
          <div className="hub-ai-hero-header">
            <div className="hub-ai-sparkle-pill">
              <Sparkles size={14} className="sparkle-glyph" />
              <span>Bond&apos;s Cinematic Discovery</span>
            </div>
            <h2 className="hub-ai-headline">What kind of story are you looking for?</h2>
            <p className="hub-ai-subheadline">
              Powered by local Ollama intelligence and verified TMDB filmography. Discover real cinema with grounded match explanations.
            </p>
          </div>

          <div className="hub-ai-hero-actions">
            {totalProcessingTime && !loading && !reprocessing && (
              <div
                className="hub-ai-hero-time-pill"
                title={`Recommendation generation completed in ${totalProcessingTime}`}
              >
                <Clock size={12} className="time-pill-icon" />
                <span>{totalProcessingTime}</span>
              </div>
            )}

            <button
              type="button"
              className={`hub-ai-history-btn ${isHistoryOpen ? 'active' : ''}`}
              onClick={() => {
                setIsHistoryOpen(true);
                fetchAISearchHistory()
                  .then((items) => {
                    if (Array.isArray(items)) {
                      setHistory(items);
                      persistHistory(items);
                    }
                  })
                  .catch(() => {});
              }}
              title="View AI Search History"
              aria-label="View AI Search History"
            >
              <History size={16} className="hub-ai-history-btn-icon" />
              <span className="hub-ai-history-btn-label">History</span>
              {history.length > 0 && (
                <span className="hub-ai-history-btn-badge" title={`${history.length} searches saved`}>
                  {history.length}
                </span>
              )}
            </button>
          </div>
        </div>

        {/* Input Bar */}
        <form
          className="hub-ai-input-form"
          onSubmit={(e) => {
            e.preventDefault();
            e.stopPropagation();
            if (loading || isCancellingRef.current || Date.now() - lastCancelledTimeRef.current < 500) return;
            if (!prompt.trim()) return;
            handleSearch(prompt);
          }}
        >
          <div className="hub-ai-input-wrapper">
            <Sparkles size={18} className="hub-ai-input-icon" />
            <input
              type="text"
              className="hub-ai-text-input"
              value={prompt}
              onChange={(e) => setPrompt(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter') {
                  e.preventDefault();
                  e.stopPropagation();
                  if (!loading && !isCancellingRef.current && prompt.trim() && Date.now() - lastCancelledTimeRef.current >= 500) {
                    handleSearch(prompt);
                  }
                }
              }}
              placeholder="E.g. Mind-bending sci-fi or psychological mystery with plot twists..."
            />
            <div className="hub-ai-actions-group">
              {showCancelButton ? (
                <button
                  key="hub-ai-cancel-action-btn"
                  type="button"
                  className="hub-ai-cancel-btn"
                  onClick={(e) => {
                    e.preventDefault();
                    e.stopPropagation();
                    handleCancel(e);
                  }}
                  title="Cancel AI Generation"
                >
                  <X size={14} />
                  <span>Cancel</span>
                </button>
              ) : (
                <button
                  key="hub-ai-submit-action-btn"
                  type="button"
                  className="hub-ai-submit-btn"
                  onClick={(e) => {
                    e.preventDefault();
                    e.stopPropagation();
                    if (!prompt.trim() || loading || isCancellingRef.current || Date.now() - lastCancelledTimeRef.current < 500) {
                      return;
                    }
                    handleSearch(prompt);
                  }}
                  disabled={!prompt.trim() || loading}
                  title="Discover Movies"
                >
                  <Send size={15} />
                  <span>Ask Bond</span>
                </button>
              )}
            </div>
          </div>
        </form>

        {/* Quick Suggestion Chips */}
        <div className="hub-ai-quick-chips">
          <span className="hub-ai-chips-label">Try asking:</span>
          {QUICK_PROMPTS.map((item) => (
            <button
              key={item}
              type="button"
              className="hub-ai-chip"
              onClick={() => handleQuickPromptClick(item)}
              disabled={loading}
            >
              {item}
            </button>
          ))}
        </div>

        {/* Curated Mood-Based Recommendation Discovery */}
        <div className="hub-ai-mood-chips-row" role="region" aria-label="Mood-based recommendation filters">
          <span className="hub-ai-chips-label">Explore by mood:</span>
          <div className="hub-ai-mood-chips-wrap">
            {MOOD_CHIPS.map((mood) => (
              <button
                key={mood.id}
                type="button"
                className={`hub-ai-mood-chip ${prompt === mood.query ? 'active-mood' : ''}`}
                onClick={() => {
                  setPrompt(mood.query);
                  handleSearch(mood.query);
                }}
                title={mood.query}
              >
                {mood.label}
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* Meaningful Multi-Stage Search Progress Indicator (Requirement 7.1) */}
      {loading && (
        <div className="hub-ai-loading-viewport" role="status" aria-live="polite">
          <div className="hub-ai-progress-top">
            <div className="hub-ai-loading-header">
              <Loader2 size={24} className="hub-ai-spinner" />
              <div className="hub-ai-loading-header-text">
                <span className="hub-ai-progress-title">Discovering films with Bond...</span>
                <span className="hub-ai-progress-sub">
                  &ldquo;{activeGeneratingPrompt || prompt}&rdquo;
                </span>
              </div>
            </div>
            <button
              key="hub-ai-viewport-cancel-btn"
              type="button"
              className="hub-ai-viewport-cancel-btn"
              onClick={(e) => {
                e.preventDefault();
                e.stopPropagation();
                handleCancel(e);
              }}
              title="Cancel generation"
            >
              <X size={14} />
              <span>Cancel</span>
            </button>
          </div>

          {/* Progress Stepper Bar */}
          <div className="hub-ai-stepper-progress-track">
            <div
              className="hub-ai-stepper-progress-fill"
              style={{ width: `${Math.min(100, (activeStageIndex + 1) * 16.66)}%` }}
            />
          </div>

          {/* Stepper Stages Grid */}
          <div className="hub-ai-stepper-grid">
            {SEARCH_STAGES.map((stage, idx) => {
              const isCompleted = idx < activeStageIndex;
              const isActive = idx === activeStageIndex;
              const isPending = idx > activeStageIndex;

              return (
                <div
                  key={stage.id}
                  className={`hub-ai-stepper-node ${isCompleted ? 'completed' : ''} ${isActive ? 'active' : ''} ${isPending ? 'pending' : ''}`}
                >
                  <div className="stepper-node-dot">
                    {isCompleted ? (
                      <Check size={12} className="stepper-check-icon" />
                    ) : isActive ? (
                      <div className="stepper-pulse-dot" />
                    ) : (
                      <span className="stepper-index-num">{stage.id}</span>
                    )}
                  </div>
                  <div className="stepper-node-content">
                    <span className="stepper-label">{stage.label}</span>
                    <span className="stepper-detail">{stage.detail}</span>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* Error View */}
      {error && !loading && (
        <div className="hub-ai-error-box">
          <AlertCircle size={22} className="error-icon" />
          <div className="hub-ai-error-content">
            <span className="hub-ai-error-title">Recommendation Unavailable</span>
            <p className="hub-ai-error-desc">{error}</p>
          </div>
          <button
            type="button"
            className="hub-ai-retry-btn"
            onClick={() => handleSearch(prompt)}
          >
            <RotateCcw size={13} />
            <span>Try Again</span>
          </button>
        </div>
      )}

      {/* Response Results Section (Never shown while loading) */}
      {response && !loading && (
        <div className="hub-ai-results-wrapper">
          {/* Interpreted Intent Showcase Card (Requirement 7.2) */}
          <div className="hub-ai-intent-showcase">
            <div className="hub-ai-intent-header-row">
              <div className="hub-ai-intent-meta-left">
                <div className="hub-ai-intent-sparkle-pill">
                  <Sparkles size={12} />
                  <span>Bond Understood</span>
                </div>
                <div className="hub-ai-intent-query-quote">
                  &ldquo;{response.query}&rdquo;
                </div>
              </div>

              {/* Discovery Summary Information (Requirement 7.6) */}
              <div className="hub-ai-discovery-summary">
                <span className="hub-ai-discovery-count-pill">
                  {response.total_candidates_analyzed} movies analyzed &middot; {response.recommendations.length} recommendations selected
                </span>
                {response.diagnostics && (
                  <button
                    type="button"
                    className={`hub-ai-diag-btn ${showDiagnostics ? 'active' : ''}`}
                    onClick={() => setShowDiagnostics((prev) => !prev)}
                    title="Toggle Developer Diagnostics"
                  >
                    <Activity size={12} />
                    <span>Diagnostics</span>
                    {showDiagnostics ? <ChevronUp size={12} /> : <ChevronDown size={12} />}
                  </button>
                )}
              </div>
            </div>

            {/* Interactive Preference Chips & Staging Toolbar (Phase 1) */}
            <div className="hub-ai-preferences-bar">
              <div className="hub-ai-pref-bar-header">
                <span className="hub-ai-pref-label">Identified preferences:</span>
                <button
                  type="button"
                  className={`hub-ai-add-pref-trigger-btn ${isAddPrefOpen ? 'active' : ''}`}
                  onClick={() => setIsAddPrefOpen((prev) => !prev)}
                  title="Add custom or suggested preference"
                >
                  <Plus size={13} />
                  <span>Add Preference</span>
                </button>
              </div>

              {/* Active Preference Chips List */}
              <div className="hub-ai-pref-chips-list">
                {activePreferences.length === 0 ? (
                  <span className="hub-ai-pref-empty-msg">
                    No preferences active. Click &ldquo;+ Add Preference&rdquo; or &ldquo;Reset Changes&rdquo;.
                  </span>
                ) : (
                  activePreferences.map((chip) => {
                    const isNewlyAdded = addedPreferences.some(
                      (p) => p.category === chip.category && p.value.toLowerCase() === chip.value.toLowerCase()
                    );
                    const nature = chip.nature || (chip.category === 'ref' ? 'reference' : 'preferred');
                    return (
                      <span
                        key={chip.id}
                        className={`hub-ai-pref-chip category-${chip.category} nature-${nature} ${isNewlyAdded ? 'is-added' : ''}`}
                        title={isNewlyAdded ? `Added preference: ${chip.label}` : `${nature.toUpperCase()}: ${chip.label}`}
                      >
                        {isNewlyAdded && <Sparkles size={10} className="pref-chip-added-glyph" />}
                        {nature === 'required' && <span className="pref-nature-badge badge-required">Required</span>}
                        {nature === 'reference' && <span className="pref-nature-badge badge-reference">Ref</span>}
                        <span className="pref-chip-text">{chip.label}</span>
                        <button
                          type="button"
                          className="pref-chip-remove"
                          onClick={() => handleRemovePreference(chip)}
                          title={`Remove "${chip.label}" preference`}
                          aria-label={`Remove "${chip.label}"`}
                        >
                          <X size={10} />
                        </button>
                      </span>
                    );
                  })
                )}
              </div>

              {/* Add Preference Dropdown / Popover */}
              {isAddPrefOpen && (
                <div className="hub-ai-add-pref-popover" role="dialog" aria-label="Add preferences">
                  <div className="hub-ai-add-pref-popover-header">
                    <span className="popover-title">Add Preference</span>
                    <button
                      type="button"
                      className="popover-close-btn"
                      onClick={() => setIsAddPrefOpen(false)}
                      title="Close"
                    >
                      <X size={14} />
                    </button>
                  </div>

                  {/* Custom Search / Input */}
                  <form className="hub-ai-add-pref-form" onSubmit={handleAddCustomSubmit}>
                    <input
                      type="text"
                      className="hub-ai-add-pref-input"
                      value={customPrefText}
                      onChange={(e) => setCustomPrefText(e.target.value)}
                      placeholder={`Type ${selectedCategoryTab} or custom preference (Enter to add)...`}
                    />
                    <button
                      type="submit"
                      className="hub-ai-add-pref-submit"
                      disabled={!customPrefText.trim()}
                    >
                      <Plus size={13} />
                      <span>Add</span>
                    </button>
                  </form>

                  {/* Category Tabs */}
                  <div className="hub-ai-add-category-tabs">
                    {(['genre', 'lang', 'theme', 'other'] as const).map((cat) => (
                      <button
                        key={cat}
                        type="button"
                        className={`category-tab-btn ${selectedCategoryTab === cat ? 'active' : ''}`}
                        onClick={() => setSelectedCategoryTab(cat)}
                      >
                        {cat === 'genre'
                          ? 'Genres'
                          : cat === 'lang'
                          ? 'Languages'
                          : cat === 'theme'
                          ? 'Themes'
                          : 'Vibes / Other'}
                      </button>
                    ))}
                  </div>

                  {/* Category Suggestions List */}
                  <div className="hub-ai-add-suggestions-grid">
                    {selectedCategoryTab === 'genre' &&
                      SUGGESTED_PREFERENCES.genre.map((item) => {
                        const isAlreadyActive = activePreferences.some(
                          (p) => p.category === 'genre' && p.value.toLowerCase() === item.toLowerCase()
                        );
                        return (
                          <button
                            key={item}
                            type="button"
                            className={`suggestion-pill ${isAlreadyActive ? 'is-active' : ''}`}
                            onClick={() => handleAddPreference('genre', item, item)}
                            disabled={isAlreadyActive}
                            title={isAlreadyActive ? 'Already added' : `Add ${item}`}
                          >
                            {isAlreadyActive ? <Check size={11} /> : <Plus size={11} />}
                            <span>{item}</span>
                          </button>
                        );
                      })}

                    {selectedCategoryTab === 'lang' &&
                      SUGGESTED_PREFERENCES.lang.map((item) => {
                        const isAlreadyActive = activePreferences.some(
                          (p) => p.category === 'lang' && p.value.toLowerCase() === item.value.toLowerCase()
                        );
                        return (
                          <button
                            key={item.value}
                            type="button"
                            className={`suggestion-pill ${isAlreadyActive ? 'is-active' : ''}`}
                            onClick={() => handleAddPreference('lang', item.label, item.value)}
                            disabled={isAlreadyActive}
                            title={isAlreadyActive ? 'Already added' : `Add ${item.label}`}
                          >
                            {isAlreadyActive ? <Check size={11} /> : <Plus size={11} />}
                            <span>{item.label}</span>
                          </button>
                        );
                      })}

                    {selectedCategoryTab === 'theme' &&
                      SUGGESTED_PREFERENCES.theme.map((item) => {
                        const isAlreadyActive = activePreferences.some(
                          (p) => p.category === 'theme' && p.value.toLowerCase() === item.toLowerCase()
                        );
                        return (
                          <button
                            key={item}
                            type="button"
                            className={`suggestion-pill ${isAlreadyActive ? 'is-active' : ''}`}
                            onClick={() => handleAddPreference('theme', item, item)}
                            disabled={isAlreadyActive}
                            title={isAlreadyActive ? 'Already added' : `Add ${item}`}
                          >
                            {isAlreadyActive ? <Check size={11} /> : <Plus size={11} />}
                            <span>{item}</span>
                          </button>
                        );
                      })}

                    {selectedCategoryTab === 'other' &&
                      SUGGESTED_PREFERENCES.other.map((item) => {
                        const isAlreadyActive = activePreferences.some(
                          (p) => p.category === 'other' && p.value.toLowerCase() === item.toLowerCase()
                        );
                        return (
                          <button
                            key={item}
                            type="button"
                            className={`suggestion-pill ${isAlreadyActive ? 'is-active' : ''}`}
                            onClick={() => handleAddPreference('other', item, item)}
                            disabled={isAlreadyActive}
                            title={isAlreadyActive ? 'Already added' : `Add ${item}`}
                          >
                            {isAlreadyActive ? <Check size={11} /> : <Plus size={11} />}
                            <span>{item}</span>
                          </button>
                        );
                      })}
                  </div>
                </div>
              )}

              {/* Staged Changes & Actions Bar (Phase 2) */}
              {hasPendingChanges && (
                <div className="hub-ai-pref-staging-bar">
                  <div className="hub-ai-pref-summary-pill">
                    {removedPreferences.length > 0 && (
                      <span className="summary-item removed">
                        {removedPreferences.length} filter{removedPreferences.length > 1 ? 's' : ''} removed
                      </span>
                    )}
                    {removedPreferences.length > 0 && addedPreferences.length > 0 && (
                      <span className="summary-dot">&middot;</span>
                    )}
                    {addedPreferences.length > 0 && (
                      <span className="summary-item added">
                        {addedPreferences.length} preference{addedPreferences.length > 1 ? 's' : ''} added
                      </span>
                    )}
                    <span className="summary-dot">&middot;</span>
                    <span className="summary-status">Changes not applied</span>
                  </div>

                  <div className="hub-ai-pref-actions-group">
                    <button
                      type="button"
                      className="hub-ai-reset-changes-btn"
                      onClick={handleResetPreferences}
                      disabled={reprocessing}
                      title="Restore original identified preferences"
                    >
                      <RotateCcw size={12} />
                      <span>Reset Filters</span>
                    </button>

                    <button
                      type="button"
                      className="hub-ai-reprocess-btn"
                      onClick={handleReprocessWithPreferences}
                      disabled={reprocessing}
                      title="Reprocess recommendations using updated preferences"
                    >
                      {reprocessing ? (
                        <>
                          <span className="hub-ai-spin-wrapper" aria-hidden="true">
                            <Loader2 size={14} className="hub-ai-spin-svg" />
                          </span>
                          <span>Reprocessing...</span>
                        </>
                      ) : (
                        <>
                          <Sparkles size={13} />
                          <span>Reprocess Recommendations</span>
                          <ArrowUpRight size={13} />
                        </>
                      )}
                    </button>
                  </div>
                </div>
              )}
            </div>

            {/* Search Refinement Suggestions (Requirement 7.5 - Staged into Preferences) */}
            <div className="hub-ai-refinements-row">
              <span className="hub-ai-refine-label">Refine discovery:</span>
              <div className="hub-ai-refine-chips">
                {REFINEMENT_SUGGESTIONS.map((item) => {
                  const isAlreadyActive = activePreferences.some(
                    (p) =>
                      (p.category === item.prefCategory && p.value.toLowerCase() === item.prefValue.toLowerCase()) ||
                      p.value.toLowerCase() === item.prefLabel.toLowerCase() ||
                      p.label.toLowerCase() === item.prefLabel.toLowerCase()
                  );
                  return (
                    <button
                      key={item.id}
                      type="button"
                      className={`hub-ai-refine-btn ${isAlreadyActive ? 'is-active' : ''}`}
                      onClick={(e) => {
                        e.preventDefault();
                        e.stopPropagation();
                        handleApplyRefinement(item);
                      }}
                      title={
                        isAlreadyActive
                          ? `"${item.prefLabel}" is active — click to remove`
                          : `Stage "${item.prefLabel}" preference (Reprocess Recommendations)`
                      }
                    >
                      <span>{item.label}</span>
                      {isAlreadyActive && <Check size={11} className="hub-ai-refine-check-icon" />}
                    </button>
                  );
                })}
              </div>
            </div>
          </div>

          {/* Developer Diagnostics Panel (Separated per Requirement 7.6) */}
          {showDiagnostics && response.diagnostics && (
            <div className="hub-ai-diagnostics-panel" role="region" aria-label="Developer Diagnostics">
              <div className="hub-ai-diag-header">
                <div className="hub-ai-diag-title">
                  <Activity size={14} className="hub-ai-diag-icon" />
                  <span>Developer Diagnostics &amp; Pipeline Breakdown</span>
                </div>
                <span className="hub-ai-diag-total-time">
                  Total: {response.diagnostics.timings_ms?.total_pipeline ?? 0} ms
                </span>
              </div>

              <div className="hub-ai-diag-grid">
                {/* Intent & Reference Movie Box */}
                <div className="hub-ai-diag-card">
                  <span className="hub-ai-diag-card-title">Intent &amp; Reference Resolution</span>
                  <div className="hub-ai-diag-kv-row">
                    <span className="diag-k">Intent Type:</span>
                    <span className="diag-v badge">{response.diagnostics.intent_type || 'general'}</span>
                  </div>
                  {response.diagnostics.reference_title_requested && (
                    <div className="hub-ai-diag-kv-row">
                      <span className="diag-k">Requested Ref:</span>
                      <span className="diag-v">&ldquo;{response.diagnostics.reference_title_requested}&rdquo;</span>
                    </div>
                  )}
                  {response.diagnostics.reference_resolved ? (
                    <div className="hub-ai-diag-kv-row">
                      <span className="diag-k">Resolved TMDB:</span>
                      <span className="diag-v highlight">
                        {response.diagnostics.reference_media_title} (ID: {response.diagnostics.reference_tmdb_id})
                      </span>
                    </div>
                  ) : response.diagnostics.reference_title_requested ? (
                    <div className="hub-ai-diag-kv-row">
                      <span className="diag-k">Resolved TMDB:</span>
                      <span className="diag-v warn">Could not resolve in catalog</span>
                    </div>
                  ) : null}
                </div>

                {/* Candidate Funnel */}
                <div className="hub-ai-diag-card">
                  <span className="hub-ai-diag-card-title">Candidate Funnel</span>
                  <div className="hub-ai-diag-funnel">
                    <div className="diag-funnel-step">
                      <span className="funnel-num">{response.diagnostics.raw_candidates_count ?? 0}</span>
                      <span className="funnel-lbl">Raw</span>
                    </div>
                    <span className="funnel-arrow">&rarr;</span>
                    <div className="diag-funnel-step">
                      <span className="funnel-num">{response.diagnostics.eligible_candidates_count ?? 0}</span>
                      <span className="funnel-lbl">Eligible</span>
                    </div>
                    <span className="funnel-arrow">&rarr;</span>
                    <div className="diag-funnel-step">
                      <span className="funnel-num">{response.diagnostics.final_recommendations_count ?? 0}</span>
                      <span className="funnel-lbl">Final</span>
                    </div>
                  </div>
                  <div className="diag-rejections-hint">
                    Rejected {response.diagnostics.rejected_candidates_count ?? 0} candidates in eligibility filtering
                  </div>
                </div>

                {/* Retrieval Tiers */}
                <div className="hub-ai-diag-card wide">
                  <span className="hub-ai-diag-card-title">Retrieval Tiers Executed</span>
                  <div className="hub-ai-diag-tiers">
                    {(response.diagnostics.retrieval_tiers_used || []).map((tier: string) => {
                      const count = response.diagnostics?.candidates_per_tier?.[tier] ?? 0;
                      return (
                        <div key={tier} className="diag-tier-badge">
                          <Layers size={11} />
                          <span className="tier-name">{tier.replace(/_/g, ' ')}</span>
                          <span className="tier-count">+{count}</span>
                        </div>
                      );
                    })}
                  </div>
                </div>

                {/* Timings */}
                {response.diagnostics.timings_ms && (
                  <div className="hub-ai-diag-card wide">
                    <span className="hub-ai-diag-card-title">Stage Latencies</span>
                    <div className="hub-ai-diag-timings-grid">
                      {Object.entries(response.diagnostics.timings_ms).map(([stage, ms]) => {
                        if (stage === 'total_pipeline') return null;
                        return (
                          <div key={stage} className="diag-timing-item">
                            <span className="stage-name">{stage.replace(/_/g, ' ')}</span>
                            <span className="stage-ms">{ms} ms</span>
                          </div>
                        );
                      })}
                    </div>
                  </div>
                )}
              </div>
            </div>
          )}

          {/* Partial Results Banner (Requirement 7.4) */}
          {response.recommendations.length > 0 && response.recommendations.length < 3 && (
            <div className="hub-ai-partial-notice">
              <Info size={15} className="partial-icon" />
              <span>
                Showing <strong>{response.recommendations.length} partial match{response.recommendations.length > 1 ? 'es' : ''}</strong>. Some of your preferences were restrictive, displaying the closest verified titles found.
              </span>
            </div>
          )}

          {/* Cards Grid or Differentiated Empty States / Reprocessing View */}
          {reprocessing ? (
            <div className="hub-ai-lower-reprocessing-box" role="status" aria-live="polite">
              <div className="hub-ai-white-loader-wrap" aria-hidden="true">
                <Loader2 size={44} className="hub-ai-white-loader" />
              </div>
              <div className="hub-ai-reprocessing-content">
                <h4 className="hub-ai-reprocessing-headline">Reprocessing Recommendations...</h4>
                <div className="hub-ai-reprocessing-counter-wrap">
                  <span className="hub-ai-reprocessing-counter-num">{reprocessSeconds} sec</span>
                  <span className="hub-ai-reprocessing-counter-dot">&middot;</span>
                  <span className="hub-ai-reprocessing-counter-label">Applying updated preferences to TMDB catalog</span>
                </div>
                <p className="hub-ai-reprocessing-sub">
                  Filtering candidates and re-ranking recommendations based on your authoritative preference chips.
                </p>
              </div>
            </div>
          ) : response.recommendations.length === 0 ? (
            <div className="hub-ai-empty-box">
              {response.error_type === 'tmdb_unconfigured' ? (
                <>
                  <AlertCircle size={32} className="hub-ai-empty-icon warn" />
                  <h4>TMDB API Key Required</h4>
                  <p>
                    {response.error_message ||
                      'Please configure your TMDB API key in Settings to discover verified movies.'}
                  </p>
                </>
              ) : response.error_type === 'reference_not_resolved' || response.error_type === 'reference_not_found' ? (
                <>
                  <Compass size={32} className="hub-ai-empty-icon warn" />
                  <h4>Reference Title Not Found</h4>
                  <p>
                    {response.error_message ||
                      `Could not locate reference movie "${response.interpreted_intent.reference_title || response.query}" in the TMDB catalog.`}
                  </p>
                  <p className="empty-sub-tip">
                    Tip: Try checking the title spelling or ask for movies by genre or mood instead.
                  </p>
                </>
              ) : response.error_type === 'country_too_restrictive' ? (
                <>
                  <Globe size={32} className="hub-ai-empty-icon warn" />
                  <h4>Country Filtering Was Too Restrictive</h4>
                  <p>
                    {response.error_message ||
                      'Matching titles were found in TMDB, but none satisfied your strict country or regional constraint.'}
                  </p>
                  <div className="hub-ai-empty-actions">
                    <button
                      type="button"
                      className="hub-ai-broaden-btn"
                      onClick={() => {
                        const broad = prompt.replace(/(indian|south indian|bollywood|malayalam|korean|hollywood)/gi, '').trim();
                        setPrompt(broad || prompt);
                        handleSearch(broad || prompt);
                      }}
                    >
                      <Globe size={13} />
                      <span>Search Across All Regions</span>
                    </button>
                    <button
                      type="button"
                      className="hub-ai-retry-btn"
                      onClick={handleResetPreferences}
                    >
                      <RotateCcw size={13} />
                      <span>Reset Filters</span>
                    </button>
                  </div>
                </>
              ) : response.error_type === 'language_too_restrictive' ? (
                <>
                  <Filter size={32} className="hub-ai-empty-icon warn" />
                  <h4>Language Filtering Was Too Restrictive</h4>
                  <p>
                    {response.error_message ||
                      'Titles were found, but none matched the mandatory language requirement. Try relaxing the language constraint.'}
                  </p>
                  <div className="hub-ai-empty-actions">
                    <button
                      type="button"
                      className="hub-ai-broaden-btn"
                      onClick={() => {
                        const broad = prompt.replace(/(malayalam|hindi|tamil|telugu|kannada|korean|english)/gi, '').trim();
                        setPrompt(broad || prompt);
                        handleSearch(broad || prompt);
                      }}
                    >
                      <Globe size={13} />
                      <span>Include All Regional Languages</span>
                    </button>
                    <button
                      type="button"
                      className="hub-ai-retry-btn"
                      onClick={handleResetPreferences}
                    >
                      <RotateCcw size={13} />
                      <span>Reset Filters</span>
                    </button>
                  </div>
                </>
              ) : response.error_type === 'ranking_threshold_too_high' ? (
                <>
                  <Activity size={32} className="hub-ai-empty-icon warn" />
                  <h4>Relevance Ranking Threshold Was Too High</h4>
                  <p>
                    {response.error_message ||
                      'Candidates passed hard filters, but none scored above the minimum relevance threshold for your combined preferences.'}
                  </p>
                  <div className="hub-ai-empty-actions">
                    <button
                      type="button"
                      className="hub-ai-broaden-btn"
                      onClick={handleReprocessWithPreferences}
                    >
                      <Sparkles size={13} />
                      <span>Re-rank with Relaxed Threshold</span>
                    </button>
                  </div>
                </>
              ) : response.error_type === 'metadata_incomplete' ? (
                <>
                  <AlertCircle size={32} className="hub-ai-empty-icon warn" />
                  <h4>Incomplete Movie Metadata</h4>
                  <p>
                    {response.error_message ||
                      'Retrieved titles lacked critical metadata required to verify your constraints.'}
                  </p>
                </>
              ) : response.error_type === 'tmdb_no_candidates' ? (
                <>
                  <Compass size={32} className="hub-ai-empty-icon" />
                  <h4>No Titles Returned from TMDB</h4>
                  <p>
                    {response.error_message ||
                      'No matching titles discovered in TMDB catalog. Try broadening your query keywords or exploring related genres.'}
                  </p>
                </>
              ) : response.error_type === 'api_failure' || response.error_type === 'network_error' ? (
                <>
                  <AlertCircle size={32} className="hub-ai-empty-icon error" />
                  <h4>Search Service Unavailable</h4>
                  <p>
                    {response.error_message ||
                      'Unable to reach TMDB or search service. Please check your internet connection or API settings.'}
                  </p>
                  <button
                    type="button"
                    className="hub-ai-retry-btn"
                    style={{ marginTop: 12 }}
                    onClick={() => handleSearch(prompt)}
                  >
                    <RotateCcw size={13} />
                    <span>Try Again</span>
                  </button>
                </>
              ) : response.error_type === 'candidates_filtered' ? (
                <>
                  <Filter size={32} className="hub-ai-empty-icon warn" />
                  <h4>Preferences Were Too Restrictive</h4>
                  <p>
                    {response.error_message ||
                      'Discovered matching movies in TMDB, but none satisfied all combined strict constraints.'}
                  </p>
                  <button
                    type="button"
                    className="hub-ai-broaden-btn"
                    style={{ marginTop: 12 }}
                    onClick={() => {
                      const broad = prompt.replace(/(only|strictly|must include)/gi, '').trim();
                      setPrompt(broad);
                      handleSearch(broad);
                    }}
                  >
                    <ArrowRight size={14} />
                    <span>Broaden Search Criteria</span>
                  </button>
                </>
              ) : (
                <>
                  <Compass size={32} className="hub-ai-empty-icon" />
                  <h4>No matching titles discovered</h4>
                  <p>
                    {response.error_message ||
                      'Try broadening your query keywords, selecting different eras, or exploring related genres.'}
                  </p>
                </>
              )}

              {/* UI Transparency & Funnel Analysis Card (Phase 5 Requirement C) */}
              {response.diagnostics && (
                <div className="hub-ai-transparency-card" role="region" aria-label="Search Transparency & Funnel Breakdown">
                  <div className="hub-ai-transparency-header">
                    <Sparkles size={14} className="transparency-icon" />
                    <span>Search Transparency &amp; Pipeline Funnel</span>
                  </div>

                  <div className="hub-ai-transparency-grid">
                    <div className="transparency-item">
                      <span className="transparency-k">Reference Movie</span>
                      <span className="transparency-v">
                        {response.diagnostics.reference_movie || response.interpreted_intent?.reference_title || 'None'}
                      </span>
                    </div>
                    <div className="transparency-item">
                      <span className="transparency-k">Required Country</span>
                      <span className="transparency-v">
                        {response.diagnostics.required_country || (response.interpreted_intent?.origin_country === 'IN' || response.interpreted_intent?.region === 'indian' ? 'India (IN)' : response.interpreted_intent?.origin_country || 'None (Global)')}
                      </span>
                    </div>
                    <div className="transparency-item">
                      <span className="transparency-k">Required Language</span>
                      <span className="transparency-v">
                        {response.diagnostics.required_language || (response.interpreted_intent?.is_explicit_language ? response.interpreted_intent?.language : 'None (All regional languages allowed)')}
                      </span>
                    </div>
                    <div className="transparency-item">
                      <span className="transparency-k">Preferred Genres &amp; Themes</span>
                      <span className="transparency-v">
                        {Array.from(new Set([
                          ...(response.interpreted_intent?.preferred_genres || response.interpreted_intent?.genres || []),
                          ...(response.interpreted_intent?.preferred_themes || response.interpreted_intent?.themes || []),
                        ])).join(', ') || 'General'}
                      </span>
                    </div>
                  </div>

                  {/* Funnel Counters */}
                  <div className="hub-ai-funnel-bar">
                    <div className="funnel-step">
                      <span className="funnel-count">{response.diagnostics.candidates_retrieved ?? response.diagnostics.raw_candidates_count ?? 0}</span>
                      <span className="funnel-label">Retrieved from TMDB</span>
                    </div>
                    <span className="funnel-arrow">&rarr;</span>
                    <div className="funnel-step">
                      <span className="funnel-count">{response.diagnostics.candidates_passing_hard_filters ?? response.diagnostics.eligible_candidates_count ?? 0}</span>
                      <span className="funnel-label">Passed Hard Filters</span>
                    </div>
                    <span className="funnel-arrow">&rarr;</span>
                    <div className="funnel-step">
                      <span className="funnel-count">{response.diagnostics.candidates_ranked ?? 0}</span>
                      <span className="funnel-label">Ranked</span>
                    </div>
                    <span className="funnel-arrow">&rarr;</span>
                    <div className="funnel-step highlight">
                      <span className="funnel-count">{response.recommendations.length}</span>
                      <span className="funnel-label">Selected</span>
                    </div>
                  </div>

                  {Boolean(response.diagnostics.recovery_attempted) && (
                    <div className="hub-ai-recovery-notice">
                      <Activity size={12} className="recovery-notice-icon" />
                      <span>
                        Automatic intelligent recovery was attempted ({(response.diagnostics.recovery_actions as string[] || []).map((a: string) => a.replace(/_/g, ' ')).join(', ') || 'adaptive discovery'}).
                      </span>
                    </div>
                  )}
                </div>
              )}
            </div>
          ) : response.presentation_sections && Object.keys(response.presentation_sections).length > 1 ? (
            /* Sectioned Presentation Layout (Requirement 6.4 & 7.1/7.3) */
            <div className="hub-ai-sections-container">
              {Object.entries(response.presentation_sections).map(([sectionName, sectionCards]) => {
                if (!sectionCards || sectionCards.length === 0) return null;
                return (
                  <div key={sectionName} className="hub-ai-presentation-group">
                    <div className="hub-ai-section-header">
                      <div className="hub-ai-section-title-wrap">
                        {sectionName === 'Best Matches' && <Sparkles size={16} className="sec-icon star" />}
                        {sectionName === 'Hidden Gems' && <Flame size={16} className="sec-icon gem" />}
                        {sectionName === 'More Like Your Request' && <Compass size={16} className="sec-icon compass" />}
                        {sectionName === 'Alternative Picks' && <Layers size={16} className="sec-icon layers" />}
                        <h3 className="hub-ai-section-title">{sectionName}</h3>
                        <span className="hub-ai-section-count">{sectionCards.length}</span>
                      </div>
                    </div>
                    <div className="hub-ai-cards-grid">
                      {sectionCards.map((rec) => renderMovieCard(rec))}
                    </div>
                  </div>
                );
              })}
            </div>
          ) : (
            /* Streamlined Card Grid Layout (Requirement 7.3) */
            <div className="hub-ai-cards-grid">
              {response.recommendations.map((rec) => renderMovieCard(rec))}
            </div>
          )}
        </div>
      )}

      {/* AI Search History Modal Window */}
      <AIHistoryModal
        isOpen={isHistoryOpen}
        onClose={() => setIsHistoryOpen(false)}
        history={history}
        onSelectQuery={handleSelectHistoryQuery}
        onDeleteQuery={handleDeleteHistoryItem}
        onClearHistory={handleClearHistory}
      />
    </section>
  );
};

export default AIRecommendationSection;
