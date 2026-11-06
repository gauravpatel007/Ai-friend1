import sys
sys.path.insert(0, ".")

from pydantic import BaseModel, Field
from typing import Optional
from app.api.movie_models import ParsedRecommendationIntent
from app.ai.movie_taxonomy import normalize_genre_name, LANGUAGE_AND_REGION_MAP, TMDB_MOVIE_GENRES

class EditedPreferenceModel(BaseModel):
    id: Optional[str] = None
    category: str = Field(default="theme")
    label: str
    value: str

def apply_edited_preferences_to_intent(intent: ParsedRecommendationIntent, edited_prefs, removed_prefs=None):
    intent_dict = intent.model_dump()
    new_intent = ParsedRecommendationIntent(**intent_dict)

    if edited_prefs is None:
        return new_intent

    prefs = []
    for p in edited_prefs:
        if isinstance(p, dict):
            prefs.append(EditedPreferenceModel(**p))
        else:
            prefs.append(p)

    rems = []
    for p in (removed_prefs or []):
        if isinstance(p, dict):
            rems.append(EditedPreferenceModel(**p))
        else:
            rems.append(p)

    # 1. Reference Title
    ref_chips = [p for p in prefs if p.category == 'ref']
    if ref_chips:
        new_intent.reference_title = ref_chips[0].value
        new_intent.reference_titles = [ref_chips[0].value]
    else:
        new_intent.reference_title = None
        new_intent.similar_to_title = None
        new_intent.reference_titles = []
        new_intent.reference_media = None
        new_intent.reference_genres = []
        if new_intent.intent_type == 'similar_to':
            new_intent.intent_type = 'general'

    # 2. Genres
    genre_names = []
    for p in prefs:
        if p.category == 'genre':
            norm = normalize_genre_name(p.value) or p.value
            genre_names.append(norm)
    new_intent.genres = list(dict.fromkeys(genre_names))
    new_intent.genres_any = new_intent.genres
    new_intent.genre_ids = [TMDB_MOVIE_GENRES[g] for g in new_intent.genres if g in TMDB_MOVIE_GENRES]

    # Exclude removed genres
    must_exclude = list(new_intent.must_exclude or [])
    for p in rems:
        if p.category == 'genre':
            norm = normalize_genre_name(p.value) or p.value
            if norm not in must_exclude:
                must_exclude.append(norm)
    new_intent.must_exclude = must_exclude

    # 3. Languages
    lang_codes = []
    for p in prefs:
        if p.category == 'lang':
            val_clean = p.value.strip().lower()
            if val_clean in LANGUAGE_AND_REGION_MAP:
                code = LANGUAGE_AND_REGION_MAP[val_clean].get("language")
                if code:
                    lang_codes.append(code)
            elif len(val_clean) == 2:
                lang_codes.append(val_clean)
            else:
                for lang_key, info in LANGUAGE_AND_REGION_MAP.items():
                    if val_clean in lang_key or lang_key in val_clean:
                        if info.get("language"):
                            lang_codes.append(info["language"])
                            break
    lang_codes = list(dict.fromkeys(lang_codes))
    new_intent.original_languages = lang_codes
    new_intent.languages = lang_codes
    new_intent.language = lang_codes[0] if len(lang_codes) == 1 else (lang_codes[0] if lang_codes else None)

    # 4. Themes
    new_intent.themes = [p.value for p in prefs if p.category == 'theme']

    # 5. Moods
    new_intent.moods = [p.value for p in prefs if p.category == 'mood']
    if new_intent.moods:
        new_intent.mood = new_intent.moods[0]

    # 6. Plot elements
    new_intent.plot_elements = [p.value for p in prefs if p.category == 'plot']

    # 7. Other preferences (e.g. underrated, recent, plot twists)
    keywords = list(new_intent.keywords or [])
    for p in prefs:
        if p.category == 'other':
            val_low = p.value.lower()
            if 'underrated' in val_low and 'underrated' not in keywords:
                keywords.append('underrated')
            if 'plot twist' in val_low and 'plot twist' not in new_intent.plot_elements:
                new_intent.plot_elements.append('plot twist')
            if 'recent' in val_low:
                new_intent.release_year_from = 2021
            if 'classic' in val_low:
                new_intent.release_year_to = 1990
    new_intent.keywords = keywords

    # Summary
    parts = []
    if new_intent.reference_title:
        parts.append(f"Like '{new_intent.reference_title}'")
    if new_intent.genres:
        parts.append(f"Genres: {', '.join(new_intent.genres)}")
    if new_intent.original_languages:
        parts.append(f"Languages: {', '.join(new_intent.original_languages)}")
    if new_intent.themes:
        parts.append(f"Themes: {', '.join(new_intent.themes)}")
    if new_intent.must_exclude:
        parts.append(f"Excluding: {', '.join(new_intent.must_exclude)}")
    new_intent.interpreted_summary = " | ".join(parts) or "Custom preference discovery"

    return new_intent

init_intent = ParsedRecommendationIntent(
    intent_type="similar_to",
    reference_title="Premalu",
    original_languages=["ml"],
    genres=["Romance", "Comedy"],
    themes=["Friendship", "Humor"],
)

edited = [
    {"category": "ref", "label": "Like: Premalu", "value": "Premalu"},
    {"category": "genre", "label": "Drama", "value": "Drama"},
    {"category": "theme", "label": "Emotional", "value": "Emotional"},
    {"category": "lang", "label": "Telugu", "value": "Telugu"},
    {"category": "theme", "label": "Family Drama", "value": "Family Drama"},
]
removed = [
    {"category": "genre", "label": "Romance", "value": "Romance"},
    {"category": "genre", "label": "Comedy", "value": "Comedy"},
    {"category": "lang", "label": "Malayalam", "value": "Malayalam"},
]

res = apply_edited_preferences_to_intent(init_intent, edited, removed)
print("Updated intent:")
print("  Reference title:", res.reference_title)
print("  Genres:", res.genres, "IDs:", res.genre_ids)
print("  Must exclude:", res.must_exclude)
print("  Languages:", res.original_languages)
print("  Themes:", res.themes)
print("  Summary:", res.interpreted_summary)
