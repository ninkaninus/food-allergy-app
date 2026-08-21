#!/bin/bash
# Blokerer uigenkaldelige udgivelseshandlinger fra udgivelse-underagenten.
# Wired som PreToolUse-hook på Bash i .claude/agents/udgivelse.md
#
# BEMÆRK: gælder KUN den agent. Hovedsessionen må stadig committe og pushe —
# push til main ER deployet (CI bygger imaget, serveren poller det selv),
# og den beslutning skal tages af et menneske, der kigger med.

INPUT=$(cat)
COMMAND=$(echo "$INPUT" | jq -r '.tool_input.command // empty')
[ -z "$COMMAND" ] && exit 0

bloker() {
  echo "Blokeret: $1. Forbered ændringen, og giv kommandoen videre til hovedsessionen." >&2
  exit 2
}

echo "$COMMAND" | grep -qE '\bgit\s+push\b' \
  && bloker "git push er deploy i dette projekt"
echo "$COMMAND" | grep -qE '\bgit\s+(reset\s+--hard|rebase|filter-branch)\b' \
  && bloker "historik må ikke skrives om"
echo "$COMMAND" | grep -qE '\bgit\s+tag\b|\bgit\s+branch\s+-D\b' \
  && bloker "tags og sletning af grene er ikke tilladt"
echo "$COMMAND" | grep -qE '\bgit\s+(merge|commit)\b' \
  && bloker "commit og merge er hovedsessionens arbejde"
echo "$COMMAND" | grep -qE '\bgh\s+(release|pr)\s+(create|edit|delete|merge|close|upload)\b' \
  && bloker "udgivelser og PR'er må ikke ændres herfra"
echo "$COMMAND" | grep -qE '\bgh\s+workflow\s+run\b|\bgh\s+run\s+rerun\b' \
  && bloker "workflows må ikke sættes i gang herfra"
echo "$COMMAND" | grep -qE '\bdocker\s+(push|compose\s+(up|down|restart))\b' \
  && bloker "docker-handlinger mod en kørende opsætning er ikke tilladt"
echo "$COMMAND" | grep -qE 'autodeploy\.sh' \
  && bloker "deploy-scriptet kører på serveren, ikke herfra"

exit 0
