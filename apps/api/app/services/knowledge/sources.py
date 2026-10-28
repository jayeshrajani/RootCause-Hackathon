"""Approved agricultural publishers and crop/condition vocabularies for guidance search.

The allowlist is backend-controlled. A domain matches itself and its subdomains on a dot
boundary only (evil-fao.org does not match fao.org). Inclusion means the organisation is a
recognised research or extension body, not that every page it publishes applies everywhere.
"""

import re
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ApprovedSource:
    domain: str
    publisher: str
    region: str


APPROVED_SOURCES: tuple[ApprovedSource, ...] = (
    # India
    ApprovedSource("icar.org.in", "Indian Council of Agricultural Research (ICAR)", "India"),
    ApprovedSource("icar.gov.in", "ICAR institutes and Krishi Vigyan Kendras", "India"),
    ApprovedSource("iihr.res.in", "ICAR-Indian Institute of Horticultural Research", "India"),
    ApprovedSource("tnau.ac.in", "Tamil Nadu Agricultural University", "India"),
    ApprovedSource("pau.edu", "Punjab Agricultural University", "India"),
    ApprovedSource(
        "ppqs.gov.in", "Directorate of Plant Protection, Quarantine & Storage (GoI)", "India"
    ),
    ApprovedSource(
        "agriwelfare.gov.in", "Ministry of Agriculture & Farmers Welfare (GoI)", "India"
    ),
    # International research and development bodies
    ApprovedSource("fao.org", "Food and Agriculture Organization of the UN (FAO)", "Global"),
    ApprovedSource("cabi.org", "CABI", "Global"),
    ApprovedSource("plantwiseplusknowledgebank.org", "CABI PlantwisePlus Knowledge Bank", "Global"),
    ApprovedSource("irri.org", "International Rice Research Institute (IRRI)", "Global"),
    ApprovedSource("cipotato.org", "International Potato Center (CIP)", "Global"),
    ApprovedSource("cimmyt.org", "International Maize and Wheat Improvement Center", "Global"),
    ApprovedSource("worldveg.org", "World Vegetable Center", "Global"),
    ApprovedSource("apsnet.org", "American Phytopathological Society", "Global"),
    # United States land-grant extension
    ApprovedSource(
        "ucanr.edu", "University of California Agriculture and Natural Resources", "USA"
    ),
    ApprovedSource("vegetables.cornell.edu", "Cornell University Vegetable Program", "USA"),
    ApprovedSource("extension.umn.edu", "University of Minnesota Extension", "USA"),
    ApprovedSource("extension.psu.edu", "Penn State Extension", "USA"),
    ApprovedSource("ifas.ufl.edu", "University of Florida IFAS Extension", "USA"),
    ApprovedSource("ces.ncsu.edu", "NC State Extension", "USA"),
    ApprovedSource("extension.purdue.edu", "Purdue Extension", "USA"),
    ApprovedSource("extension.umd.edu", "University of Maryland Extension", "USA"),
    ApprovedSource("extension.colostate.edu", "Colorado State University Extension", "USA"),
    # Europe, Australia, Africa
    ApprovedSource("ahdb.org.uk", "Agriculture and Horticulture Development Board", "UK"),
    ApprovedSource("teagasc.ie", "Teagasc (Agriculture and Food Development Authority)", "Ireland"),
    ApprovedSource("dpi.nsw.gov.au", "NSW Department of Primary Industries", "Australia"),
    ApprovedSource("agriculture.vic.gov.au", "Agriculture Victoria", "Australia"),
    ApprovedSource(
        "dpird.wa.gov.au",
        "WA Department of Primary Industries and Regional Development",
        "Australia",
    ),
    ApprovedSource("kalro.org", "Kenya Agricultural and Livestock Research Organization", "Kenya"),
)


def approved_sources(domains: list[str] | None = None) -> tuple[ApprovedSource, ...]:
    """The built-in allowlist, optionally narrowed to `domains`. Never widened by config."""
    if not domains:
        return APPROVED_SOURCES
    wanted = {d.strip().lower().lstrip(".") for d in domains}
    return tuple(source for source in APPROVED_SOURCES if source.domain in wanted)


def match_approved(host: str, sources: tuple[ApprovedSource, ...]) -> ApprovedSource | None:
    host = host.lower().rstrip(".")
    for source in sources:
        if host == source.domain or host.endswith("." + source.domain):
            return source
    return None


@dataclass(frozen=True, slots=True)
class Vocabulary:
    label: str
    terms: tuple[str, ...]


