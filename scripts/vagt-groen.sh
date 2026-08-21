#!/bin/bash
# Vogter den ene invariant: motoren må gøre en vare rød eller gul — aldrig grøn.
# Kørt som PostToolUse-hook på Edit|Write (se .claude/settings.json).
#
# Hooket er med vilje dumt. Det fanger de to ændringer, der peger i den
# FARLIGE retning — under-advarsel — og lader alt andet passere:
#
#   1. En ny grøn dom i app/ uden for POST /api/products/{ean}/confirm.
#   2. Et regelsæt, der er blevet blødere: færre contains-mønstre eller
#      flere exclude-mønstre for et allergen.
#
# Det er ikke bevis for en fejl. Det er et sted, hvor et menneske skal se
# efter, før ændringen bliver til en vare, familien tror er sikker.

INPUT=$(cat)
FILE=$(echo "$INPUT" | jq -r '.tool_input.file_path // empty')
[ -z "$FILE" ] && exit 0
[ -f "$FILE" ] || exit 0

REL=${FILE#"$PWD"/}

# ---------------------------------------------------------------------------
# 1. Grønne domme uden for bekræftelsesruten
# ---------------------------------------------------------------------------
if echo "$REL" | grep -qE '^(app|ocr_service)/.*\.py$'; then
  # Kun TILFØJEDE linjer. Sammenligninger (== State.FREE) er læsning, ikke
  # en dom, og filtreres fra — det er tildelingerne, der kan bryde reglen.
  TILFOEJET=$(git diff HEAD -- "$REL" 2>/dev/null | grep '^+' | grep -v '^+++' \
    | grep -E "State\.FREE|state\s*=\s*['\"]free['\"]|['\"]state['\"]\s*:\s*['\"]free['\"]" \
    | grep -vE "==|!=|\bis\b|\bin\b|^\+\s*#")

  if [ -n "$TILFOEJET" ]; then
    {
      echo "Ny grøn dom tilføjet i $REL."
      echo
      echo "State.FREE sættes ét sted i appen: POST /api/products/{ean}/confirm,"
      echo "som kræver en indlogget bruger. Fravær af bevis er ikke bevis for"
      echo "fravær — fandt motoren ingenting, er svaret UNKNOWN."
      echo
      echo "Er linjen bekræftelsesruten selv, så sig det og fortsæt. Ellers er"
      echo "ændringen forkert. Kør de fire invariant-tests, før du går videre:"
      echo "  pytest tests/test_matcher.py::test_engine_never_returns_free \\"
      echo "         tests/test_matcher.py::test_ocr_mode_still_never_returns_free \\"
      echo "         tests/test_auth.py::test_only_human_confirmation_produces_green \\"
      echo "         tests/test_auth.py::test_unknown_barcode_returns_no_verdicts -q"
      echo
      echo "Tilføjede linjer:"
      echo "$TILFOEJET"
    } >&2
    exit 2
  fi
fi

# ---------------------------------------------------------------------------
# 2. Et blødere regelsæt
# ---------------------------------------------------------------------------
if [ "$REL" = "data/allergens.yaml" ]; then
  taeller() {
    awk '
      /^  - slug:/ { slug=$3; sec=""; next }
      /^    (contains|maybe|exclude):[[:space:]]*$/ { sec=$1; sub(/:$/, "", sec); next }
      /^    [a-zæøå_]+:/ { sec=""; next }
      /^      - / { if (slug != "" && sec != "") c[slug "\t" sec]++ }
      END { for (k in c) print k "\t" c[k] }
    ' | sort
  }

  FOER=$(git show HEAD:data/allergens.yaml 2>/dev/null | taeller)
  [ -z "$FOER" ] && exit 0
  NU=$(taeller < "$REL")

  BLOEDERE=$(awk -F'\t' '
    NR == FNR { foer[$1 "\t" $2] = $3; next }
    {
      key = $1 "\t" $2; set[key] = 1
      f = foer[key] + 0; n = $3 + 0
      if ($2 == "contains" && n < f)
        printf "  %s: contains %d -> %d (%d %s fjernet)\n", $1, f, n, f - n,
               (f - n == 1 ? "mønster" : "mønstre")
      if ($2 == "exclude" && n > f)
        printf "  %s: exclude %d -> %d (%d %s tilføjet)\n", $1, f, n, n - f,
               (n - f == 1 ? "undtagelse" : "undtagelser")
    }
    END {
      for (k in foer)
        if (!(k in set)) {
          split(k, d, "\t")
          if (d[2] == "contains")
            printf "  %s: contains %d -> 0 (hele afsnittet er væk)\n", d[1], foer[k]
        }
    }
  ' <(printf '%s\n' "$FOER") <(printf '%s\n' "$NU"))

  if [ -n "$BLOEDERE" ]; then
    {
      echo "Regelsættet er blevet blødere for mindst ét allergen:"
      echo "$BLOEDERE"
      echo
      echo "Færre contains-mønstre og flere exclude-mønstre peger samme vej:"
      echo "der advares om mindre end før. Over-advarsel irriterer;"
      echo "under-advarsel gør et barn sygt."
      echo
      echo "Før du går videre:"
      echo "  - kør pytest tests/test_matcher.py -q"
      echo "  - kontrollér at en ny exclude ikke maskerer et længere"
      echo "    contains/maybe-mønster (_mask() har protect netop derfor)"
      echo "  - skriv i svaret, hvilken rigtig falsk positiv undtagelsen er til"
    } >&2
    exit 2
  fi
fi

exit 0
