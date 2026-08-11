"""
Allergen-matchning mod fritekst-ingredienslister.

Designprincip: motoren afgør ALDRIG at noget er sikkert. Den kan kun sige
"her er noget", "her er måske noget" eller "jeg fandt ingenting" — og det
sidste er ikke det samme som frit. Kun et menneske kan sætte FREE.
"""

from __future__ import annotations

import hashlib
import re
import unicodedata
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

import yaml

MASK_CHAR = "\u2591"  # ░ — samme længde som det maskerede, så offsets holder

# OCR-tolerance.
#
# Tesseract læser 6-punkts tryk på krøllet folie med omkring 90% konfidens,
# og det er ikke godt nok: "skummetmælkspulver" bliver til
# "skummetmaalkspulver" og "jordbær" til "jordbzer". Eksakt matchning
# misser dem begge — altså præcis de to allergener, der stod på pakken.
#
# Løsningen er at folde æ/ø/å ned til ASCII og derefter tillade et par
# tegns afvigelse. "maalk" og folded "maelk" er én redigering fra hinanden.
# Falske positiver er billige her: OCR-resultatet skal alligevel gennem
# et menneske. Falske negativer er det, der gør et barn syg.
FOLD = str.maketrans({
    "æ": "ae", "ø": "oe", "å": "aa", "é": "e", "ü": "u", "ö": "oe", "ä": "ae",
    "0": "o", "1": "l", "5": "s", "@": "o", "|": "l",
})


def fold(text: str) -> str:
    """Ensretter danske tegn og de cifre, OCR oftest forveksler med bogstaver."""
    return text.translate(FOLD)


def _edit_distance(a: str, b: str, limit: int) -> int:
    """Levenshtein med tidlig afbrydelse. Returnerer limit+1 hvis for langt."""
    if abs(len(a) - len(b)) > limit:
        return limit + 1
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        best = i
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
            best = min(best, cur[j])
        if best > limit:
            return limit + 1
        prev = cur
    return prev[-1]