CROP_TERMS: dict[str, Vocabulary] = {
    "rice": Vocabulary("rice", ("rice", "paddy", "oryza")),
    "wheat": Vocabulary("wheat", ("wheat", "triticum")),
    "maize": Vocabulary("maize", ("maize", "corn", "zea mays")),
    "cotton": Vocabulary("cotton", ("cotton", "gossypium")),
    "sugarcane": Vocabulary("sugarcane", ("sugarcane", "sugar cane", "saccharum")),
    "soybean": Vocabulary("soybean", ("soybean", "soya", "soy bean", "glycine max")),
    "groundnut": Vocabulary("groundnut", ("groundnut", "peanut", "arachis")),
    "chickpea": Vocabulary("chickpea", ("chickpea", "chick pea", "bengal gram", "cicer")),
    "tomato": Vocabulary("tomato", ("tomato", "solanum lycopersicum", "lycopersicon")),
    "potato": Vocabulary("potato", ("potato", "solanum tuberosum")),
    "onion": Vocabulary("onion", ("onion", "allium cepa")),
    "chilli": Vocabulary("chilli pepper", ("chilli", "chili", "hot pepper", "capsicum", "pepper")),
}

CONDITION_TERMS: dict[str, Vocabulary] = {
    "blast": Vocabulary("blast", ("blast", "magnaporthe", "pyricularia")),
    "brown_spot": Vocabulary(
        "brown spot", ("brown spot", "bipolaris", "cochliobolus", "helminthosporium")
    ),
    "bacterial_blight": Vocabulary(
        "bacterial leaf blight", ("bacterial blight", "bacterial leaf blight", "xanthomonas")
    ),
    "tungro": Vocabulary("tungro virus", ("tungro",)),
    "bacterial_spot": Vocabulary("bacterial spot", ("bacterial spot", "xanthomonas")),
    "early_blight": Vocabulary("early blight", ("early blight", "alternaria")),
    "late_blight": Vocabulary("late blight", ("late blight", "phytophthora")),
    "leaf_mold": Vocabulary(
        "leaf mold", ("leaf mold", "leaf mould", "passalora", "fulvia", "cladosporium")
    ),
    "mosaic_virus": Vocabulary("mosaic virus", ("mosaic",)),
    "septoria_leaf_spot": Vocabulary("septoria leaf spot", ("septoria",)),
    "spider_mites": Vocabulary("spider mites", ("spider mite", "tetranychus", "mite")),
    "target_spot": Vocabulary("target spot", ("target spot", "corynespora")),
    "yellow_leaf_curl_virus": Vocabulary(
        "yellow leaf curl virus", ("yellow leaf curl", "tylcv", "leaf curl")
    ),
    "fungal_disease": Vocabulary(
        "fungal leaf diseases",
        ("fungal", "fungus", "fungi", "leaf spot", "blight", "mildew", "rust", "anthracnose"),
    ),
    "bacterial_disease": Vocabulary("bacterial diseases", ("bacterial", "bacteria", "bacterium")),
    "viral_disease": Vocabulary("virus diseases", ("virus", "viral", "mosaic")),
    "insect_pest": Vocabulary(
        "insect pests",
        ("insect", "pest", "aphid", "whitefly", "thrips", "caterpillar", "borer", "beetle"),
    ),
    "mite_damage": Vocabulary("mite damage", ("mite",)),
    "water_stress": Vocabulary(
        "drought stress", ("drought", "water stress", "moisture stress", "wilting", "irrigation")
    ),
    "waterlogging": Vocabulary(
        "waterlogging", ("waterlogging", "waterlogged", "flooding", "drainage", "excess water")
    ),
    "heat_stress": Vocabulary("heat stress", ("heat stress", "high temperature", "heat")),
    "cold_stress": Vocabulary("cold injury", ("cold", "frost", "chilling", "low temperature")),
    "nutrient_deficiency": Vocabulary(
        "nutrient deficiency symptoms",
        ("deficiency", "nutrient", "nitrogen", "potassium", "magnesium", "chlorosis"),
    ),
    "chemical_injury": Vocabulary(
        "herbicide injury",
        ("herbicide injury", "phytotoxicity", "chemical injury", "spray injury", "drift"),
    ),
}

# Subset of Tavily's `country` values; anything else is simply not sent.
TAVILY_COUNTRIES = frozenset(
    {
        "afghanistan", "australia", "bangladesh", "bhutan", "brazil", "cambodia", "cameroon",
        "canada", "chile", "china", "colombia", "egypt", "ethiopia", "france", "germany",
        "ghana", "india", "indonesia", "iran", "iraq", "italy", "japan", "kenya", "malawi",
        "malaysia", "mali", "mexico", "morocco", "mozambique", "myanmar", "nepal",
        "netherlands", "new zealand", "nigeria", "pakistan", "peru", "philippines", "rwanda",
        "senegal", "south africa", "spain", "sri lanka", "tanzania", "thailand", "turkey",
        "uganda", "ukraine", "united kingdom", "united states", "vietnam", "zambia", "zimbabwe",
    }
)  # fmt: skip


def mentions_any(text: str, terms: tuple[str, ...]) -> bool:
    lowered = text.lower()
    return any(re.search(rf"\b{re.escape(term)}(?:e?s)?\b", lowered) for term in terms)
