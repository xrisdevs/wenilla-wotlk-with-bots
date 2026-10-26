#!/usr/bin/env bash
set -euo pipefail
umask 077
export ARENA_WWW="${ARENA_WWW:-/www}"
export ARENA_LOBBY_UI="${ARENA_LOBBY_UI:-/app/client/lobby}"
export ARENA_BUILDS="${ARENA_BUILDS:-/app/controller/lobby/builds.json}"
export WOW_DATA="${WOW_DATA:-/game-data}"
exec wenilla-arena-host