def _fuzzy_spans(text: str, patterns: list[str]) -> list[tuple[str, int, int, str]]:
    """
    Finder omtrentlige forekomster af mønstrene i OCR-tekst.

    Returnerer (mønster, start, slut, det-der-faktisk-stod). Kun mønstre på
    mindst fem tegn — kortere ord giver alt for mange tilfældige træf.
    """
    folded = fold(text.lower())
    hits: list[tuple[str, int, int, str]] = []
    words = [(m.start(), m.end(), m.group(0)) for m in re.finditer(r"[a-zæøå0-9|@]+", folded)]

    for raw in patterns:
        pat = fold(raw.lower())
        if len(pat) < 5 or " " in raw:
            continue
        limit = 1 if len(pat) < 9 else 2
        for start, end, word in words:
            # Bemærk: der skippes ikke på word == pat. Fuzzy-passet kører
            # først når det eksakte pass fandt nul, og "aeggeblomme" er
            # netop et ord, der kun matcher efter foldning.
            candidates = [word]
            # sammensat ord: prøv også vinduer inde i ordet
            if len(word) > len(pat):
                step = max(1, len(pat) // 3)
                candidates += [
                    word[i : i + len(pat)] for i in range(0, len(word) - len(pat) + 1, step)
                ]
            if any(_edit_distance(c, pat, limit) <= limit for c in candidates):
                hits.append((raw, start, min(end, len(text)), text[start:end]))
                break
    return hits


class State(str, Enum):
    CONTAINS = "contains"      # rød: allergenet er fundet
    TRACE_RISK = "trace_risk"  # orange: sporadvarsel eller usikker ingrediens
    UNKNOWN = "unknown"        # grå: ingen data, eller intet fundet i tekst
    FREE = "free"              # grøn: KUN sat manuelt af et menneske


class Basis(str, Enum):
    MANUAL = "manual"                  # menneske har læst emballagen
    OFF_ALLERGEN_TAG = "off_allergen_tag"
    OFF_TRACE_TAG = "off_trace_tag"
    TEXT_MATCH = "text_match"
    TEXT_MAYBE = "text_maybe"
    TRACE_STATEMENT = "trace_statement"      # "kan indeholde spor af mælk"
    TRACE_UNSPECIFIED = "trace_unspecified"  # sporadvarsel uden navn på allergen
    OCR_FUZZY = "ocr_fuzzy"            # omtrentligt match i OCR-tekst
    NO_TEXT = "no_text"                # der var slet ingen ingrediensliste
    NOT_FOUND_IN_TEXT = "not_found_in_text"


@dataclass
class Hit:
    pattern: str
    start: int
    end: int
    excerpt: str


@dataclass
class AllergenVerdict:
    allergen_slug: str
    state: State
    basis: Basis
    hits: list[Hit] = field(default_factory=list)

    @property
    def is_blocking(self) -> bool:
        return self.state in (State.CONTAINS, State.TRACE_RISK)


def normalize(text: str | None) -> str:
    """Ensretter tekst uden at ændre længden mere end nødvendigt."""
    if not text:
        return ""
    t = unicodedata.normalize("NFC", text).lower()
    # Open Food Facts markerer allergener med understreger: _mælk_
    t = t.replace("_", " ")
    t = re.sub(r"[*®™†•]", " ", t)
    t = re.sub(r"[\s\u00a0]+", " ", t)
    return t.strip()


def ingredients_hash(text: str | None) -> str:
    """Bruges til at invalidere manuelle godkendelser når opskriften ændrer sig."""
    return hashlib.sha256(normalize(text).encode("utf-8")).hexdigest()[:16]


def _compile(patterns: list[str]) -> list[tuple[str, re.Pattern]]:
    """
    Kræver ordgrænse FØR mønsteret, men ikke efter.

    Det giver: "mælk" rammer "mælkepulver" (præfiks i sammensat ord)
    men ikke "kokosmælk" (suffiks). Sammensætninger med allergenet bagest
    skal stå eksplicit i listen.
    """
    out = []
    for p in patterns or []:
        rx = re.compile(r"(?<![a-zæøåéü0-9])" + re.escape(p.lower()))
        out.append((p, rx))
    return out


class Ruleset:
    def __init__(self, path: str | Path):
        raw = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
        self.allergens: dict[str, dict] = {}
        for a in raw["allergens"]:
            self.allergens[a["slug"]] = {
                "meta": a,
                "contains": _compile(a.get("contains")),
                "maybe": _compile(a.get("maybe")),
                "exclude": _compile(a.get("exclude")),
            }
        self.trace_markers = _compile(raw.get("trace_markers", []))
        self._spor_cache: dict[str, bool] = {}

    # -- intern hjælper -----------------------------------------------------

    def _spor_spans(self, text: str) -> list[tuple[int, int]]:
        """
        Hvor står sporangivelserne — fra markøren til sætningen slutter.

        "Kan indeholde spor af mælk" er ikke det samme som mælk i
        ingredienslisten, og forskellen betyder noget for dem, der bruger
        appen: nogle tåler spor, andre gør ikke. Derfor skal teksten efter
        markøren behandles for sig.

        Spanet stopper ved punktum eller efter 200 tegn. Loftet er der,
        fordi OCR taber punktummer: uden det kunne én markør midt i en
        dårligt læst tekst sluge resten af ingredienslisten og gøre et
        rigtigt allergen til "kun spor" — under-advarsel er den farlige
        retning.
        """
        spans: list[tuple[int, int]] = []
        for _, rx in self.trace_markers:
            for m in rx.finditer(text):
                slut = len(text)
                for tegn in ".;!":
                    i = text.find(tegn, m.end())
                    if i != -1:
                        slut = min(slut, i)
                spans.append((m.start(), min(slut, m.end() + 200)))
        return spans

    def _naevner_allergen(self, tekst: str) -> bool:
        """Nævner sporangivelsen overhovedet et allergen, vi kender?

        Gør den det, er den konkret, og så gælder den kun de nævnte.
        Gør den det ikke ("kan indeholde spor af andre kornsorter"), er
        den vag, og så må alle få den gule advarsel.
        """
        if tekst in self._spor_cache:
            return self._spor_cache[tekst]
        svar = any(
            rx.search(tekst)
            for rules in self.allergens.values()
            for _, rx in rules["contains"]
        )
        if len(self._spor_cache) > 256:
            self._spor_cache.clear()
        self._spor_cache[tekst] = svar
        return svar

    @staticmethod
    def _mask(
        text: str,
        rules: list[tuple[str, re.Pattern]],
        protect: list[tuple[int, int]] | None = None,
    ) -> str:
        """
        Erstatter undtagelser med ░ af samme længde, så offsets bevares.

        `protect` beskytter spans, der allerede er ramt af et længere og mere
        specifikt mønster. Eksempel: undtagelsen "mælkesyre" må ikke maskere
        de første ni tegn af maybe-mønsteret "mælkesyrekultur" og dermed
        gøre det usynligt.
        """
        chars = list(text)
        for _, rx in rules:
            for m in rx.finditer(text):
                if protect and any(
                    m.start() < pe and ps < m.end() and (pe - ps) > (m.end() - m.start())
                    for ps, pe in protect
                ):
                    continue
                for i in range(m.start(), m.end()):
                    chars[i] = MASK_CHAR
        return "".join(chars)

    @staticmethod
    def _find(text: str, original: str, rules: list[tuple[str, re.Pattern]]) -> list[Hit]:
        hits: list[Hit] = []
        for label, rx in rules:
            for m in rx.finditer(text):
                lo = max(0, m.start() - 28)
                hi = min(len(original), m.end() + 28)
                hits.append(
                    Hit(
                        pattern=label,
                        start=m.start(),
                        end=m.end(),
                        excerpt=original[lo:hi].strip(),
                    )
                )
        # dedupliker overlappende træf, behold længste mønster
        hits.sort(key=lambda h: (h.start, -(h.end - h.start)))
        kept: list[Hit] = []
        for h in hits:
            if not any(k.start <= h.start and h.end <= k.end for k in kept):
                kept.append(h)
        return kept

    # -- offentligt API -----------------------------------------------------

    def evaluate(
        self,
        allergen_slug: str,
        ingredients_text: str | None,
        off_allergen_tags: list[str] | None = None,
        off_trace_tags: list[str] | None = None,
        ocr: bool = False,
    ) -> AllergenVerdict:
        rules = self.allergens[allergen_slug]
        off_tag = rules["meta"].get("off_tag")

        # 1. OFF's strukturerede allergen-tags vinder, når de findes.
        #    Kun gyldigt for EU-14; jordbær/banan har off_tag = null.
        if off_tag and off_tag in (off_allergen_tags or []):
            return AllergenVerdict(allergen_slug, State.CONTAINS, Basis.OFF_ALLERGEN_TAG)

        text = normalize(ingredients_text)
        if not text:
            return AllergenVerdict(allergen_slug, State.UNKNOWN, Basis.NO_TEXT)

        # 2. Maskér FØR match. Rækkefølgen er hele pointen.
        #    - contains ser hverken undtagelser eller maybe-mønstre.
        #      Uden det ville "jordbæraroma" blive rød på præfikset "jordbær".
        #    - maybe ser kun undtagelserne maskeret væk.
        for_contains = self._mask(text, rules["exclude"] + rules["maybe"])
        protect = [
            (h.start, h.end) for h in self._find(text, text, rules["maybe"])
        ]
        for_maybe = self._mask(text, rules["exclude"], protect=protect)

        # Sporangivelsen maskeres UD af contains-passet. "Kan indeholde spor
        # af mælk" må ikke læses som mælk i ingredienslisten — det er hele
        # forskellen mellem "aldrig" og "vi vurderer fra gang til gang".
        # Står allergenet BÅDE i listen og i sporangivelsen, vinder listen,
        # fordi det kun er spanet der maskeres.
        spor_spans = self._spor_spans(text)
        if spor_spans:
            tegn = list(for_contains)
            for a, b in spor_spans:
                for i in range(a, min(b, len(tegn))):
                    tegn[i] = MASK_CHAR
            for_contains = "".join(tegn)

        hits = self._find(for_contains, text, rules["contains"])
        if hits:
            return AllergenVerdict(allergen_slug, State.CONTAINS, Basis.TEXT_MATCH, hits)

        if off_tag and off_tag in (off_trace_tags or []):
            return AllergenVerdict(allergen_slug, State.TRACE_RISK, Basis.OFF_TRACE_TAG)

        # Kommer teksten fra OCR, prøver vi også omtrentlige match, før vi
        # nøjes med "fandt ingenting". Se FOLD-kommentaren øverst.
        if ocr:
            fz = _fuzzy_spans(
                for_contains, [p for p, _ in rules["contains"]]
            )
            if fz:
                return AllergenVerdict(
                    allergen_slug,
                    State.CONTAINS,
                    Basis.OCR_FUZZY,
                    [Hit(pattern=p, start=a, end=b, excerpt=raw) for p, a, b, raw in fz],
                )

        # Nævner sporangivelsen NETOP dette allergen? Så er det gult — og
        # kun for det allergen. Før gjorde enhver sporadvarsel alle 17
        # gule, også dem etiketten slet ikke nævner, og en app der råber
        # ulv ved hver vare bliver holdt op med at blive læst.
        if spor_spans:
            spor_hits: list[Hit] = []
            vagt = False
            for a, b in spor_spans:
                udsnit = text[a:b]
                for h in self._find(udsnit, udsnit, rules["contains"]):
                    spor_hits.append(Hit(h.pattern, a + h.start, a + h.end, h.excerpt))
                if not self._naevner_allergen(udsnit):
                    vagt = True
            if spor_hits:
                return AllergenVerdict(
                    allergen_slug, State.TRACE_RISK, Basis.TRACE_STATEMENT, spor_hits
                )
            if vagt:
                return AllergenVerdict(
                    allergen_slug,
                    State.TRACE_RISK,
                    Basis.TRACE_UNSPECIFIED,
                    [Hit(t, a, b, text[a:b]) for a, b in spor_spans for t in ["spor"]][:1],
                )

        maybe_hits = self._find(for_maybe, text, rules["maybe"])
        if maybe_hits:
            return AllergenVerdict(
                allergen_slug, State.TRACE_RISK, Basis.TEXT_MAYBE, maybe_hits
            )

        # 3. Intet fundet. Det er UNKNOWN — ikke FREE.
        return AllergenVerdict(allergen_slug, State.UNKNOWN, Basis.NOT_FOUND_IN_TEXT)

    def evaluate_all(self, slugs: list[str], **kw) -> list[AllergenVerdict]:
        return [self.evaluate(s, **kw) for s in slugs]


def aggregate(verdicts: list[AllergenVerdict]) -> str:
    """
    Samlet dom for en scanning.
      unsafe    — mindst ét allergen er fundet
      caution   — spor/usikkerhed
      unverified— ingen blokeringer, men ikke alt er manuelt bekræftet
      safe      — alle valgte allergener manuelt sat til FREE
    """
    if any(v.state == State.CONTAINS for v in verdicts):
        return "unsafe"
    if any(v.state == State.TRACE_RISK for v in verdicts):
        return "caution"
    if verdicts and all(
        v.state == State.FREE and v.basis == Basis.MANUAL for v in verdicts
    ):
        return "safe"
    return "unverified"
