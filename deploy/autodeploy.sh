#!/usr/bin/env bash
# Pull-baseret deploy-agent til unRAID — serverens halvdel af auto-deploy.
# Se deploy/UNRAID.md for opsætning og .github/workflows/deploy.yml for
# CI-halvdelen.
#
# Princippet er Argo CD's, kogt ned til én maskine: git er den ønskede
# tilstand, agenten sammenligner og afstemmer. Konkret:
#
#   1. Hent origin/main. Ny commit? Ellers stop.
#   2. Findes image'et ghcr.io/...:sha-<commit>? Ellers stop — det betyder
#      at CI ikke er færdig, eller at testene fejlede. Ingen grønne tests,
#      intet deploy.
#   3. git reset --hard, pin APP_IMAGE i .env til sha-tagget, compose up.
#   4. Vent på at containerens healthcheck melder healthy. Gør den ikke det,
#      rulles der tilbage til sidste kendte gode commit + image.
#
# Kør den fra User Scripts-plugin'et på et cron-skema, fx hvert 5. minut.
# Den tager en fil-lås, så overlappende kørsler er ufarlige.
#
# Kræver kun det, stock unRAID har: bash, docker, flock. git følger IKKE
# med unRAID — mangler den, kører git-kommandoerne i en engangs-container
# (alpine/git) med samme stier, så resultatet er identisk.
#
# Alt kan overstyres med miljøvariabler; defaults passer til layoutet i
# deploy/UNRAID.md.

set -euo pipefail

REPO_DIR="${REPO_DIR:-/mnt/user/appdata/allergiscan/repo}"
SECRETS_DIR="${SECRETS_DIR:-/mnt/user/appdata/allergiscan/secrets}"
BRANCH="${BRANCH:-main}"
IMAGE="${IMAGE:-ghcr.io/ninkaninus/food-allergy-app}"
GHCR_USER="${GHCR_USER:-ninkaninus}"
STATE_FILE="$REPO_DIR/.deploy-state"      # sidste commit der bestod healthcheck
HEALTH_TIMEOUT="${HEALTH_TIMEOUT:-90}"     # sekunder; containerens probe kører hvert 30. s

# Filerne i repoet ejes typisk af root eller nobody på unRAID; uden dette
# nægter git at røre dem ("dubious ownership").
export GIT_CONFIG_COUNT=1 GIT_CONFIG_KEY_0=safe.directory GIT_CONFIG_VALUE_0='*'

log() { printf '%s  %s\n' "$(date '+%F %T')" "$*"; }

run_git() {
    if command -v git >/dev/null 2>&1; then
        git "$@"
        return
    fi
    local extra=()
    [ -d "$SECRETS_DIR" ] && extra+=(-v "$SECRETS_DIR:$SECRETS_DIR:ro")
    [ -n "${GIT_SSH_COMMAND:-}" ] && extra+=(-e "GIT_SSH_COMMAND=$GIT_SSH_COMMAND")
    docker run --rm -v "$REPO_DIR:$REPO_DIR" -w "$REPO_DIR" \
        -e GIT_CONFIG_COUNT -e GIT_CONFIG_KEY_0 -e GIT_CONFIG_VALUE_0 \
        "${extra[@]}" alpine/git "$@"
}

# Opdatér eller tilføj KEY=VALUE i .env. .env er gitignoreret, så
# git reset --hard rører den ikke.
set_env() {
    local key=$1 val=$2
    if grep -q "^${key}=" .env 2>/dev/null; then
        sed -i "s|^${key}=.*|${key}=${val}|" .env
    else
        printf '%s=%s\n' "$key" "$val" >>.env
    fi
}

wait_healthy() {
    local waited=0 status=ukendt
    while [ "$waited" -lt "$HEALTH_TIMEOUT" ]; do
        status=$(docker inspect --format '{{.State.Health.Status}}' allergiscan 2>/dev/null || echo mangler)
        [ "$status" = healthy ] && return 0
        sleep 3
        waited=$((waited + 3))
    done
    log "healthcheck: status er '$status' efter ${HEALTH_TIMEOUT}s"
    return 1
}

deploy() {
    local sha=$1
    run_git reset --hard --quiet "$sha"
    set_env APP_IMAGE "$IMAGE:sha-$sha"
    docker compose up -d --quiet-pull
}

rollback() {
    local last
    last=$(cat "$STATE_FILE" 2>/dev/null || true)
    if [ -z "$last" ]; then
        log "FEJL: deploy fejlede og der er ingen kendt god version at rulle tilbage til"
        exit 1
    fi
    log "ruller tilbage til $last"
    deploy "$last"
    if wait_healthy; then
        log "rollback lykkedes — appen kører på $last, men den nye commit er stadig i stykker"
    else
        log "FEJL: rollback til $last bestod heller ikke healthcheck — kig manuelt på det NU"
    fi
    exit 1
}

main() {
    exec 9>"$REPO_DIR/.deploy-lock"
    flock -n 9 || exit 0    # en anden kørsel er i gang

    cd "$REPO_DIR"

    # Læseadgang: deploy-nøgle til git (privat repo) og token til GHCR
    # (privat package). Begge er valgfrie — offentligt repo klonet over
    # https og offentlig pakke kræver ingen af delene.
    if [ -f "$SECRETS_DIR/deploy_key" ]; then
        export GIT_SSH_COMMAND="ssh -i $SECRETS_DIR/deploy_key -o IdentitiesOnly=yes -o UserKnownHostsFile=$SECRETS_DIR/known_hosts -o StrictHostKeyChecking=accept-new"
    fi
    if [ -f "$SECRETS_DIR/ghcr_token" ]; then
        docker login ghcr.io -u "$GHCR_USER" --password-stdin <"$SECRETS_DIR/ghcr_token" >/dev/null 2>&1
    fi

    run_git fetch --quiet origin "$BRANCH"
    local want last_good running
    want=$(run_git rev-parse "origin/$BRANCH")
    last_good=$(cat "$STATE_FILE" 2>/dev/null || true)
    running=$(docker inspect --format '{{.State.Running}}' allergiscan 2>/dev/null || echo false)

    if [ "$want" = "$last_good" ] && [ "$running" = true ]; then
        exit 0    # afstemt — ingenting at gøre
    fi

    # Findes imaget for den ønskede commit? Ellers er CI ikke færdig (eller
    # testene fejlede), og så venter vi bare til næste kørsel.
    if ! docker pull --quiet "$IMAGE:sha-$want" >/dev/null 2>&1; then
        log "intet image for $want endnu — CI kører stadig eller fejlede; prøver igen senere"
        exit 0
    fi

    log "deployer $want (fra $(run_git rev-parse --short HEAD))"
    deploy "$want"
    wait_healthy || rollback

    echo "$want" >"$STATE_FILE"
    log "ok — $want kører og er healthy"
}

main "$@"
