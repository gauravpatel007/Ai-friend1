"""Canonical Movie Taxonomy and Dictionary for Intent Parsing & Discovery.

Maintains canonical mappings between:
- Genre names and TMDB genre IDs (Movie & TV).
- User slang and colloquial expressions (e.g. 'sci-fi', 'rom-com', 'whodunit').
- Mood descriptions, emotional tones, and related genres/themes.
- Plot element descriptors (e.g. 'unexpected endings', 'unreliable narrator', 'time loops').
- Regional cinema, language codes, and industry boundaries.
- Decade and temporal expressions (e.g. '90s', 'classic', 'post 2020').
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Set, Tuple

# ---------------------------------------------------------------------------
# 1. Canonical TMDB Genre Mappings
# ---------------------------------------------------------------------------
TMDB_MOVIE_GENRES: Dict[str, int] = {
    "Action": 28,
    "Adventure": 12,
    "Animation": 16,
    "Comedy": 35,
    "Crime": 80,
    "Documentary": 99,
    "Drama": 18,
    "Family": 10751,
    "Fantasy": 14,
    "History": 36,
    "Horror": 27,
    "Music": 10402,
    "Mystery": 9648,
    "Romance": 10749,
    "Science Fiction": 878,
    "TV Movie": 10770,
    "Thriller": 53,
    "War": 10752,
    "Western": 37,
}

TMDB_TV_GENRES: Dict[str, int] = {
    "Action & Adventure": 10759,
    "Animation": 16,
    "Comedy": 35,
    "Crime": 80,
    "Documentary": 99,
    "Drama": 18,
    "Family": 10751,
    "Kids": 10762,
    "Mystery": 9648,
    "News": 10763,
    "Reality": 10764,
    "Sci-Fi & Fantasy": 10765,
    "Soap": 10766,
    "Talk": 10767,
    "War & Politics": 10768,
    "Western": 37,
}

# Inverted mapping: ID -> Genre Name
TMDB_ID_TO_GENRE: Dict[int, str] = {v: k for k, v in TMDB_MOVIE_GENRES.items()}
TMDB_ID_TO_GENRE.update({v: k for k, v in TMDB_TV_GENRES.items()})

# Cross-type genre remapping (Movie ID -> TV ID)
MOVIE_TO_TV_GENRE_REMAP: Dict[int, int] = {
    28: 10759,   # Action -> Action & Adventure
    12: 10759,   # Adventure -> Action & Adventure
    878: 10765,  # Science Fiction -> Sci-Fi & Fantasy
    14: 10765,   # Fantasy -> Sci-Fi & Fantasy
    10752: 10768,# War -> War & Politics
}

# ---------------------------------------------------------------------------
# 2. Colloquial User Expression to Genre & Theme Decomposition
# ---------------------------------------------------------------------------
USER_EXPRESSION_DECOMPOSITION: Dict[str, Dict[str, Any]] = {
    "sci-fi": {"genres": ["Science Fiction"]},
    "scifi": {"genres": ["Science Fiction"]},
    "science fiction": {"genres": ["Science Fiction"]},
    "rom-com": {"genres": ["Romance", "Comedy"]},
    "romcom": {"genres": ["Romance", "Comedy"]},
    "romantic comedy": {"genres": ["Romance", "Comedy"]},
    "psychological thriller": {
        "genres": ["Thriller", "Mystery"],
        "themes": ["psychological", "mind games"],
        "moods": ["tense", "chilling"],
    },
    "psychological mystery": {
        "genres": ["Mystery", "Thriller"],
        "themes": ["psychological", "puzzle"],
        "moods": ["mind-bending", "suspenseful"],
    },
    "whodunit": {
        "genres": ["Mystery", "Crime"],
        "themes": ["whodunit", "detective", "murder mystery"],
        "moods": ["intriguing", "witty"],
    },
    "neo-noir": {
        "genres": ["Crime", "Thriller", "Drama"],
        "themes": ["neo-noir", "cynicism", "moral ambiguity"],
        "moods": ["dark", "gritty"],
    },
    "noir": {
        "genres": ["Crime", "Mystery", "Drama"],
        "themes": ["film noir", "detective"],
        "moods": ["dark", "bleak"],
    },
    "period drama": {
        "genres": ["Drama", "History"],
        "themes": ["period setting", "historical context"],
    },
    "period action": {
        "genres": ["Action", "History", "Drama"],
        "themes": ["historical conflict", "warrior", "rebellion"],
        "moods": ["epic"],
    },
    "survival": {
        "genres": ["Adventure", "Drama", "Thriller"],
        "themes": ["survival", "wilderness", "life or death"],
        "moods": ["intense", "gripping"],
    },
    "slasher": {
        "genres": ["Horror", "Thriller"],
        "themes": ["masked killer", "survival"],
        "moods": ["spine-chilling"],
    },
    "cyberpunk": {
        "genres": ["Science Fiction", "Thriller", "Action"],
        "themes": ["cyberpunk", "high tech low life", "AI consciousness", "dystopia"],
        "moods": ["dark", "atmospheric"],
    },
    "wall street": {
        "genres": ["Drama", "Crime", "Thriller"],
        "themes": ["financial collapse", "insider trading", "corporate greed"],
        "moods": ["tense", "fast-paced"],
    },
}

# ---------------------------------------------------------------------------
# 3. Mood Descriptions & Associated Semantic Expansions
# ---------------------------------------------------------------------------
MOOD_DICTIONARY: Dict[str, Dict[str, Any]] = {
    "mind-bending": {
        "canonical_mood": "mind-bending",
        "aliases": ["mind bending", "mind-boggling", "mindblowing", "trippy", "cerebral", "surreal", "reality bending"],
        "related_genres": ["Science Fiction", "Mystery", "Thriller"],
        "related_themes": ["psychological", "reality distortion", "simulation", "existentialism"],
        "related_plot_elements": ["plot twist", "temporal paradox", "unreliable narrator", "parallel universes"],
        "tmdb_keywords": ["plot twist", "psychological", "surrealism", "alternate reality", "time loop", "mind game"],
    },
    "feel-good": {
        "canonical_mood": "feel-good",
        "aliases": ["feel good", "heartwarming", "wholesome", "uplifting", "comforting", "cheerful"],
        "related_genres": ["Comedy", "Drama", "Family", "Romance"],
        "related_themes": ["friendship", "kindness", "triumph over adversity", "slice of life"],
        "related_plot_elements": ["heartwarming journey", "happy ending", "personal growth"],
        "tmdb_keywords": ["feel-good", "friendship", "heartwarming", "optimism", "coming of age"],
    },
    "cozy": {
        "canonical_mood": "cozy",
        "aliases": ["cozy evening", "comfort movie", "relaxing", "gentle", "chill evening"],
        "related_genres": ["Drama", "Comedy", "Romance", "Animation", "Family"],
        "related_themes": ["small town charm", "nostalgia", "comfort", "casual leisure"],
        "related_plot_elements": ["gentle humor", "intimate conversation"],
        "tmdb_keywords": ["small town", "nostalgia", "gentle", "family relationships"],
    },
    "dark_and_gritty": {
        "canonical_mood": "dark_and_gritty",
        "aliases": ["dark", "gritty", "bleak", "visceral", "hard-hitting", "raw", "cynical"],
        "related_genres": ["Crime", "Thriller", "Drama", "Action"],
        "related_themes": ["underworld", "corruption", "moral ambiguity", "urban decay"],
        "related_plot_elements": ["brutality", "uncompromising consequences"],
        "tmdb_keywords": ["neo-noir", "gritty", "corruption", "organized crime", "revenge"],
    },
    "spine-chilling": {
        "canonical_mood": "spine-chilling",
        "aliases": ["spine chilling", "terrifying", "scary", "creepy", "eerie", "haunting", "dread-inducing"],
        "related_genres": ["Horror", "Mystery", "Thriller"],
        "related_themes": ["supernatural dread", "haunting", "psychological terror"],
        "related_plot_elements": ["jump scares", "cursed entity", "macabre revelation"],
        "tmdb_keywords": ["haunting", "supernatural", "demonic possession", "isolation", "fear"],
    },
    "adrenaline": {
        "canonical_mood": "adrenaline",
        "aliases": ["adrenaline-rush", "action-packed", "fast-paced", "explosive", "high-octane", "intense action"],
        "related_genres": ["Action", "Thriller", "Adventure"],
        "related_themes": ["chases", "explosions", "heroic combat", "ticking clock"],
        "related_plot_elements": ["gun-fu", "stunts", "car chase", "hostage rescue"],
        "tmdb_keywords": ["assassin", "martial arts", "chase", "explosions", "shootout"],
    },
    "emotional": {
        "canonical_mood": "emotional",
        "aliases": ["tearjerker", "poignant", "heartbreaking", "melancholic", "touching", "sad"],
        "related_genres": ["Drama", "Romance"],
        "related_themes": ["grief", "loss", "sacrifice", "poignant love", "redemption"],
        "related_plot_elements": ["bittersweet climax", "terminal illness", "family estrangement"],
        "tmdb_keywords": ["tragedy", "loss of loved one", "sacrifice", "redemption"],
    },
    "witty": {
        "canonical_mood": "witty",
        "aliases": ["witty", "clever", "smart humor", "satirical", "sharp dialogue"],
        "related_genres": ["Comedy", "Mystery", "Drama"],
        "related_themes": ["whodunit", "satire", "eccentric detective"],
        "related_plot_elements": ["banter", "clever deduction", "ironic reveal"],
        "tmdb_keywords": ["satire", "black comedy", "witty dialogue", "eccentric"],
    },
}

# ---------------------------------------------------------------------------
# 4. Plot Element Descriptors & Concepts
# ---------------------------------------------------------------------------
PLOT_ELEMENT_DICTIONARY: Dict[str, Dict[str, Any]] = {
    "plot_twist": {
        "aliases": [
            "unexpected ending", "unexpected endings", "plot twist", "plot twists",
            "shocking twist", "shocking twists", "shocking reveal", "unexpected reveal",
            "twist ending", "twist endings", "unpredictable ending",
        ],
        "primary_genres": ["Mystery", "Thriller", "Drama"],
        "tmdb_keywords": ["plot twist", "surprise ending", "twist ending", "hidden identity"],
    },
    "unreliable_narrator": {
        "aliases": [
            "unreliable narrator", "unreliable narrators", "subjective reality",
            "hallucination", "delusion", "distorted memory", "false memory",
        ],
        "primary_genres": ["Mystery", "Thriller", "Drama"],
        "tmdb_keywords": ["unreliable narrator", "hallucination", "amnesia", "psychological"],
    },
    "time_loop": {
        "aliases": [
            "time loop", "time loops", "repeating day", "looping time",
            "temporal loop", "groundhog day", "stuck in time",
        ],
        "primary_genres": ["Science Fiction", "Mystery", "Comedy"],
        "tmdb_keywords": ["time loop", "repeating day", "temporal paradox", "time travel"],
    },
    "parallel_universes": {
        "aliases": [
            "parallel universe", "parallel universes", "multiverse",
            "alternate reality", "alternate realities", "alternate dimension",
            "quantum branching", "alternate timeline",
        ],
        "primary_genres": ["Science Fiction", "Adventure"],
        "tmdb_keywords": ["parallel universe", "multiverse", "alternate dimension", "alternate timeline"],
    },
    "reality_distortion": {
        "aliases": [
            "reality is not what it seems", "simulated reality", "simulation",
            "virtual reality", "matrix", "questioning reality",
        ],
        "primary_genres": ["Science Fiction", "Mystery", "Thriller"],
        "tmdb_keywords": ["simulated reality", "virtual reality", "matrix", "conspiracy", "existential"],
    },
    "detective_protagonist": {
        "aliases": [
            "intelligent detective", "detective protagonists", "brilliant detective",
            "detective mystery", "detective mysteries", "sleuth", "private investigator",
        ],
        "primary_genres": ["Mystery", "Crime"],
        "tmdb_keywords": ["detective", "police detective", "investigation", "clues", "whodunit"],
    },
    "revenge": {
        "aliases": ["revenge", "vengeance", "payback", "vigilante justice", "retribution"],
        "primary_genres": ["Thriller", "Action", "Crime"],
        "tmdb_keywords": ["revenge", "vengeance", "vigilante", "payback"],
    },
}

# ---------------------------------------------------------------------------
# 5. Language Codes, Regional Cinema, & Geographic Boundaries
# ---------------------------------------------------------------------------
LANGUAGE_AND_REGION_MAP: Dict[str, Dict[str, Any]] = {
    # Indian Cinema
    "malayalam": {"language": "ml", "region": "south_indian", "country": "IN"},
    "telugu": {"language": "te", "region": "south_indian", "country": "IN"},
    "tamil": {"language": "ta", "region": "south_indian", "country": "IN"},
    "kannada": {"language": "kn", "region": "south_indian", "country": "IN"},
    "hindi": {"language": "hi", "region": "bollywood", "country": "IN"},
    "bollywood": {"language": "hi", "region": "bollywood", "country": "IN"},
    "gujarati": {"language": "gu", "region": "gujarati", "country": "IN"},
    "marathi": {"language": "mr", "region": "indian", "country": "IN"},
    "bengali": {"language": "bn", "region": "indian", "country": "IN"},
    "indian": {"language": None, "region": "indian", "country": "IN"},
    "south indian": {"language": None, "region": "south_indian", "country": "IN"},

    # International Cinema
    "korean": {"language": "ko", "region": "international", "country": "KR"},
    "japanese": {"language": "ja", "region": "international", "country": "JP"},
    "spanish": {"language": "es", "region": "international", "country": "ES"},
    "french": {"language": "fr", "region": "international", "country": "FR"},
    "german": {"language": "de", "region": "international", "country": "DE"},
    "italian": {"language": "it", "region": "international", "country": "IT"},
    "hollywood": {"language": "en", "region": "hollywood", "country": "US"},
    "english": {"language": "en", "region": None, "country": None},
}

# ---------------------------------------------------------------------------
# 6. Temporal and Era Expressions
# ---------------------------------------------------------------------------
TEMPORAL_EXPRESSIONS: Dict[str, Dict[str, Optional[int]]] = {
    "90s": {"release_year_from": 1990, "release_year_to": 1999},
    "1990s": {"release_year_from": 1990, "release_year_to": 1999},
    "80s": {"release_year_from": 1980, "release_year_to": 1989},
    "1980s": {"release_year_from": 1980, "release_year_to": 1989},
    "70s": {"release_year_from": 1970, "release_year_to": 1979},
    "1970s": {"release_year_from": 1970, "release_year_to": 1979},
    "2000s": {"release_year_from": 2000, "release_year_to": 2009},
    "2010s": {"release_year_from": 2010, "release_year_to": 2019},
    "after 2020": {"release_year_from": 2021, "release_year_to": None},
    "post 2020": {"release_year_from": 2021, "release_year_to": None},
    "recent": {"release_year_from": 2022, "release_year_to": None},
    "classic": {"release_year_from": None, "release_year_to": 1989},
}


def normalize_genre_name(genre_candidate: str) -> Optional[str]:
    """Normalize any user/model genre string to canonical TMDB movie genre name."""
    cand = genre_candidate.strip().lower()
    if cand.endswith("ies"):
        cand_stem = cand[:-3] + "y"
    else:
        cand_stem = cand.rstrip("s")

    for canonical in TMDB_MOVIE_GENRES:
        if cand == canonical.lower() or cand_stem == canonical.lower():
            return canonical

    # Check expression decomposition
    if cand in USER_EXPRESSION_DECOMPOSITION:
        decomp = USER_EXPRESSION_DECOMPOSITION[cand]
        if decomp.get("genres"):
            return decomp["genres"][0]

    # Substring matching for plural or variants (e.g. 'thrillers' -> 'Thriller')
    for canonical in TMDB_MOVIE_GENRES:
        c_low = canonical.lower()
        if cand.startswith(c_low) or c_low.startswith(cand) or cand_stem.startswith(c_low) or c_low.startswith(cand_stem):
            return canonical

    return None


def resolve_mood_semantics(mood_term: str) -> Optional[Dict[str, Any]]:
    """Look up a mood term and return its semantic expansion dictionary."""
    clean = mood_term.strip().lower().replace("-", "_").replace(" ", "_")
    for key, data in MOOD_DICTIONARY.items():
        if clean == key or clean == data["canonical_mood"].replace("-", "_"):
            return data
        if any(alias in mood_term.lower() for alias in data["aliases"]):
            return data
    return None


def resolve_plot_elements(query_text: str) -> List[Dict[str, Any]]:
    """Detect plot element concepts present in user query."""
    q_lower = query_text.lower()
    matches: List[Dict[str, Any]] = []
    for concept, data in PLOT_ELEMENT_DICTIONARY.items():
        if any(alias in q_lower for alias in data["aliases"]):
            matches.append(data)
    return matches


# ---------------------------------------------------------------------------
# 7. Canonical TMDB Keyword IDs (for Plot Tropes, Themes & Elements)
# ---------------------------------------------------------------------------
TMDB_KEYWORD_IDS: Dict[str, int] = {
    "plot twist": 9799,
    "plot twists": 9799,
    "surprise ending": 10839,
    "twist ending": 10839,
    "time loop": 156828,
    "time loops": 156828,
    "temporal paradox": 156828,
    "time travel": 4379,
    "unreliable narrator": 214540,
    "unreliable narrators": 214540,
    "parallel universe": 9663,
    "parallel universes": 9663,
    "multiverse": 209714,
    "alternate reality": 160352,
    "alternate dimension": 156321,
    "simulated reality": 180547,
    "virtual reality": 4563,
    "detective": 703,
    "police detective": 156360,
    "private investigator": 2041,
    "whodunit": 10714,
    "murder mystery": 9748,
    "investigation": 14624,
    "revenge": 9748,
    "vengeance": 9748,
    "assassin": 3258,
    "survival": 10084,
    "psychological": 9937,
    "psychological thriller": 12565,
    "mind game": 161176,
    "amnesia": 1568,
    "hallucination": 156363,
    "heist": 10051,
    "serial killer": 10714,
    "artificial intelligence": 310,
    "supernatural": 9715,
    "haunting": 10224,
    "dystopia": 4565,
    "dystopian future": 4565,
    "neo-noir": 9882,
    "martial arts": 779,
    "dark comedy": 9716,
    "black comedy": 9716,
    "conspiracy": 10453,
    "existential": 10321,
    "existentialism": 10321,
    "alien": 9951,
    "cyberpunk": 12190,
    "space travel": 9887,
    "isolation": 10084,
    "hostage": 9744,
    "corruption": 4152,
}


def resolve_keyword_ids(keywords: List[str], tmdb_client: Optional[Any] = None) -> List[int]:
    """Resolve a list of keyword strings to verified TMDB integer keyword IDs.
    
    Checks pre-mapped canonical taxonomy first; falls back to dynamic TMDB
    keyword search if a configured TMDBClient is provided.
    """
    resolved_ids: List[int] = []
    seen_ids: Set[int] = set()

    for kw in keywords:
        clean = kw.strip().lower()
        if not clean:
            continue

        # 1. Exact match in pre-mapped dictionary
        if clean in TMDB_KEYWORD_IDS:
            kid = TMDB_KEYWORD_IDS[clean]
            if kid not in seen_ids:
                seen_ids.add(kid)
                resolved_ids.append(kid)
            continue

        # Check singular stem
        clean_stem = clean.rstrip("s")
        if clean_stem in TMDB_KEYWORD_IDS:
            kid = TMDB_KEYWORD_IDS[clean_stem]
            if kid not in seen_ids:
                seen_ids.add(kid)
                resolved_ids.append(kid)
            continue

        # 2. Dynamic TMDB keyword search if client is available
        if tmdb_client and hasattr(tmdb_client, "search_keywords"):
            try:
                results = tmdb_client.search_keywords(clean)
                if results:
                    # Pick best match: exact name match first, else first result
                    picked_id = None
                    for r in results:
                        if (r.get("name") or "").lower() == clean:
                            picked_id = int(r["id"])
                            break
                    if not picked_id and results[0].get("id"):
                        picked_id = int(results[0]["id"])

                    if picked_id and picked_id not in seen_ids:
                        seen_ids.add(picked_id)
                        resolved_ids.append(picked_id)
            except Exception:
                pass

    return resolved_ids
