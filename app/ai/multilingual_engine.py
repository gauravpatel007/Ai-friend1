"""Multilingual Communication Engine for Bond.

Handles:
1. Accurate Language Detection for Native Scripts and Romanized Indic (Gujlish, Hinglish).
2. Authoritative System Prompt Directives for Target Language & Script (Native vs Romanized).
3. Transliteration safety nets for Gujarati & Devanagari Romanization.
4. TTS Engine Language Compatibility Matrix & Limitations Validation.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from app.utils.logger import get_logger

logger = get_logger(__name__)

# ─── Language Metadata Registry ───────────────────────────────────────

SUPPORTED_LANGUAGES: Dict[str, Dict[str, Any]] = {
    "en": {
        "code": "en",
        "name": "English",
        "native_name": "English",
        "script": "latin",
        "stt_supported": True,
    },
    "gu": {
        "code": "gu",
        "name": "Gujarati",
        "native_name": "ગુજરાતી",
        "script": "gujarati",
        "stt_supported": True,
    },
    "hi": {
        "code": "hi",
        "name": "Hindi",
        "native_name": "हिन्दी",
        "script": "devanagari",
        "stt_supported": True,
    },
}

SUPPORTED_STT_LANGUAGES: Dict[str, Dict[str, Any]] = {
    "auto": {
        "code": "auto",
        "name": "Automatic detection (English, Gujarati, Hindi only)",
        "native_name": "Auto-detect",
        "script": "auto",
        "stt_supported": True,
    },
    "en": {
        "code": "en",
        "name": "English",
        "native_name": "English",
        "script": "latin",
        "stt_supported": True,
    },
    "gu": {
        "code": "gu",
        "name": "Gujarati",
        "native_name": "ગુજરાતી",
        "script": "gujarati",
        "stt_supported": True,
    },
    "hi": {
        "code": "hi",
        "name": "Hindi",
        "native_name": "हिन्दी",
        "script": "devanagari",
        "stt_supported": True,
    },
}

# ─── Indic Romanized & Script Lexicons ────────────────────────────────

# High-frequency English functional words (stopwords, pronouns, auxiliaries, prepositions, and common queries)
# Used as a contrastive filter to prevent misclassifying ordinary English as Gujarati
_ENGLISH_CONTRASTIVE_WORDS = {
    "a", "about", "above", "after", "again", "against", "all", "am", "an", "and", "any", "are",
    "aren't", "as", "at", "be", "because", "been", "before", "being", "below", "between", "both",
    "but", "by", "can", "can't", "cannot", "could", "couldn't", "did", "didn't", "do", "does",
    "doesn't", "doing", "don't", "down", "during", "each", "few", "for", "from", "further", "had",
    "hadn't", "has", "hasn't", "have", "haven't", "having", "he", "he'd", "he'll", "he's", "her",
    "here", "here's", "hers", "herself", "him", "himself", "his", "how", "how's", "i", "i'd",
    "i'll", "i'm", "i've", "if", "in", "into", "is", "isn't", "it", "it's", "its", "itself",
    "let's", "me", "more", "most", "mustn't", "my", "myself", "no", "nor", "not", "of", "off",
    "on", "once", "only", "or", "other", "ought", "our", "ours", "ourselves", "out", "over", "own",
    "same", "shan't", "she", "she'd", "she'll", "she's", "should", "shouldn't", "so", "some", "such",
    "than", "that", "that's", "the", "their", "theirs", "them", "themselves", "then", "there",
    "there's", "these", "they", "they'd", "they'll", "they're", "they've", "this", "those",
    "through", "to", "too", "under", "until", "up", "very", "was", "wasn't", "we", "we'd", "we'll",
    "we're", "we've", "were", "weren't", "what", "what's", "when", "when's", "where", "where's",
    "which", "while", "who", "who's", "whom", "why", "why's", "with", "won't", "would", "wouldn't",
    "you", "you'd", "you'll", "you're", "you've", "your", "yours", "yourself", "yourselves",
    # Common English technical, conversation, and action verbs
    "code", "help", "please", "thanks", "thank", "write", "explain", "create", "test", "file",
    "tell", "show", "give", "make", "find", "check", "run", "open", "close", "see", "look", "think",
    "know", "today", "tomorrow", "time", "day", "said", "say", "talk", "chat", "good", "fine",
}

# Distinctive Gujarati Romanized Tokens (Gujlish) with linguistic weight
_GUJARATI_ROMAN_TOKENS = {
    # Verb auxiliaries and inflections (Unique to Gujarati)
    "che": 5, "chhe": 5, "ce": 4, "cho": 5, "chho": 5, "chu": 5, "chhu": 5,
    "nathi": 5, "hato": 4, "hati": 4, "hatu": 4, "hata": 4,
    "joiye": 5, "joye": 4, "avjo": 5, "aavo": 4, "jajo": 5,
    "karo": 3, "karta": 3, "kare": 3, "karu": 4, "karshe": 4, "karsho": 4, "kro": 3,
    "bol": 3, "bolo": 4, "kaho": 4, "aapjo": 5, "aapo": 5, "apo": 4,
    "maliye": 5, "maline": 5, "thayo": 5, "thay": 4, "thashe": 4,
    "raho": 4, "rahe": 4, "raheta": 4, "gaya": 3, "gayi": 3, "gayo": 3,
    "chale": 4, "chalo": 3, "aavadtu": 5, "jamya": 4, "thik": 3, "shikhvo": 5,

    # Pronouns and Possessives (Unique to Gujarati)
    "tamaru": 5, "tamari": 5, "tamaro": 5, "tamara": 5, "tamne": 5,
    "taru": 5, "tari": 5, "taro": 5, "tara": 5, "tane": 5,
    "maru": 5, "mari": 5, "maro": 5, "mara": 5, "mane": 5,
    "aapnu": 5, "aapna": 5, "aapne": 4, "tame": 5, "ame": 4, "amne": 4,
    "hu": 5, "hoon": 4, "hun": 4, "tme": 4, "temne": 4, "temnu": 5,
    "ene": 4, "enu": 4,

    # Question words (Unique to Gujarati)
    "shu": 5, "su": 4, "soo": 4, "kem": 5, "kyare": 5, "kya": 3, "kyaan": 4, "kyaa": 4,
    "kon": 4, "kevu": 5, "kevo": 5, "kevi": 5, "ketla": 5, "ketli": 5, "ketlu": 5,
    "sha": 4,

    # Conversational Phrases, Adverbs, Idioms & Postpositions
    "majama": 5, "maja": 4, "maza": 3, "saru": 4, "saroo": 4,
    "aabhar": 5, "dhanyavad": 3, "swagat": 4, "khabar": 4,
    "jawab": 5, "javav": 4, "zavab": 4, "jawaab": 5,
    "gujarati": 5, "gujaratima": 5, "naam": 4, "saathe": 5, "mate": 4,
    "pachhi": 5, "pahela": 5, "sudhi": 5, "aaje": 4, "kaale": 5, "bapore": 5,
    "saanje": 4, "savaare": 4, "khub": 4, "badhu": 4, "dost": 3, "mitra": 3,
    "bhai": 3, "ben": 3, "krupa": 4, "varta": 4,
}

# Distinctive Hindi Romanized Tokens (Hinglish) with linguistic weight
_HINDI_ROMAN_TOKENS = {
    # Pronouns & Possessives
    "aapka": 5, "aapki": 5, "aapke": 5,
    "tumhara": 5, "tumhari": 5, "tumhare": 5,
    "mera": 5, "meri": 5, "mere": 5,
    "hamara": 5, "hamari": 5, "hamare": 5,
    "hum": 3, "aap": 3, "tum": 3, "main": 3,
    "mujhe": 5, "tujhe": 5, "humein": 5,
    # Question words
    "kya": 4, "kaise": 5, "kaisa": 4, "kaisi": 4,
    "kab": 4, "kahan": 5, "kaha": 3, "kidhar": 5, "kaun": 4,
    "kitna": 4, "kitni": 4, "kitne": 4,
    # Verbs & Auxiliaries
    "hai": 5, "hain": 5, "hoon": 4, "hun": 3,
    "hoga": 3, "hogi": 3, "hoge": 3,
    "tha": 4, "thi": 4,
    "nahi": 4, "nahin": 4, "mat": 2, "chahiye": 4,
    "karein": 4, "karta": 3, "karti": 3, "rahe": 3, "raha": 4, "rahi": 4,
    # Conversational Phrases & Words
    "namaste": 5, "shukriya": 5, "theek": 3, "bahut": 4, "achha": 4, "achhi": 4,
    "batao": 4, "bataiye": 5, "hindi": 5,
}

# Distinctive Gujarati Bigram Collocations
_GUJARATI_BIGRAMS = {
    ("kem", "cho"), ("kem", "chho"), ("su", "che"), ("shu", "che"), ("su", "chhe"), ("shu", "chhe"),
    ("tamaru", "naam"), ("tamaru", "name"), ("taru", "naam"), ("taru", "name"),
    ("shu", "karo"), ("su", "karo"), ("karo", "cho"), ("karo", "chho"),
    ("kare", "che"), ("kare", "chhe"), ("maja", "ma"), ("maza", "ma"),
    ("ma", "chu"), ("ma", "chhu"), ("jawab", "aapo"), ("jawab", "apo"),
    ("zavab", "aapo"), ("kya", "raho"), ("kya", "rahe"), ("raho", "cho"),
    ("gujarati", "ma"), ("khub", "aabhar"), ("aanand", "thayo"), ("maline", "aanand"),
    ("tame", "shu"), ("tame", "su"), ("hu", "maja"), ("hoon", "maja"),
}

# Distinctive Hindi Bigram Collocations
_HINDI_BIGRAMS = {
    ("aapka", "naam"), ("kya", "hai"), ("kaise", "ho"), ("kaise", "hain"),
    ("mera", "naam"), ("kar", "rahe"), ("rahe", "ho"), ("hindi", "me"),
    ("kya", "kar"), ("bataiye", "mujhe"),
}

# High-fidelity Roman-to-Gujarati Word Lexicon
COMMON_ROMAN_TO_GUJARATI_WORDS = {
    "kem": "કેમ", "cho": "છો", "chho": "છો", "tamaru": "તમારું", "tamari": "તમારી",
    "tamaro": "તમારો", "tamara": "તમારા", "taru": "તારું", "tari": "તારી", "taro": "તારો",
    "tara": "તારા", "maru": "મારું", "mari": "મારી", "maro": "મારો", "mara": "મારા",
    "naam": "નામ", "name": "નામ", "su": "શું", "shu": "શું", "soo": "શું",
    "che": "છે", "chhe": "છે", "tame": "તમે", "tme": "તમે", "karo": "કરો", "kro": "કરો",
    "mane": "મને", "gujarati": "ગુજરાતી", "gujaratima": "ગુજરાતીમાં", "ma": "માં",
    "jawab": "જવાબ", "zavab": "જવાબ", "javav": "જવાબ", "jawaab": "જવાબ",
    "aapo": "આપો", "apo": "આપો", "aapjo": "આપજો", "hu": "હું", "hoon": "હું", "hun": "હું",
    "maja": "મજા", "maza": "મજા", "majama": "મજામાં", "chu": "છું", "chhu": "છું",
    "kya": "ક્યાં", "kyaa": "ક્યાં", "kyaan": "ક્યાં", "raho": "રહો", "rahe": "રહે",
    "aabhar": "આભાર", "khub": "ખૂબ", "saru": "સારું", "badhu": "બધું", "nathi": "નથી",
    "ha": "હા", "na": "ના", "madad": "મદદ", "kon": "કોણ", "chale": "ચાલે",
    "tamne": "તમને", "maline": "મળીને", "aanand": "આનંદ", "thayo": "થયો",
    "dost": "દોસ્ત", "bond": "બોન્ડ", "divas": "દિવસ", "aaje": "આજે", "kaale": "કાલે",
    "pachhi": "પછી", "bolo": "બોલો", "kaho": "કહો", "swagat": "સ્વાગત",
    "ek": "એક", "be": "બે", "tran": "ત્રણ", "chaar": "ચાર", "paanch": "પાંચ",
    "shikhvo": "શીખવો", "varta": "વાર્તા", "mitra": "મિત્ર", "bhai": "ભાઈ", "ben": "બહેન",
    "tamne": "તમને", "tane": "તને", "amne": "અમને", "ame": "અમે",
}

# Idiomatic Pattern Knowledge Base: (Regex, Canonical Roman, Native Gujarati Script, Intent, English Gloss)
_IDIOM_PATTERNS = [
    # 1. Kem cho?
    (
        re.compile(r"\b(kem|kkm|km)\s+(cho|chho)\b", re.IGNORECASE),
        "Kem cho?",
        "કેમ છો?",
        "greeting",
        "How are you?",
    ),
    # 2. Tamaru naam su che?
    (
        re.compile(r"\b(tamaru|tmaru|taru)\s+(naam|name)\s+(su|shu|soo)\s+(che|chhe)\b", re.IGNORECASE),
        "Tamaru naam shu che?",
        "તમારું નામ શું છે?",
        "asking_name",
        "What is your name?",
    ),
    # 3. Tame shu karo cho?
    (
        re.compile(r"\b(tame|tme|tu)?\s*(su|shu|soo)\s+(karo|kro|kare)\s+(cho|chho|che|chhe)\b", re.IGNORECASE),
        "Tame shu karo cho?",
        "તમે શું કરો છો?",
        "asking_activity",
        "What are you doing?",
    ),
    # 4. Mane Gujarati ma jawab aapo
    (
        re.compile(r"\b(mane\s+)?gujarati\s*(ma|maa)?\s*(jawab|javav|zavab)?\s*(aapo|apo|bolo|kaho)\b", re.IGNORECASE),
        "Mane Gujarati ma jawab aapo",
        "મને ગુજરાતીમાં જવાબ આપો",
        "request_language_gujarati",
        "Answer me in Gujarati / Speak in Gujarati",
    ),
    # 5. Hu maja ma chu
    (
        re.compile(r"\b(hu|hoon|hun)?\s*(maja|majama|maza)\s*(ma)?\s*(chu|chhu)\b", re.IGNORECASE),
        "Hu maja ma chu",
        "હું મજામાં છું",
        "status_wellbeing",
        "I am fine / I am doing great",
    ),
    # 6. Tame kya raho cho?
    (
        re.compile(r"\b(tame|tme|tu)?\s*(kya|kyaan|kyaa)\s*(raho|rahe)\s*(cho|chho|che|chhe)\b", re.IGNORECASE),
        "Tame kya raho cho?",
        "તમે ક્યાં રહો છો?",
        "asking_location",
        "Where do you live?",
    ),
    # 7. Tamne maline aanand thayo
    (
        re.compile(r"\btamne\s+maline\s+aanand\s+thayo\b", re.IGNORECASE),
        "Tamne maline aanand thayo",
        "તમને મળીને આનંદ થયો",
        "pleasantry",
        "Pleased to meet you",
    ),
    # 8. Khub aabhar / aabhar
    (
        re.compile(r"\b(khub\s+)?aabhar\b", re.IGNORECASE),
        "Khub aabhar",
        "ખૂબ આભાર",
        "gratitude",
        "Thank you very much",
    ),
    # 9. Shu chale che?
    (
        re.compile(r"\b(shu|su|soo)\s+(chale|chaale)\s+(che|chhe)\b", re.IGNORECASE),
        "Shu chale che?",
        "શું ચાલે છે?",
        "greeting_status",
        "What's going on? / What's up?",
    ),
    # 10. Tame kon cho?
    (
        re.compile(r"\b(tame|tme|tu)\s+kon\s+(cho|chho|che|chhe)\b", re.IGNORECASE),
        "Tame kon cho?",
        "તમે કોણ છો?",
        "asking_identity",
        "Who are you?",
    ),
    # 11. Mane madad karo
    (
        re.compile(r"\b(mane\s+)?madad\s+(karo|joiye|apo)\b", re.IGNORECASE),
        "Mane madad karo",
        "મને મદદ કરો",
        "request_help",
        "Please help me",
    ),
    # 12. Kaale maliye / Pachhi maliye
    (
        re.compile(r"\b(kaale|pachhi)\s+maliye\b", re.IGNORECASE),
        "Kaale maliye",
        "કાલે મળીએ",
        "farewell",
        "See you tomorrow / See you later",
    ),
    # 13. Tamari umar ketli che?
    (
        re.compile(r"\b(tamari|tari)\s+umar\s+(ketli|ketlu)\s+(che|chhe)\b", re.IGNORECASE),
        "Tamari umar ketli che?",
        "તમારી ઉંમર કેટલી છે?",
        "asking_age",
        "How old are you?",
    ),
    # 14. Saru che / Badhu saru che
    (
        re.compile(r"\b(badhu\s+)?(saru|saroo)\s+(che|chhe)\b", re.IGNORECASE),
        "Badhu saru che",
        "બધું સારું છે",
        "statement_all_good",
        "Everything is fine / all good",
    ),
]


@dataclass
class NormalizedGujarati:
    """Detailed linguistic normalization metadata for Romanized Gujarati (Gujlish)."""
    raw_input: str
    is_gujarati: bool
    confidence: float
    canonical_roman: str
    native_script: str
    semantic_intent: str
    english_gloss: str
    detected_markers: List[str]


class RomanGujaratiNormalizer:
    """Linguistic intelligence normalizer and semantic ground-truth resolver for Roman Gujarati (Gujlish)."""

    @classmethod
    def is_roman_gujarati(cls, text: str) -> bool:
        """Convenience method checking whether text is Romanized Gujarati."""
        return cls.classify_and_normalize(text).is_gujarati

    @classmethod
    def phonological_latin_to_gu(cls, word: str) -> str:
        """Phonological fallback converting Latin letters to authentic Gujarati Unicode script."""
        CONSONANTS = {
            "chh": "છ", "kh": "ખ", "gh": "ઘ", "ch": "ચ", "zh": "ઝ",
            "th": "થ", "dh": "ધ", "ph": "ફ", "bh": "ભ", "sh": "શ",
            "k": "ક", "g": "ગ", "c": "ક", "j": "જ", "z": "ઝ",
            "t": "ત", "d": "દ", "n": "ન", "p": "પ", "f": "ફ",
            "b": "બ", "m": "મ", "y": "ય", "r": "ર", "l": "લ",
            "v": "વ", "w": "વ", "s": "સ", "h": "હ",
        }
        INITIAL_VOWELS = {
            "aa": "આ", "a": "અ", "ee": "ઈ", "i": "ઇ", "oo": "ઊ", "u": "ઉ",
            "e": "એ", "ai": "ઐ", "o": "ઓ", "au": "ઔ",
        }
        MATRAS = {
            "aa": "ા", "a": "", "ee": "ી", "i": "િ", "oo": "ૂ", "u": "ુ",
            "e": "ે", "ai": "ૈ", "o": "ો", "au": "ૌ",
        }

        w = word.lower()
        n = len(w)
        i = 0
        res = []
        prev_was_consonant = False

        while i < n:
            matched_consonant = None
            for clen in (3, 2, 1):
                cand = w[i : i + clen]
                if cand in CONSONANTS:
                    matched_consonant = CONSONANTS[cand]
                    step = clen
                    break

            if matched_consonant:
                if prev_was_consonant:
                    res.append("્")  # Virama
                res.append(matched_consonant)
                prev_was_consonant = True
                i += step
                continue

            matched_vowel = None
            for vlen in (2, 1):
                cand = w[i : i + vlen]
                if prev_was_consonant and cand in MATRAS:
                    matched_vowel = MATRAS[cand]
                    step = vlen
                    break
                elif not prev_was_consonant and cand in INITIAL_VOWELS:
                    matched_vowel = INITIAL_VOWELS[cand]
                    step = vlen
                    break

            if matched_vowel is not None:
                res.append(matched_vowel)
                prev_was_consonant = False
                i += step
                continue

            res.append(w[i])
            prev_was_consonant = False
            i += 1

        return "".join(res)

    @classmethod
    def transliterate_to_native_script(cls, text: str) -> str:
        """Transliterate Roman Gujarati sentence to native Gujarati script using dictionary + phonology."""
        words = text.split(" ")
        res = []
        for w in words:
            m = re.match(r"^([a-zA-Z]+)([^a-zA-Z]*)$", w)
            if m:
                core, punct = m.group(1).lower(), m.group(2)
                if core in COMMON_ROMAN_TO_GUJARATI_WORDS:
                    res.append(COMMON_ROMAN_TO_GUJARATI_WORDS[core] + punct)
                else:
                    res.append(cls.phonological_latin_to_gu(core) + punct)
            else:
                res.append(w)
        return " ".join(res)

    @classmethod
    def classify_and_normalize(cls, text: str) -> NormalizedGujarati:
        """Analyze text, distinguish from English and Hindi, and return rich normalized representation."""
        cleaned = text.strip()
        words = re.findall(r"\b[a-zA-Z]+\b", cleaned.lower())
        if not words:
            return NormalizedGujarati(
                raw_input=cleaned,
                is_gujarati=False,
                confidence=0.0,
                canonical_roman=cleaned,
                native_script=cleaned,
                semantic_intent="unknown",
                english_gloss=cleaned,
                detected_markers=[],
            )

        total_words = len(words)
        eng_matches = sum(1 for w in words if w in _ENGLISH_CONTRASTIVE_WORDS)

        gu_score = 0
        gu_markers: List[str] = []
        for w in words:
            if w in _GUJARATI_ROMAN_TOKENS:
                gu_score += _GUJARATI_ROMAN_TOKENS[w]
                gu_markers.append(w)

        hi_score = 0
        for w in words:
            if w in _HINDI_ROMAN_TOKENS:
                hi_score += _HINDI_ROMAN_TOKENS[w]

        # Bigram evaluations
        for i in range(len(words) - 1):
            bg = (words[i], words[i + 1])
            if bg in _GUJARATI_BIGRAMS:
                gu_score += 8
                gu_markers.append(f"{bg[0]} {bg[1]}")
            if bg in _HINDI_BIGRAMS:
                hi_score += 8

        # Contrastive English Filter:
        # If English functional vocabulary constitutes 60%+ of tokens and there is no overwhelming Gujarati evidence,
        # classify as English to prevent false positives on phrases like "What do you do?", "Where is he going?", etc.
        if eng_matches / total_words >= 0.6:
            if gu_score < 4 or gu_score <= hi_score:
                return NormalizedGujarati(
                    raw_input=cleaned,
                    is_gujarati=False,
                    confidence=0.0,
                    canonical_roman=cleaned,
                    native_script=cleaned,
                    semantic_intent="english",
                    english_gloss=cleaned,
                    detected_markers=[],
                )

        is_gu = (gu_score >= 3 and gu_score >= hi_score)
        if not is_gu:
            return NormalizedGujarati(
                raw_input=cleaned,
                is_gujarati=False,
                confidence=0.0,
                canonical_roman=cleaned,
                native_script=cleaned,
                semantic_intent="other",
                english_gloss=cleaned,
                detected_markers=[],
            )

        # Matched as Gujarati! Check idiomatic pattern library for precise canonical normalization
        conf = min(0.99, 0.65 + (gu_score * 0.05))
        for pat, canonical, native, intent, gloss in _IDIOM_PATTERNS:
            if pat.search(cleaned):
                return NormalizedGujarati(
                    raw_input=cleaned,
                    is_gujarati=True,
                    confidence=conf,
                    canonical_roman=canonical,
                    native_script=native,
                    semantic_intent=intent,
                    english_gloss=gloss,
                    detected_markers=gu_markers,
                )

        # General Gujarati input not matching a fixed idiom
        native_script = cls.transliterate_to_native_script(cleaned)
        return NormalizedGujarati(
            raw_input=cleaned,
            is_gujarati=True,
            confidence=conf,
            canonical_roman=cleaned,
            native_script=native_script,
            semantic_intent="conversational",
            english_gloss=f"User query in Gujarati: '{cleaned}'",
            detected_markers=gu_markers,
        )


@dataclass
class DetectedLanguage:
    """Result of language detection."""
    code: str
    name: str
    confidence: float
    is_romanized: bool = False
    detected_script: str = "latin"
    normalized_gujarati: Optional[NormalizedGujarati] = None

    @property
    def is_transliterated(self) -> bool:
        return self.is_romanized


class MultilingualEngine:
    """Core intelligence engine for language detection, prompt engineering, and script formatting."""

    @staticmethod
    def detect_language(text: str) -> DetectedLanguage:
        """Accurately identify input language supporting both native scripts and Romanized Indic.
        
        Correctly recognizes 'Tamaru naam su che?' as Gujarati (Romanized) rather than Hindi.
        """
        cleaned = text.strip()
        if not cleaned:
            return DetectedLanguage(code="en", name="English", confidence=1.0)

        # 1. Native Unicode Script Block Detection
        gu_chars = sum(1 for c in cleaned if 0x0A80 <= ord(c) <= 0x0AFF)
        hi_chars = sum(1 for c in cleaned if 0x0900 <= ord(c) <= 0x097F)
        bn_chars = sum(1 for c in cleaned if 0x0980 <= ord(c) <= 0x09FF)
        ta_chars = sum(1 for c in cleaned if 0x0B80 <= ord(c) <= 0x0BFF)
        te_chars = sum(1 for c in cleaned if 0x0C00 <= ord(c) <= 0x0C7F)
        pa_chars = sum(1 for c in cleaned if 0x0A00 <= ord(c) <= 0x0A7F)
        ja_chars = sum(1 for c in cleaned if (0x3040 <= ord(c) <= 0x309F) or (0x30A0 <= ord(c) <= 0x30FF))
        zh_chars = sum(1 for c in cleaned if 0x4E00 <= ord(c) <= 0x9FFF)

        total_alpha = sum(1 for c in cleaned if c.isalpha())
        if total_alpha > 0:
            if gu_chars / total_alpha > 0.2:
                return DetectedLanguage(code="gu", name="Gujarati", confidence=0.98, is_romanized=False, detected_script="gujarati")
            if hi_chars / total_alpha > 0.2:
                return DetectedLanguage(code="hi", name="Hindi", confidence=0.98, is_romanized=False, detected_script="devanagari")
            if bn_chars / total_alpha > 0.2:
                return DetectedLanguage(code="bn", name="Bengali", confidence=0.98, is_romanized=False, detected_script="bengali")
            if ta_chars / total_alpha > 0.2:
                return DetectedLanguage(code="ta", name="Tamil", confidence=0.98, is_romanized=False, detected_script="tamil")
            if te_chars / total_alpha > 0.2:
                return DetectedLanguage(code="te", name="Telugu", confidence=0.98, is_romanized=False, detected_script="telugu")
            if pa_chars / total_alpha > 0.2:
                return DetectedLanguage(code="pa", name="Punjabi", confidence=0.98, is_romanized=False, detected_script="gurmukhi")
            if ja_chars / total_alpha > 0.2:
                return DetectedLanguage(code="ja", name="Japanese", confidence=0.98, is_romanized=False, detected_script="japanese")
            if zh_chars / total_alpha > 0.3:
                return DetectedLanguage(code="zh", name="Chinese", confidence=0.98, is_romanized=False, detected_script="cjk")

        # 2. Romanized Script & English Analysis
        words = re.findall(r"\b[a-zA-Z]+\b", cleaned.lower())
        if not words:
            return DetectedLanguage(code="en", name="English", confidence=1.0)

        # Check Roman Gujarati Normalizer first
        norm_gu = RomanGujaratiNormalizer.classify_and_normalize(cleaned)
        if norm_gu.is_gujarati:
            logger.debug(
                "[MULTILINGUAL] Roman Gujarati detected: canonical='%s', native='%s', intent='%s', conf=%.2f",
                norm_gu.canonical_roman, norm_gu.native_script, norm_gu.semantic_intent, norm_gu.confidence,
            )
            return DetectedLanguage(
                code="gu",
                name="Gujarati",
                confidence=norm_gu.confidence,
                is_romanized=True,
                detected_script="latin",
                normalized_gujarati=norm_gu,
            )

        # 3. Roman Hindi (Hinglish) Analysis
        total_words = len(words)
        eng_matches = sum(1 for w in words if w in _ENGLISH_CONTRASTIVE_WORDS)

        hi_score = 0
        for w in words:
            if w in _HINDI_ROMAN_TOKENS:
                hi_score += _HINDI_ROMAN_TOKENS[w]

        for i in range(len(words) - 1):
            bg = (words[i], words[i + 1])
            if bg in _HINDI_BIGRAMS:
                hi_score += 8

        lower_text = cleaned.lower()
        if "aapka naam" in lower_text or "kya hai" in lower_text or "kaise ho" in lower_text:
            hi_score += 8

        # Contrastive English Filter for Hindi:
        if total_words > 0 and (eng_matches / total_words) >= 0.5:
            if hi_score < 8:
                return DetectedLanguage(code="en", name="English", confidence=0.95, is_romanized=False, detected_script="latin")

        if hi_score >= 3:
            conf = min(0.99, 0.65 + (hi_score * 0.05))
            return DetectedLanguage(code="hi", name="Hindi", confidence=conf, is_romanized=True, detected_script="latin")

        # 4. European Language quick markers
        es_markers = {"hola", "como", "estas", "gracias", "por", "favor", "que", "buenos", "dias"}
        fr_markers = {"bonjour", "salut", "comment", "allez", "vous", "merci", "oui"}
        de_markers = {"hallo", "guten", "morgen", "tag", "danke", "bitte", "wie", "geht"}

        w_set = set(words)
        if len(w_set & es_markers) >= 2:
            return DetectedLanguage(code="es", name="Spanish", confidence=0.90, is_romanized=False, detected_script="latin")
        if len(w_set & fr_markers) >= 2:
            return DetectedLanguage(code="fr", name="French", confidence=0.90, is_romanized=False, detected_script="latin")
        if len(w_set & de_markers) >= 2:
            return DetectedLanguage(code="de", name="German", confidence=0.90, is_romanized=False, detected_script="latin")

        return DetectedLanguage(code="en", name="English", confidence=0.95, is_romanized=False, detected_script="latin")

    # ─── System Prompt Instruction Generation ──────────────────────────

    @classmethod
    def build_persistent_multilingual_directives(
        cls,
        response_language: str = "en",
        response_format: str = "native",
        target_lang_code: Optional[str] = None,
        target_format: Optional[str] = None,
    ) -> str:
        """Construct conversation-level persistent multilingual instructions enforcing strict selected language rules."""
        raw_lang = (target_lang_code or response_language or "en").lower().strip()
        is_auto = (raw_lang == "auto")
        target_lang_code = "auto" if is_auto else (raw_lang if raw_lang in SUPPORTED_LANGUAGES else "en")
        raw_fmt = (target_format or response_format or "native").lower().strip()
        is_romanized = (raw_fmt == "romanized")

        target_meta = SUPPORTED_LANGUAGES.get(target_lang_code, SUPPORTED_LANGUAGES.get("en", {}))
        target_name = target_meta.get("name", "ENGLISH").upper() if not is_auto else "AUTO"

        lines: List[str] = [
            "[STRICT RESPONSE LANGUAGE DIRECTIVES - BOND]:",
            "[Multilingual Understanding & Language Directives]",
            "You are Bond, a friendly, intelligent AI companion with strict multilingual response control.",
        ]

        if is_auto:
            lines.extend([
                "1. STRICT SELECTED RESPONSE LANGUAGE RULE (AUTO-DETECT):",
                "   - Selected Response Language: Auto-detect.",
                "   - The selected response language in Settings is the absolute priority over the user's input language.",
                "   - NEVER automatically change or switch your response language based on the user's latest message.",
                "   - Detect the language in which the user communicates and respond in that language.",
                "   - If the user communicates in Gujarati, respond in Gujarati (e.g. 'Kem cho?' -> 'હું મજામાં છું! તમે કેમ છો?').",
                "   - If the user communicates in English, respond in English (e.g. 'Hello, how are you?' -> 'I\\'m doing great! How are you?').",
                "   - If the user communicates in Hindi, respond in Hindi (e.g. 'आप कैसे हो?' -> 'मैं अच्छा हूँ! आप कैसे हैं?').",
            ])
        else:
            lines.extend([
                f"1. STRICT SELECTED RESPONSE LANGUAGE RULE ({target_name} ONLY):",
                f"   - Selected Response Language: {target_name}.",
                f"   - ABSOLUTE RULE: You MUST formulate and generate ALL your responses in {target_name}.",
                f"   - The selected response language in Settings is the absolute priority over the user's input language.",
                f"   - NEVER automatically change or switch your response language based on the user's latest message.",
                f"   - If English is selected: Even if the user asks in Gujarati (e.g. 'Kem cho?', 'Tamaru naam su che?') or Hindi (e.g. 'Aap kaise hain?'), your response MUST BE IN ENGLISH (e.g. 'I am doing great! How are you?').",
                f"   - If Gujarati is selected: Even if the user asks in English (e.g. 'Hello, how are you?', 'What is your name?') or Hindi, your response MUST BE IN GUJARATI (e.g. 'હું મજામાં છું! તમે કેમ છો?').",
                f"   - If Hindi is selected: Even if the user asks in Gujarati (e.g. 'Kem cho?') or English, your response MUST BE IN HINDI (e.g. 'मैं अच्छा हूँ! आप कैसे हैं?').",
                f"   - Consistency: Do NOT randomly mix English, Gujarati, and Hindi. Keep your response strictly in {target_name}.",
            ])

        lines.extend([
            "",
            "2. AI Response Text Format (Script Style):",
        ])

        if target_lang_code == "gu" or (is_auto and target_lang_code == "auto"):
            if is_romanized:
                lines.extend([
                    "   - Setting: ROMANIZED LATIN LETTERS (English alphabet).",
                    "   - You MUST write your response in GUJARATI using the Latin alphabet (Gujlish).",
                    "   - Write authentic, natural conversational Gujarati words phonetically in Latin letters (e.g. 'Maru naam Bond che! Tamne maline aanand thayo.', 'Hu majama chu, tame kem cho?').",
                    "   - CRITICAL CONSTRAINT: DO NOT translate into English words (do NOT say 'My name is Bond', say 'Maru naam Bond che!').",
                    "   - DO NOT use Gujarati script characters (do not output 'મારું નામ બોન્ડ છે'). Use Latin letters only.",
                ])
            else:
                lines.extend([
                    "   - Setting: NATIVE GUJARATI SCRIPT (ગુજરાતી લિપિ).",
                    "   - You MUST write your response in authentic GUJARATI NATIVE SCRIPT (ગુજરાતી લિપિ, e.g. 'મારું નામ બોન્ડ છે! તમને મળીને આનંદ થયો.').",
                    "   - DO NOT output Devanagari (Hindi) script when replying in Gujarati.",
                    "   - DO NOT output English text when Gujarati is selected.",
                ])
        elif target_lang_code == "hi":
            if is_romanized:
                lines.extend([
                    "   - Setting: ROMANIZED LATIN LETTERS (English alphabet).",
                    "   - You MUST write your response in HINDI using the Latin alphabet (Hinglish).",
                    "   - Write authentic, natural conversational Hindi words phonetically in Latin letters (e.g. 'Mera naam Bond hai! Main achha hoon, aap kaise hain?').",
                    "   - CRITICAL CONSTRAINT: DO NOT translate into English words. Use Latin letters only.",
                ])
            else:
                lines.extend([
                    "   - Setting: Native Script (देवनागरी लिपि).",
                    "   - You MUST write your response in authentic HINDI NATIVE DEVANAGARI SCRIPT (देवनागरी लिपि, e.g. 'मेरा नाम बॉन्ड है! आप कैसे हैं?').",
                    "   - DO NOT output Gujarati script when replying in Hindi.",
                ])
        else:  # English
            lines.extend([
                "   - Setting: English (Latin Script).",
                "   - You MUST write your entire response in clear, friendly, natural English.",
                "   - Understand Gujarati and Hindi inputs completely, but formulate your answer 100% in English.",
            ])

        lines.extend([
            "",
            "3. Deep Gujarati Romanization Comprehension:",
            "   - Understand Gujarati written using English letters (e.g., 'Kem cho?', 'Tamaru naam su che?', 'Tame shu karo cho?', 'Mane Gujarati ma jawab aapo', 'Hu maja ma chu', 'Tame kya raho cho?').",
            "   - Understand these as authentic Gujarati input, not ordinary English.",
            "   - DO NOT interpret Gujarati transliteration as Hindi merely because the languages share vocabulary (e.g., 'naam', 'dost') or roots.",
            "   - Distinctive Gujarati markers ('che', 'cho', 'chu', 'thayo', 'karo', 'raho', 'su' / 'shu', 'kya', 'kem', 'tamaru', 'tamne', 'maru', 'mane', 'hu', 'tame', 'nathi', 'aapo') are strictly GUJARATI.",
            "   - DO NOT misinterpret this as Hindi.",
            "   - However, your RESPONSE language must still follow the selected Settings preference above.",
            "",
            "4. Conversational Fluency & Context Preservation:",
            "   - Maintain natural conversational language rather than producing literal machine translations.",
            "   - Preserve full conversation context and memories across language switches.",
            "   - Do NOT randomly mix English, Gujarati, and Hindi.",
            "   - Remember the configured response language consistently throughout the conversation.",
        ])

        return "\n".join(lines)

    @classmethod
    def build_turn_ground_truth(
        cls,
        user_input: Optional[str] = None,
        response_language: str = "auto",
        response_format: str = "native",
        user_message: Optional[str] = None,
        configured_resp_lang: Optional[str] = None,
        configured_resp_format: Optional[str] = None,
    ) -> Optional[str]:
        """Construct turn-level linguistic ground truth and explicit output language commands."""
        actual_input = user_message if user_message is not None else (user_input or "")
        cleaned = actual_input.strip()
        if not cleaned:
            return None

        raw_lang = (configured_resp_lang or response_language or "auto").lower().strip()
        is_auto = (raw_lang == "auto")
        target_lang_code = "auto" if is_auto else (raw_lang if raw_lang in SUPPORTED_LANGUAGES else "en")
        fmt = (configured_resp_format or response_format or "native").lower().strip()
        is_romanized_requested = (fmt == "romanized")

        detected = cls.detect_language(cleaned)

        # Optimization (Phase 5): Standard English input in auto mode does not require turn-level override
        if is_auto and detected.code == "en" and not detected.is_romanized:
            return None

        turn_lines: List[str] = [
            "[Turn Linguistic Ground Truth]:",
        ]

        if is_auto:
            turn_lines.append("- RESPONSE MODE: Auto-detect (Mirror user input language)")
        else:
            target_meta = SUPPORTED_LANGUAGES.get(target_lang_code, {})
            t_name = target_meta.get("name", "English").upper()
            turn_lines.append(f"- MANDATORY RESPONSE LANGUAGE: {t_name} (Selected in Settings — DO NOT CHANGE)")

        # Case 1: Romanized Gujarati input (Gujlish)
        if detected.code == "gu" and detected.is_romanized:
            norm = detected.normalized_gujarati
            norm_native = norm.native_script if norm else "તમારું નામ શું છે?"
            norm_gloss = norm.english_gloss if norm else "What is your name?"
            intent = norm.semantic_intent if norm else "conversational"
            turn_lines.extend([
                "- User Input: Romanized Gujarati (Gujlish written in Latin letters).",
                f"- User Input Language: Gujarati",
                f"- User Message: \"{cleaned}\"",
                f"- Normalized Gujarati Script: \"{norm_native}\"",
                f"- Meaning / English Gloss: \"{norm_gloss}\" (Intent: {intent})",
                "- Linguistic Comprehension: Accurately understand this message as GUJARATI.",
                "- DO NOT misinterpret this as Hindi or ordinary English.",
            ])

            if is_auto or target_lang_code == "gu":
                if is_romanized_requested:
                    turn_lines.extend([
                        "- MANDATORY OUTPUT: Respond in authentic GUJARATI using ROMANIZED LATIN LETTERS (Gujlish).",
                        "  * Write natural Gujarati words using the English alphabet (e.g., 'Hu Bond chu. Tamne maline aanand thayo!').",
                        "  * DO NOT translate into English. Keep original Gujarati meaning.",
                        "  * DO NOT use Gujarati script characters.",
                    ])
                else:
                    turn_lines.extend([
                        "- MANDATORY OUTPUT: Respond in authentic GUJARATI using NATIVE GUJARATI SCRIPT (ગુજરાતી લિપિ).",
                        f"  * Normalized user input was: '{norm_native}'.",
                        "  * Write your entire reply in authentic NATIVE GUJARATI SCRIPT (e.g., 'હું બોન્ડ છું! તમને મળીને આનંદ થયો.').",
                        "  * DO NOT misinterpret this as Hindi. DO NOT output Hindi/Devanagari script or English.",
                    ])
            elif target_lang_code == "en":
                turn_lines.append(
                    f"- MANDATORY OUTPUT: The user communicated in Gujarati (meaning: '{norm_gloss}'). "
                    f"Because English is selected in Settings, You MUST respond in clear, friendly ENGLISH (e.g. if user said 'Kem cho?', reply 'I\\'m doing great! How are you?'). "
                    f"DO NOT reply in Gujarati or English."
                )
            elif target_lang_code == "hi":
                if is_romanized_requested:
                    turn_lines.append(
                        "- MANDATORY OUTPUT: The user communicated in Gujarati, but Hindi is selected in Settings. "
                        "You MUST respond in HINDI using ROMANIZED LATIN LETTERS (Hinglish). DO NOT reply in Gujarati or English."
                    )
                else:
                    turn_lines.append(
                        "- MANDATORY OUTPUT: The user communicated in Gujarati, but Hindi is selected in Settings. "
                        "You MUST respond in HINDI using NATIVE DEVANAGARI SCRIPT (देवनागरी लिपि). DO NOT reply in Gujarati or English."
                    )
            else:
                target_meta = SUPPORTED_LANGUAGES.get(target_lang_code, {})
                t_name = target_meta.get("name", target_lang_code).upper()
                turn_lines.append(f"- MANDATORY OUTPUT: You MUST respond in {t_name}.")
            return "\n".join(turn_lines)

        # Case 2: Native Gujarati input
        elif detected.code == "gu" and not detected.is_romanized:
            turn_lines.extend([
                "- User Input: Native Gujarati Script (ગુજરાતી લિપિ).",
                "- User Input Language: Gujarati",
                f"- User Message: \"{cleaned}\"",
            ])
            if is_auto or target_lang_code == "gu":
                if is_romanized_requested:
                    turn_lines.append("- MANDATORY OUTPUT: Respond in GUJARATI using ROMANIZED LATIN LETTERS (Gujlish). DO NOT translate into English. DO NOT use Gujarati script characters.")
                else:
                    turn_lines.append("- MANDATORY OUTPUT: Respond in GUJARATI using NATIVE GUJARATI SCRIPT (ગુજરાતી લિપિ).")
            elif target_lang_code == "en":
                turn_lines.append(
                    "- MANDATORY OUTPUT: The user communicated in Gujarati. "
                    "Because English is selected in Settings, You MUST respond in clear, friendly ENGLISH. "
                    "DO NOT reply in Gujarati or English."
                )
            elif target_lang_code == "hi":
                if is_romanized_requested:
                    turn_lines.append("- MANDATORY OUTPUT: Respond in HINDI using ROMANIZED LATIN LETTERS (Hinglish). DO NOT reply in Gujarati or English.")
                else:
                    turn_lines.append("- MANDATORY OUTPUT: Respond in HINDI using NATIVE DEVANAGARI SCRIPT (देवनागरी लिपि). DO NOT reply in Gujarati or English.")
            return "\n".join(turn_lines)

        # Case 3: English input
        elif detected.code == "en":
            turn_lines.extend([
                f"- User Input Language: English",
                f"- User Message: \"{cleaned}\"",
            ])
            if is_auto or target_lang_code == "en":
                turn_lines.append("- MANDATORY OUTPUT: Respond in clear, friendly, natural ENGLISH.")
            elif target_lang_code == "gu":
                if is_romanized_requested:
                    turn_lines.append(
                        f"- MANDATORY OUTPUT: User Input Language: English, but Gujarati is selected in Settings. "
                        f"You MUST respond in GUJARATI using ROMANIZED LATIN LETTERS (Gujlish). DO NOT respond in English."
                    )
                else:
                    turn_lines.append(
                        f"- MANDATORY OUTPUT: User Input Language: English, but Gujarati is selected in Settings. "
                        f"You MUST respond in GUJARATI using NATIVE GUJARATI SCRIPT (ગુજરાતી લિપિ). DO NOT respond in English."
                    )
            elif target_lang_code == "hi":
                if is_romanized_requested:
                    turn_lines.append(
                        f"- MANDATORY OUTPUT: User Input Language: English, but Hindi is selected in Settings. "
                        f"You MUST respond in HINDI using ROMANIZED LATIN LETTERS (Hinglish). DO NOT respond in English."
                    )
                else:
                    turn_lines.append(
                        f"- MANDATORY OUTPUT: User Input Language: English, but Hindi is selected in Settings. "
                        f"You MUST respond in HINDI using NATIVE DEVANAGARI SCRIPT (देवनागरी लिपि). DO NOT respond in English."
                    )
            else:
                target_meta = SUPPORTED_LANGUAGES.get(target_lang_code, {})
                t_name = target_meta.get("name", target_lang_code).upper()
                turn_lines.append(f"- MANDATORY OUTPUT: You MUST respond in {t_name}.")
            return "\n".join(turn_lines)

        # Case 4: Hindi input (Native or Romanized)
        elif detected.code == "hi":
            script_desc = "Romanized Latin (Hinglish)" if detected.is_romanized else "Native Devanagari script"
            turn_lines.extend([
                f"- User Input: Hindi ({script_desc}).",
                f"- User Input Language: Hindi",
                f"- User Message: \"{cleaned}\"",
            ])
            if is_auto or target_lang_code == "hi":
                if is_romanized_requested:
                    turn_lines.append("- MANDATORY OUTPUT: Respond in HINDI using ROMANIZED LATIN LETTERS (Hinglish).")
                else:
                    turn_lines.append("- MANDATORY OUTPUT: Respond in HINDI using NATIVE DEVANAGARI SCRIPT (देवनागरी लिपि).")
            elif target_lang_code == "en":
                turn_lines.append(
                    "- MANDATORY OUTPUT: The user communicated in Hindi. "
                    "Because English is selected in Settings, You MUST respond in clear, friendly ENGLISH. "
                    "DO NOT reply in Hindi."
                )
            elif target_lang_code == "gu":
                if is_romanized_requested:
                    turn_lines.append("- MANDATORY OUTPUT: Respond in GUJARATI using ROMANIZED LATIN LETTERS (Gujlish). DO NOT reply in Hindi.")
                else:
                    turn_lines.append("- MANDATORY OUTPUT: Respond in GUJARATI using NATIVE GUJARATI SCRIPT (ગુજરાતી લિપિ). DO NOT reply in Hindi.")
            return "\n".join(turn_lines)

        # Fallback for any other input
        return "\n".join(turn_lines)

    @classmethod
    def build_multilingual_prompt_instruction(
        cls,
        user_input: str = "",
        response_language: str = "auto",
        response_format: str = "native",
    ) -> str:
        """Construct complete authoritative language directives and ground truth for system prompt.
        
        Args:
            user_input: The user's prompt text (optional for conversation-level persistent prompts).
            response_language: Configured target language ('auto', 'en', 'gu', 'hi', etc.). Default: 'auto'.
            response_format: Configured script style ('native' or 'romanized').
            
        Returns:
            Authoritative prompt block injecting persistent multilingual foundation and turn-level ground truth.
        """
        persistent = cls.build_persistent_multilingual_directives(
            response_language=response_language,
            response_format=response_format,
        )
        turn_truth = cls.build_turn_ground_truth(
            user_input=user_input,
            response_language=response_language,
            response_format=response_format,
        )
        if turn_truth:
            return f"{persistent}\n\n{turn_truth}"
        return persistent

    # ─── Script Transliteration & Format Enforcement ───────────────────

    @classmethod
    def format_response_script(cls, text: str, target_language: str, target_format: str) -> str:
        """Ensure the emitted response strictly matches the user's requested script format and language.
        
        If the user requested 'romanized' but the LLM outputted native Gujarati or Devanagari script,
        this converts native Unicode characters to Romanized Latin script.
        If the user requested 'native' but the LLM outputted Romanized Gujarati/Hindi,
        this converts to native script characters.
        If English was selected but native script leaked, converts to English greeting/text.
        """
        if not text or not text.strip():
            return text

        lang = (target_language or "en").lower().strip()
        fmt = (target_format or "native").lower().strip()

        has_gujarati = any(0x0A80 <= ord(c) <= 0x0AFF for c in text)
        has_devanagari = any(0x0900 <= ord(c) <= 0x097F for c in text)

        if lang == "en":
            # Strict safety net: English selected should not leak Gujarati/Hindi script
            if has_gujarati:
                COMMON_GU_TO_EN = {
                    "હું મજામાં છું! તમે કેમ છો?": "I'm doing great! How are you?",
                    "હું મજામાં છું, તમે કેમ છો?": "I'm doing great! How are you?",
                    "હું મજામાં છું": "I'm doing great!",
                    "મારું નામ બોન્ડ છે! તમને મળીને આનંદ થયો.": "My name is Bond! Pleased to meet you.",
                    "મારું નામ બોન્ડ છે!": "My name is Bond!",
                    "મારું નામ બોન્ડ છે": "My name is Bond.",
                    "તમને મળીને આનંદ થયો": "Pleased to meet you!",
                    "કેમ છો?": "How are you?",
                    "શું ચાલે છે?": "What's up?",
                }
                for gu_phrase, en_trans in COMMON_GU_TO_EN.items():
                    if gu_phrase in text:
                        text = text.replace(gu_phrase, en_trans)
                if any(0x0A80 <= ord(c) <= 0x0AFF for c in text):
                    text = cls.transliterate_gujarati_to_latin(text)
            elif has_devanagari:
                COMMON_HI_TO_EN = {
                    "मैं अच्छा हूँ! आप कैसे हैं?": "I'm doing great! How are you?",
                    "मैं अच्छा हूँ": "I'm doing great!",
                    "मेरा नाम बॉन्ड है! आपसे मिलकर खुशी हुई।": "My name is Bond! Pleased to meet you.",
                    "मेरा नाम बॉन्ड है!": "My name is Bond!",
                    "मेरा नाम बॉन्ड है": "My name is Bond.",
                    "आप कैसे हैं?": "How are you?",
                }
                for hi_phrase, en_trans in COMMON_HI_TO_EN.items():
                    if hi_phrase in text:
                        text = text.replace(hi_phrase, en_trans)
                if any(0x0900 <= ord(c) <= 0x097F for c in text):
                    text = cls.transliterate_devanagari_to_latin(text)
            return text

        elif lang == "gu":
            if fmt == "romanized":
                if has_gujarati:
                    return cls.transliterate_gujarati_to_latin(text)
                elif has_devanagari:
                    return cls.transliterate_devanagari_to_latin(text)
            elif fmt == "native":
                if not has_gujarati and not has_devanagari:
                    return RomanGujaratiNormalizer.transliterate_to_native_script(text)
                elif has_devanagari:
                    rom = cls.transliterate_devanagari_to_latin(text)
                    return RomanGujaratiNormalizer.transliterate_to_native_script(rom)

        elif lang == "hi":
            if fmt == "romanized":
                if has_devanagari:
                    return cls.transliterate_devanagari_to_latin(text)
                elif has_gujarati:
                    return cls.transliterate_gujarati_to_latin(text)
            elif fmt == "native":
                if has_gujarati:
                    rom = cls.transliterate_gujarati_to_latin(text)
                    return cls.transliterate_latin_to_devanagari(rom)
                elif not has_devanagari:
                    return cls.transliterate_latin_to_devanagari(text)

        return text

    @classmethod
    def generate_language_preview(cls, target_language: str = "gu", target_format: str = "native") -> Dict[str, str]:
        """Generate live test preview text using the application's actual formatting and transliteration pipeline.
        
        Requirements (Phase 8):
        - Selected language: Gujarati
        - Selected format: Native Script -> "નમસ્તે! હું બોન્ડ છું. આજે તમે કેમ છો?"
        - When Romanized / Latin Script is selected -> "Namaste! Hu Bond chu. Aaje tame kem cho?"
        - Dynamically generated using format_response_script rather than hardcoded string.
        """
        lang = (target_language or "auto").lower().strip()
        fmt = (target_format or "native").lower().strip()

        SAMPLE_TEXTS = {
            "gu": "નમસ્તે! હું બોન્ડ છું. આજે તમે કેમ છો?",
            "hi": "नमस्ते! मैं बॉन्ड हूँ। आज आप कैसे हैं?",
            "mr": "नमस्कार! मी बाँड आहे. आज तुम्ही कसे आहात?",
            "bn": "নমস্কার! আমি বন্ড। আজ আপনি কেমন আছেন?",
            "ta": "வணக்கம்! நான் பாண்ட். இன்று நீங்கள் எப்படி இருக்கிறீர்கள்?",
            "te": "నమస్కారం! నేను బాండ్. ఈరోజు మీరు ఎలా ఉన్నారు?",
            "pa": "ਸਤਿ ਸ੍ਰੀ ਅਕਾਲ! ਮੈਂ ਬਾਂਡ ਹਾਂ। ਅੱਜ ਤੁਸੀਂ ਕਿਵੇਂ ਹੋ?",
            "es": "¡Hola! Soy Bond. ¿Cómo estás hoy?",
            "fr": "Bonjour! Je suis Bond. Comment allez-vous aujourd'hui?",
            "de": "Hallo! Ich bin Bond. Wie geht es dir heute?",
            "ja": "こんにちは！ボンドです。今日はお元気ですか？",
            "zh": "你好！我是邦德。你今天好吗？",
            "en": "Hello! I am Bond. How are you today?",
        }

        if lang == "auto":
            gu_native = SAMPLE_TEXTS["gu"]
            preview_text = cls.format_response_script(gu_native, "gu", fmt)
            user_sample = "Tamaru naam su che? / Kem cho?"
            desc = "Auto-detect dynamically mirrors your input language (shown using current format)."
        else:
            base_text = SAMPLE_TEXTS.get(lang, SAMPLE_TEXTS["en"])
            preview_text = cls.format_response_script(base_text, lang, fmt)
            user_sample = (
                "Tamaru naam su che?" if lang == "gu"
                else ("Aapka naam kya hai?" if lang == "hi"
                else "What is your name?")
            )
            desc = f"Configured response language: {SUPPORTED_LANGUAGES.get(lang, {}).get('name', lang)}."

        return {
            "language": lang,
            "format": fmt,
            "user_sample": user_sample,
            "preview_text": preview_text,
            "description": desc,
        }

    @staticmethod
    def transliterate_latin_to_devanagari(text: str) -> str:
        """Transliterate Romanized Hindi (Hinglish) to native Devanagari script."""
        COMMON_ROMAN_TO_HI_WORDS = {
            "mera": "मेरा", "meri": "मेरी", "mere": "मेरे",
            "naam": "नाम", "name": "नाम", "bond": "बॉन्ड",
            "hai": "है", "hain": "हैं", "hoon": "हूँ", "hun": "हूँ",
            "aap": "आप", "kaise": "कैसे", "kaisi": "कैसी", "ho": "हो",
            "main": "मैं", "achha": "अच्छा", "achhi": "अच्छी", "theek": "ठीक",
            "namaste": "नमस्ते", "shukriya": "शुक्रिया", "dhanyavaad": "धन्यवाद",
            "kya": "क्या", "kar": "कर", "rahe": "रहे", "raha": "रहा", "rahi": "रही",
            "batao": "बताओ", "bataiye": "बताइए", "kripya": "कृपया",
            "dost": "दोस्त", "haan": "हाँ", "ha": "हाँ", "nahi": "नहीं", "nahin": "नहीं",
            "bahut": "बहुत", "khushi": "खुशी", "hui": "हुई", "milkar": "मिलकर",
        }
        words = text.split(" ")
        res = []
        for w in words:
            m = re.match(r"^([a-zA-Z]+)([^a-zA-Z]*)$", w)
            if m:
                core, punct = m.group(1).lower(), m.group(2)
                if core in COMMON_ROMAN_TO_HI_WORDS:
                    res.append(COMMON_ROMAN_TO_HI_WORDS[core] + punct)
                else:
                    res.append(w)
            else:
                res.append(w)
        return " ".join(res)

    @staticmethod
    def transliterate_gujarati_to_latin(text: str) -> str:
        """Deterministic transliterator converting Gujarati script to Romanized Latin (Gujlish)."""
        GU_VOWELS = {
            'અ': 'a', 'આ': 'aa', 'ઇ': 'i', 'ઈ': 'ee', 'ઉ': 'u', 'ઊ': 'oo',
            'ઋ': 'ru', 'એ': 'e', 'ઐ': 'ai', 'ઓ': 'o', 'ઔ': 'au', 'અં': 'an', 'અઃ': 'ah',
        }
        GU_MATRAS = {
            'ા': 'aa', 'િ': 'i', 'ી': 'ee', 'ુ': 'u', 'ૂ': 'oo', 'ૃ': 'ru',
            'ે': 'e', 'ૈ': 'ai', 'ો': 'o', 'ૌ': 'au', 'ં': 'n', 'ઃ': 'h', '્': '',
        }
        GU_CONSONANTS = {
            'ક': 'k', 'ખ': 'kh', 'ગ': 'g', 'ઘ': 'gh', 'ઙ': 'ng',
            'ચ': 'ch', 'છ': 'chh', 'જ': 'j', 'ઝ': 'zh', 'ઞ': 'ny',
            'ટ': 't', 'ઠ': 'th', 'ડ': 'd', 'ઢ': 'dh', 'ણ': 'n',
            'ત': 't', 'થ': 'th', 'દ': 'd', 'ધ': 'dh', 'ન': 'n',
            'પ': 'p', 'ફ': 'f', 'બ': 'b', 'ભ': 'bh', 'મ': 'm',
            'ય': 'y', 'ર': 'r', 'લ': 'l', 'ળ': 'l', 'વ': 'v',
            'શ': 'sh', 'ષ': 'sh', 'સ': 's', 'હ': 'h',
            # Digits
            '૦': '0', '૧': '1', '૨': '2', '૩': '3', '૪': '4',
            '૫': '5', '૬': '6', '૭': '7', '૮': '8', '૯': '9',
            '।': '.',
        }

        # Common word overrides for authentic, natural Gujlish spelling
        COMMON_GU_OVERRIDES = {
            "હું": "Hu", "બોન્ડ": "Bond", "છું": "chu", "છે": "che", "છો": "cho", "છે!": "che!",
            "તમારું": "Tamaru", "તારું": "Taru", "મારું": "Maru", "મારો": "Maro", "મારી": "Mari",
            "નામ": "naam", "શું": "su", "શું?": "su?",
            "કેમ": "Kem", "તમને": "tamne", "તમે": "Tame", "મને": "mane", "તને": "tane",
            "મળીને": "maline", "આનંદ": "aanand", "થયો": "thayo", "થયો!": "thayo!",
            "આભાર": "Aabhar", "નથી": "nathi", "સારું": "saru", "બધું": "badhu",
            "મજામાં": "majama", "હા": "Ha", "ના": "Na", "દોસ્ત": "dost",
            "ક્યાં": "kya", "રહો": "raho", "કરો": "karo", "જવાબ": "jawab", "આપો": "aapo",
            "ગુજરાતીમાં": "Gujarati ma", "ગુજરાતી": "Gujarati", "બોલો": "bolo", "કહો": "kaho",
            "દિવસ": "divas", "આજે": "aaje", "કાલે": "kaale", "પછી": "pachhi", "મળીએ": "maliye",
            "મદદ": "madad", "કોણ": "kon", "ચાલે": "chale", "સ્વાગત": "swagat", "ખૂબ": "Khub",
        }

        # Apply whole-word replacements first
        result_words = []
        for word in text.split(" "):
            # Strip trailing punctuation for dictionary match
            m = re.match(r"^([\w\u0A80-\u0AFF]+)([^\w\u0A80-\u0AFF]*)$", word)
            if m:
                core, punct = m.group(1), m.group(2)
                if core in COMMON_GU_OVERRIDES:
                    result_words.append(COMMON_GU_OVERRIDES[core] + punct)
                    continue

            # Character-by-character transliteration
            out = []
            chars = list(word)
            n = len(chars)
            i = 0
            while i < n:
                c = chars[i]
                if c in GU_VOWELS:
                    out.append(GU_VOWELS[c])
                elif c in GU_CONSONANTS:
                    base = GU_CONSONANTS[c]
                    # Check next char for matra or halant (virama)
                    if i + 1 < n and chars[i + 1] in GU_MATRAS:
                        matra = GU_MATRAS[chars[i + 1]]
                        out.append(base + matra)
                        i += 1  # Skip matra
                    elif i + 1 < n and chars[i + 1] == '્':
                        out.append(base)  # Halant: no inherent vowel
                        i += 1
                    else:
                        # Inherent 'a' vowel unless at end of word or before punctuation
                        if i == n - 1 or not chars[i + 1].isalpha():
                            out.append(base)
                        else:
                            out.append(base + 'a')
                elif c in GU_MATRAS:
                    out.append(GU_MATRAS[c])
                else:
                    out.append(c)
                i += 1
            result_words.append("".join(out))

        joined = " ".join(result_words)
        # Sentence casing after terminal punctuation
        joined = re.sub(r'([.!?]\s+)([a-z])', lambda m: m.group(1) + m.group(2).upper(), joined)
        if joined and joined[0].islower():
            joined = joined[0].upper() + joined[1:]
        return joined

    @staticmethod
    def transliterate_devanagari_to_latin(text: str) -> str:
        """Deterministic transliterator converting Devanagari script to Romanized Latin (Hinglish)."""
        HI_VOWELS = {
            'अ': 'a', 'आ': 'aa', 'इ': 'i', 'ई': 'ee', 'उ': 'u', 'ऊ': 'oo',
            'ऋ': 'ri', 'ए': 'e', 'ऐ': 'ai', 'ओ': 'o', 'औ': 'au', 'अं': 'an', 'अः': 'ah',
        }
        HI_MATRAS = {
            'ा': 'aa', 'ि': 'i', 'ी': 'ee', 'ु': 'u', 'ू': 'oo', 'ृ': 'ri',
            'े': 'e', 'ै': 'ai', 'ो': 'o', 'ौ': 'au', 'ं': 'n', 'ः': 'h', '्': '',
        }
        HI_CONSONANTS = {
            'क': 'k', 'ख': 'kh', 'ग': 'g', 'घ': 'gh', 'ङ': 'ng',
            'च': 'ch', 'छ': 'chh', 'ज': 'j', 'झ': 'zh', 'ञ': 'ny',
            'ट': 't', 'ठ': 'th', 'ड': 'd', 'ढ': 'dh', 'ण': 'n',
            'त': 't', 'थ': 'th', 'द': 'd', 'ध': 'dh', 'न': 'n',
            'प': 'p', 'फ': 'f', 'ब': 'b', 'भ': 'bh', 'म': 'm',
            'य': 'y', 'र': 'r', 'ल': 'l', 'व': 'v',
            'श': 'sh', 'ष': 'sh', 'स': 's', 'ह': 'h',
            # Digits
            '०': '0', '१': '1', '२': '2', '३': '3', '४': '4',
            '૫': '5', '६': '6', '७': '7', '८': '8', '९': '9',
            '।': '.',
        }

        COMMON_HI_OVERRIDES = {
            "मेरा": "Mera", "नाम": "naam", "बॉन्ड": "Bond", "है": "hai", "हैं": "hain",
            "आप": "Aap", "कैसे": "kaise", "हो": "ho", "नमस्ते": "Namaste", "शुक्रिया": "Shukriya",
            "अच्छा": "Achha", "बहुत": "bahut", "दोस्त": "dost", "हाँ": "Haan", "नहीं": "nahi",
        }

        result_words = []
        for word in text.split(" "):
            m = re.match(r"^([\w\u0900-\u097F]+)([^\w\u0900-\u097F]*)$", word)
            if m:
                core, punct = m.group(1), m.group(2)
                if core in COMMON_HI_OVERRIDES:
                    result_words.append(COMMON_HI_OVERRIDES[core] + punct)
                    continue

            out = []
            chars = list(word)
            n = len(chars)
            i = 0
            while i < n:
                c = chars[i]
                if c in HI_VOWELS:
                    out.append(HI_VOWELS[c])
                elif c in HI_CONSONANTS:
                    base = HI_CONSONANTS[c]
                    if i + 1 < n and chars[i + 1] in HI_MATRAS:
                        matra = HI_MATRAS[chars[i + 1]]
                        out.append(base + matra)
                        i += 1
                    elif i + 1 < n and chars[i + 1] == '्':
                        out.append(base)
                        i += 1
                    else:
                        if i == n - 1 or not chars[i + 1].isalpha():
                            out.append(base)
                        else:
                            out.append(base + 'a')
                elif c in HI_MATRAS:
                    out.append(HI_MATRAS[c])
                else:
                    out.append(c)
                i += 1
            result_words.append("".join(out))

        return " ".join(result_words)

    # ─── TTS Compatibility & Limitations Validation ────────────────────

    @classmethod
    def prepare_text_for_tts(
        cls,
        text: str,
        target_language: str = "auto",
        engine_name: str = "",
        installed_voices: Optional[List[str]] = None,
        preferred_voice_id: Optional[str] = None,
        preferred_gender: Optional[str] = None,
    ) -> Tuple[str, Optional[str]]:
        """Prepare sentence text for TTS synthesis.
        
        If the active TTS engine/voice cannot natively pronounce raw Indic scripts
        (Gujarati or Devanagari), this converts the text into phonetic Romanized script
        (Gujlish / Hinglish) so the engine speaks the authentic words aloud without producing
        silence or corrupted audio.
        
        Returns:
            Tuple of (spoken_text, voice_hint)
        """
        if not text or not text.strip():
            return "", None

        eng = (engine_name or "").lower().strip()
        has_gujarati = any(0x0A80 <= ord(c) <= 0x0AFF for c in text)
        has_devanagari = any(0x0900 <= ord(c) <= 0x097F for c in text)

        # Check for Indian English voice on Windows (Ravi for Male, Heera for Female)
        gender_low = (preferred_gender or "").lower()
        indian_voice_hint = None
        if installed_voices:
            if gender_low == "male":
                for v in installed_voices:
                    if "ravi" in v.lower():
                        indian_voice_hint = v
                        break
                if not indian_voice_hint:
                    for v in installed_voices:
                        if "heera" in v.lower():
                            indian_voice_hint = v
                            break
            else:
                for v in installed_voices:
                    if "heera" in v.lower():
                        indian_voice_hint = v
                        break
                if not indian_voice_hint:
                    for v in installed_voices:
                        if "ravi" in v.lower():
                            indian_voice_hint = v
                            break

        # Check for native language voices
        native_gu_voice = None
        native_hi_voice = None
        if installed_voices:
            for v in installed_voices:
                v_low = v.lower()
                if "gujarat" in v_low or "dhwani" in v_low or "niranjan" in v_low:
                    native_gu_voice = v
                if "hindi" in v_low or "kalpana" in v_low:
                    native_hi_voice = v

        if has_gujarati:
            if native_gu_voice and ("sapi" in eng or "piper" in eng):
                return text, native_gu_voice
            # Transliterate to phonetic Romanized Gujarati for the speech synthesizer
            spoken = cls.transliterate_gujarati_to_latin(text)
            hint = (indian_voice_hint if "sapi" in eng else preferred_voice_id)
            return spoken, hint

        if has_devanagari:
            if native_hi_voice and ("sapi" in eng or "piper" in eng):
                return text, native_hi_voice
            spoken = cls.transliterate_devanagari_to_latin(text)
            hint = (indian_voice_hint if "sapi" in eng else preferred_voice_id)
            return spoken, hint

        # Latin alphabet text (already Romanized)
        det = cls.detect_language(text)
        if det.code in ("gu", "hi") and "sapi" in eng and indian_voice_hint:
            return text, indian_voice_hint

        return text, preferred_voice_id

    @classmethod
    def check_tts_capability(
        cls,
        engine_name: str,
        target_language: str,
        installed_voices: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Verify whether the active TTS engine supports speech synthesis for the requested language.
        
        Provides transparent limitation warnings so users understand if a voice is missing
        rather than producing corrupted audio.
        """
        eng = (engine_name or "").lower().strip()
        lang = (target_language or "en").lower().strip()
        if lang == "auto":
            lang = "en"  # Default test against English

        lang_meta = SUPPORTED_LANGUAGES.get(lang, {"name": lang.upper()})
        lang_name = lang_meta.get("name", lang.upper())

        # Test & Mock TTS Engines
        if "mock" in eng or "dummy" in eng or "test" in eng:
            return {
                "supported": True,
                "engine_name": engine_name or "MockTTSEngine",
                "target_language": lang,
                "language_name": lang_name,
                "status_badge": "Supported (Mock)",
                "badge_color": "#32D74B",
                "message": f"Mock TTS engine supports {lang_name} for automated testing.",
            }

        # Kokoro Engine: Highly optimized for English; supports Indic via Romanized phonemes
        if "kokoro" in eng:
            if lang == "en":
                return {
                    "supported": True,
                    "engine_name": "Kokoro (82M ONNX)",
                    "target_language": lang,
                    "language_name": lang_name,
                    "status_badge": "Supported",
                    "badge_color": "#32D74B",
                    "message": "Kokoro TTS natively synthesizes natural 24kHz American & British English.",
                }
            elif lang in ("gu", "hi", "mr", "bn", "ta", "te", "pa"):
                return {
                    "supported": True,
                    "engine_name": "Kokoro (82M ONNX)",
                    "target_language": lang,
                    "language_name": lang_name,
                    "status_badge": "Supported (Phonetic Speech)",
                    "badge_color": "#32D74B",
                    "message": f"Kokoro TTS speaks Romanized {lang_name} phonetically with clear pronunciation.",
                }
            else:
                return {
                    "supported": False,
                    "engine_name": "Kokoro (82M ONNX)",
                    "target_language": lang,
                    "language_name": lang_name,
                    "status_badge": "Voice Not Installed",
                    "badge_color": "#FF9F0A",
                    "message": (
                        f"Kokoro TTS currently supports English. A {lang_name} neural model is not installed. "
                        f"To protect audio quality, spoken synthesis will be safely muted for {lang_name}, "
                        f"while chat responses will continue in {lang_name}."
                    ),
                }

        # Piper Engine: ONNX local models per voice
        elif "piper" in eng:
            # Check if an installed voice matches the requested language code
            matching_voice = None
            if installed_voices:
                for v in installed_voices:
                    v_low = v.lower()
                    if f"{lang}_" in v_low or f"{lang}-" in v_low or f"_{lang}" in v_low:
                        matching_voice = v
                        break

            if lang == "en":
                return {
                    "supported": True,
                    "engine_name": "Piper TTS",
                    "target_language": lang,
                    "language_name": lang_name,
                    "status_badge": "Supported",
                    "badge_color": "#32D74B",
                    "message": "Piper TTS has the 'en_US-lessac-medium' neural voice loaded.",
                }
            elif matching_voice:
                return {
                    "supported": True,
                    "engine_name": "Piper TTS",
                    "target_language": lang,
                    "language_name": lang_name,
                    "status_badge": "Supported",
                    "badge_color": "#32D74B",
                    "message": f"Piper TTS has matching {lang_name} voice '{matching_voice}' loaded.",
                }
            elif lang in ("gu", "hi"):
                return {
                    "supported": True,
                    "engine_name": "Piper TTS",
                    "target_language": lang,
                    "language_name": lang_name,
                    "status_badge": "Supported (Phonetic Speech)",
                    "badge_color": "#32D74B",
                    "message": f"Piper TTS speaks Romanized {lang_name} phonetically.",
                }
            else:
                return {
                    "supported": False,
                    "engine_name": "Piper TTS",
                    "target_language": lang,
                    "language_name": lang_name,
                    "status_badge": "Voice Not Installed",
                    "badge_color": "#FF9F0A",
                    "message": (
                        f"Piper TTS currently has an English voice ('en_US-lessac') loaded. "
                        f"No {lang_name} Piper ONNX model was found in assets/piper/. "
                        f"Spoken audio will be paused for {lang_name} to prevent audio corruption."
                    ),
                }

        # SAPI5 Windows System Voices
        elif "sapi" in eng:
            has_native_voice = False
            has_indian_voice = False
            if installed_voices:
                for v in installed_voices:
                    v_low = v.lower()
                    if lang == "gu" and ("gujarat" in v_low or "dhwani" in v_low or "niranjan" in v_low):
                        has_native_voice = True
                    elif lang == "hi" and ("hindi" in v_low or "kalpana" in v_low):
                        has_native_voice = True
                    if "heera" in v_low or "ravi" in v_low:
                        has_indian_voice = True

            if has_native_voice:
                return {
                    "supported": True,
                    "engine_name": "Windows SAPI5",
                    "target_language": lang,
                    "language_name": lang_name,
                    "status_badge": "Supported (Native Voice)",
                    "badge_color": "#32D74B",
                    "message": f"Windows SAPI5 native voice for {lang_name} is available on this system.",
                }
            elif has_indian_voice and lang in ("gu", "hi", "mr", "bn", "ta", "te", "pa"):
                return {
                    "supported": True,
                    "engine_name": "Windows SAPI5",
                    "target_language": lang,
                    "language_name": lang_name,
                    "status_badge": "Supported (Indian Speech Engine)",
                    "badge_color": "#32D74B",
                    "message": f"Windows SAPI5 Indian voice (Heera/Ravi) will synthesize {lang_name} phonetically.",
                }
            elif lang == "en" or lang in ("gu", "hi"):
                return {
                    "supported": True,
                    "engine_name": "Windows SAPI5",
                    "target_language": lang,
                    "language_name": lang_name,
                    "status_badge": "Supported" if (lang == "en") else "Supported (Phonetic Speech)",
                    "badge_color": "#32D74B",
                    "message": f"Windows SAPI5 voice will synthesize {lang_name}.",
                }
            else:
                return {
                    "supported": False,
                    "engine_name": "Windows SAPI5",
                    "target_language": lang,
                    "language_name": lang_name,
                    "status_badge": "Windows Voice Not Installed",
                    "badge_color": "#FF9F0A",
                    "message": (
                        f"Windows does not currently have a {lang_name} speech pack installed. "
                        f"Install the {lang_name} language pack in Windows Settings -> Time & Language -> Speech to enable voice."
                    ),
                }

        # Default fallback
        return {
            "supported": (lang == "en"),
            "engine_name": engine_name or "TTS",
            "target_language": lang,
            "language_name": lang_name,
            "status_badge": "Supported" if (lang == "en") else "Limited",
            "badge_color": "#32D74B" if (lang == "en") else "#FF9F0A",
            "message": f"Active TTS voice capability status for {lang_name}.",
        }
