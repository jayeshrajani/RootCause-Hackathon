"""Deterministic text checks shared by guidance retrieval and the Nemotron guardrails.

Patterns are deliberately conservative: removing a borderline sentence is safer than showing an
unverified chemical instruction or an overconfident claim to a farmer.
"""

import re

ACTIVE_INGREDIENTS = (
    "mancozeb", "chlorothalonil", "copper oxychloride", "copper hydroxide", "copper sulphate",
    "copper sulfate", "bordeaux", "metalaxyl", "mefenoxam", "carbendazim", "benomyl",
    "propiconazole", "tebuconazole", "hexaconazole", "difenoconazole", "azoxystrobin",
    "pyraclostrobin", "trifloxystrobin", "tricyclazole", "isoprothiolane", "validamycin",
    "streptocycline", "streptomycin", "kasugamycin", "cymoxanil", "dimethomorph", "fosetyl",
    "imidacloprid", "thiamethoxam", "acetamiprid", "chlorpyrifos", "cypermethrin",
    "lambda-cyhalothrin", "deltamethrin", "spinosad", "abamectin", "emamectin", "dimethoate",
    "malathion", "profenofos", "fipronil", "carbofuran", "glyphosate", "paraquat", "2,4-d",
    "wettable sulphur", "wettable sulfur", "neem oil", "azadirachtin",
)  # fmt: skip

_INGREDIENT = re.compile(
    r"\b(" + "|".join(re.escape(name) for name in ACTIVE_INGREDIENTS) + r")\b", re.IGNORECASE
)
_PRODUCT_CLASS = re.compile(
    r"\b(fungicide|insecticide|pesticide|bactericide|miticide|acaricide|herbicide|nematicide|"
    r"agrochemical|agro-chemical)s?\b",
    re.IGNORECASE,
)
_APPLY = re.compile(
    r"\b(spray|sprays|spraying|apply|applying|drench|drenching|dust|dusting|treat with)\b",
    re.IGNORECASE,
)
_DOSE = re.compile(
    r"\b\d+(?:[.,]\d+)?\s*(?:%|ppm|ml|g|gm|gms|kg|oz|lbs?|l|litres?|liters?|grams?)\s*"
    r"(?:/|per|a|an|in)\s*(?:\d+\s*)?(?:l|litres?|liters?|ha|hectares?|acres?|plants?|tanks?|"
    r"gallons?|kg|m2|sq)\b",
    re.IGNORECASE,
)
_FORMULATION = re.compile(
    r"\b\d+(?:[.,]\d+)?\s*%\s*(?:wp|ec|sc|wg|wdg|sl|df|sp|gr|cs|od|w/v|w/w)\b", re.IGNORECASE
)
_SCHEDULE = re.compile(
    r"\b(?:every|at)\s+\d+\s*(?:(?:-|to|–)\s*\d+\s*)?days?(?:\s+intervals?)?\b", re.IGNORECASE
)
_BRAND_MARK = re.compile(r"[®™]")

_CERTAINTY = re.compile(
    r"\b(confirm(?:ed|s)?|definitely|certainly|undoubtedly|without (?:a )?doubt|"
    r"100\s?% (?:sure|certain|confident)|guaranteed?|is diagnosed|diagnosis is)\b",
    re.IGNORECASE,
)
_HEDGE_BEFORE = re.compile(
    r"(?:\bnot|\bcannot|\bcan't|n't|\bunable to|\buntil|\bunless|\bto|\bwould|\bcould|\bmay|"
    r"\bmight|\bhelp|\bhelps|\bneeded to|\bneed to|\bun)\s*(?:be\s+)?$",
    re.IGNORECASE,
)
_INSTRUCTION_LIKE = re.compile(
    r"(ignore (?:all |any |the )?(?:previous|prior|above) instructions|system prompt|"
    r"you are (?:an? )?(?:ai|assistant|language model)|disregard (?:the|all) )",
    re.IGNORECASE,
)
_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")
_SITE_CHROME = re.compile(
    r"\b(cookies? (?:are|is) disabled|uses? cookies|accept (?:all )?cookies|"
    r"skip to (?:main )?content|shopping cart|javascript (?:is )?(?:disabled|required)|"
    r"sign in to|log in to)\b",
    re.IGNORECASE,
)
# Breadcrumb items split at their numbers: "Home 2.", "Vegetable farming 5."
_BREADCRUMB = re.compile(r"^[A-Za-z][\w &,'/-]{0,48}\s\d{1,2}\.$")


def is_chemical_instruction(text: str) -> bool:
    """A named active ingredient, a dose, a formulation, a brand mark, or a spray schedule."""
    if _INGREDIENT.search(text) or _DOSE.search(text) or _FORMULATION.search(text):
        return True
    if _BRAND_MARK.search(text):
        return True
    return bool(_APPLY.search(text) and (_PRODUCT_CLASS.search(text) or _SCHEDULE.search(text)))


def mentions_chemical_product(text: str) -> bool:
    """Any pesticide class, ingredient or dose; used for model-written actions and claims."""
    return bool(_PRODUCT_CLASS.search(text)) or is_chemical_instruction(text)


def overstates_certainty(text: str) -> bool:
    for match in _CERTAINTY.finditer(text):
        before = text[max(0, match.start() - 30) : match.start()]
        if not _HEDGE_BEFORE.search(before):
            return True
    return False


def looks_like_instructions(text: str) -> bool:
    return bool(_INSTRUCTION_LIKE.search(text))


def clean_markup(text: str) -> str:
    text = re.sub(r"!\[[^\]]*\]\([^)]*\)", " ", text)
    text = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", text)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"https?://\S+", " ", text)
    text = text.replace("[...]", " … ")
    text = re.sub(r"[#*_`>|]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def safe_excerpt(text: str, limit: int = 600) -> str:
    """Clean page text, drop chemical/dose, instruction-like and site-chrome sentences, trim."""
    kept = [
        sentence
        for sentence in _SENTENCE_SPLIT.split(clean_markup(text))
        if sentence
        and not is_chemical_instruction(sentence)
        and not looks_like_instructions(sentence)
        and not _SITE_CHROME.search(sentence)
        and not _BREADCRUMB.match(sentence)
    ]
    excerpt = ""
    for sentence in kept:
        candidate = f"{excerpt} {sentence}".strip()
        if len(candidate) > limit:
            break
        excerpt = candidate
    if not excerpt and kept:
        excerpt = kept[0][: limit - 1].rstrip() + "…"
    return excerpt


_STOPWORDS = frozenset(
    [
        "this",
        "that",
        "with",
        "from",
        "have",
        "been",
        "were",
        "will",
        "would",
        "could",
        "should",
        "their",
        "there",
        "they",
        "them",
        "these",
        "those",
        "your",
        "into",
        "than",
        "then",
        "when",
        "what",
        "which",
        "while",
        "where",
        "also",
        "more",
        "most",
        "some",
        "such",
        "only",
        "very",
        "about",
        "after",
        "before",
        "other",
        "over",
        "under",
        "plant",
        "plants",
        "crop",
        "crops",
        "leaf",
        "leaves",
        "field",
    ]
)


def content_words(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z]{4,}", text.lower()) if w not in _STOPWORDS}


def supported_by(claim: str, excerpt: str, *, min_shared: int = 2, min_ratio: float = 0.3) -> bool:
    """Lexical check that an excerpt talks about the claim. Necessary, not sufficient."""
    words = content_words(claim)
    if not words:
        return False
    shared = words & content_words(excerpt)
    return len(shared) >= min_shared and len(shared) / len(words) >= min_ratio
