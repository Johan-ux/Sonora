#!/bin/sh
# Doble clic en macOS: la Terminal abre este fichero y arranca Sonora con
# scripts/iniciar.sh, que la primera vez prepara el entorno.
exec "$(dirname "$0")/iniciar.sh" "$@"
