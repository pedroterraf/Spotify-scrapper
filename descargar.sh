#!/usr/bin/env bash

###############################################################################
# Script de Descarga de Álbumes de Spotify
# 
# Descripción:
#   Obtiene la lista exacta de canciones de cada álbum desde la API de Spotify
#   y las descarga una por una desde YouTube en la mejor calidad disponible.
#
# Requisitos:
#   - yt-dlp: pipx install yt-dlp
#   - jq: brew install jq
#   - curl (incluido en macOS)
#
# Uso:
#   ./descargar.sh
#
###############################################################################

set -o nounset  # Error si variable no definida
set -o pipefail # Error en pipes
# Nota: No usamos errexit para permitir manejo manual de errores en descargas

###############################################################################
# CONFIGURACIÓN
###############################################################################

readonly DESCARGAS_DIR="$HOME/Desktop/Canciones Oscar"
readonly TIMEOUT_DESCARGAS=300  # 5 minutos por canción
readonly PAUSA_ENTRE_ALBUMES=3  # segundos

# IDs de los álbumes de Spotify
readonly -a ALBUMES_IDS=(
    "5uRYrFEMuJqp3jffO8gQx1"  # Proyecto Identidad
    "1x9UI81d0NKMPlx4LXQX9x"  # El Tango Es una Posibilidad Infinita
    "0Fk1hCjQXQif6B15shSgwq"  # Con T de Tango
    "6hnDbOfdPLWqs0HJS2iUXB"  # Homenaje A Carlos Gardel - Tangos De Siempre
    "3P8R9nvFRFP6PqWVAMKp8H"  # Homenaje A Carlos Gardel - Aquellos Tangos
)

# Nombres de los álbumes (para las carpetas)
readonly -a ALBUMES_NAMES=(
    "Proyecto Identidad"
    "El Tango Es una Posibilidad Infinita"
    "Con T de Tango"
    "Homenaje A Carlos Gardel - Tangos De Siempre"
    "Homenaje A Carlos Gardel - Aquellos Tangos"
)

# Tokens de Spotify: se leen de variables de entorno (ver .env.example).
# Nunca hardcodees tokens reales acá — este archivo se versiona en git.
if [ -f "$(dirname "${BASH_SOURCE[0]}")/.env" ]; then
    # shellcheck disable=SC1091
    source "$(dirname "${BASH_SOURCE[0]}")/.env"
fi

if [ -z "${SPOTIFY_TOKEN:-}" ] || [ -z "${CLIENT_TOKEN:-}" ]; then
    echo "❌ Error: faltan SPOTIFY_TOKEN y/o CLIENT_TOKEN."
    echo "   Copiá .env.example a .env y completá los tokens (ver README)."
    exit 1
fi
readonly SPOTIFY_TOKEN
readonly CLIENT_TOKEN

# Variables globales de control
TOTAL_ALBUMES=0
ALBUMES_COMPLETOS=0
TOTAL_CANCIONES=0
CANCIONES_DESCARGADAS=0

###############################################################################
# FUNCIONES AUXILIARES
###############################################################################

# Verificar que las herramientas necesarias estén instaladas
verificar_herramientas() {
    local herramientas_faltantes=()
    
    if ! command -v yt-dlp >/dev/null 2>&1; then
        herramientas_faltantes+=("yt-dlp")
    fi
    
    if ! command -v jq >/dev/null 2>&1; then
        herramientas_faltantes+=("jq")
    fi
    
    if [ ${#herramientas_faltantes[@]} -gt 0 ]; then
        echo "❌ Error: Faltan las siguientes herramientas:"
        for herramienta in "${herramientas_faltantes[@]}"; do
            echo "   - $herramienta"
        done
        echo ""
        echo "📦 Instalación:"
        echo "   pipx install yt-dlp"
        echo "   brew install jq"
        exit 1
    fi
}

# Limpiar nombre de archivo (quitar caracteres especiales)
limpiar_nombre() {
    echo "$1" | sed 's/[^a-zA-Z0-9]/-/g' | tr '[:upper:]' '[:lower:]'
}

###############################################################################
# FUNCIONES PRINCIPALES
###############################################################################

# Obtener lista de canciones de un álbum desde la API de Spotify
obtener_canciones_album() {
    local -r album_id="$1"
    local -r temp_file=$(mktemp)
    
    # Hacer request a la API de Spotify
    if ! curl -s --fail 'https://api-partner.spotify.com/pathfinder/v2/query' \
        -H 'accept: application/json' \
        -H 'accept-language: es' \
        -H 'app-platform: WebPlayer' \
        -H "authorization: Bearer $SPOTIFY_TOKEN" \
        -H "client-token: $CLIENT_TOKEN" \
        -H 'content-type: application/json;charset=UTF-8' \
        -H 'origin: https://open.spotify.com' \
        -H 'referer: https://open.spotify.com/' \
        -H 'sec-ch-ua: "Not:A-Brand";v="99", "Google Chrome";v="145", "Chromium";v="145"' \
        -H 'sec-ch-ua-mobile: ?0' \
        -H 'sec-ch-ua-platform: "macOS"' \
        -H 'sec-fetch-dest: empty' \
        -H 'sec-fetch-mode: cors' \
        -H 'sec-fetch-site: same-site' \
        -H 'spotify-app-version: 896000000' \
        -H 'user-agent: Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36' \
        --data-raw "{\"variables\":{\"uri\":\"spotify:album:$album_id\",\"locale\":\"intl-es\",\"offset\":0,\"limit\":50},\"operationName\":\"getAlbum\",\"extensions\":{\"persistedQuery\":{\"version\":1,\"sha256Hash\":\"b9bfabef66ed756e5e13f68a942deb60bd4125ec1f1be8cc42769dc0259b4b10\"}}}" \
        > "$temp_file"; then
        rm -f "$temp_file"
        return 1
    fi
    
    # Extraer canciones usando jq
    if [ -s "$temp_file" ]; then
        jq -r '.data.albumUnion.tracksV2.items[] | "\(.track.trackNumber)|\(.track.name)|\(.track.artists.items[0].profile.name)"' "$temp_file" 2>/dev/null
        local exit_code=$?
        rm -f "$temp_file"
        return $exit_code
    fi
    
    rm -f "$temp_file"
    return 1
}

# Descargar una canción desde YouTube en la mejor calidad disponible
descargar_cancion() {
    local -r numero="$1"
    local -r titulo="$2"
    local -r artista="$3"
    local -r album_dir="$4"
    local -r busqueda="$artista $titulo"
    
    echo "   🎵 [$numero] $artista - $titulo"
    
    # Intentar formatos en orden de preferencia (mejor calidad primero)
    local -a formatos=("opus" "m4a" "mp3")
    local -a calidades=("0" "0" "320K")
    local exit_code=1
    
    for i in "${!formatos[@]}"; do
        local formato="${formatos[$i]}"
        local calidad="${calidades[$i]}"
        
        local yt_dlp_cmd=(
            yt-dlp
            "ytsearch:$busqueda"
            --extract-audio
            --audio-format "$formato"
            --audio-quality "$calidad"
            --output "$album_dir/%(autonumber)02d - %(title)s.%(ext)s"
            --no-playlist
            --quiet
            --progress
        )
        
        if command -v timeout >/dev/null 2>&1; then
            if timeout "$TIMEOUT_DESCARGAS" "${yt_dlp_cmd[@]}" >/dev/null 2>&1; then
                exit_code=0
                break
            fi
        else
            if "${yt_dlp_cmd[@]}" >/dev/null 2>&1; then
                exit_code=0
                break
            fi
        fi
    done
    
    if [ $exit_code -eq 0 ]; then
        echo "      ✅ Descargada"
        return 0
    else
        echo "      ❌ Error al descargar"
        return 1
    fi
}

# Descargar un álbum completo
descargar_album() {
    local -r album_id="$1"
    local -r album_name="$2"
    local -r numero_album="$3"
    local -r total_albumes="$4"
    
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "📀 ÁLBUM $numero_album/$total_albumes: $album_name"
    echo ""
    
    # Crear directorio para este álbum
    local album_dir="$DESCARGAS_DIR/$(limpiar_nombre "$album_name")"
    mkdir -p "$album_dir"
    
    echo "🔍 Obteniendo lista de canciones desde Spotify..."
    
    # Obtener canciones del álbum
    local canciones
    if ! canciones=$(obtener_canciones_album "$album_id"); then
        echo "❌ Error: No se pudieron obtener las canciones del álbum"
        echo "   Verifica que los tokens sean válidos"
        return 1
    fi
    
    local total_canciones_album
    total_canciones_album=$(echo "$canciones" | wc -l | tr -d ' ')
    echo "✅ Encontradas $total_canciones_album canciones"
    echo ""
    echo "📋 Descargando canciones una por una..."
    echo ""
    
    local canciones_descargadas_album=0
    
    # Descargar cada canción
    while IFS='|' read -r numero titulo artista; do
        if [[ -n "$numero" && -n "$titulo" && -n "$artista" ]]; then
            if descargar_cancion "$numero" "$titulo" "$artista" "$album_dir"; then
                ((CANCIONES_DESCARGADAS++))
                ((canciones_descargadas_album++))
            fi
            ((TOTAL_CANCIONES++))
            echo ""
            sleep 1
        fi
    done <<< "$canciones"
    
    echo ""
    echo "✅ Álbum $numero_album completado ($canciones_descargadas_album/$total_canciones_album canciones)"
    ((ALBUMES_COMPLETOS++))
    return 0
}

###############################################################################
# MAIN
###############################################################################

main() {
    echo "🎵 Descarga de Álbumes de Spotify"
    echo "==================================="
    echo ""
    echo "ℹ️  Este script:"
    echo "   1. Obtiene la lista exacta de canciones desde Spotify"
    echo "   2. Descarga cada canción desde YouTube en la mejor calidad"
    echo "   3. Procesa álbum por álbum, canción por canción"
    echo ""
    
    # Verificar herramientas
    verificar_herramientas
    echo "✅ Herramientas disponibles"
    echo ""
    
    # Crear directorio de descargas
    if ! mkdir -p "$DESCARGAS_DIR"; then
        echo "❌ Error: No se pudo crear el directorio de descargas"
        exit 1
    fi
    
    if ! cd "$DESCARGAS_DIR"; then
        echo "❌ Error: No se pudo acceder al directorio de descargas"
        exit 1
    fi
    
    echo "📁 Descargando en: $DESCARGAS_DIR"
    echo ""
    echo "🎼 Procesando ${#ALBUMES_IDS[@]} álbumes..."
    echo ""
    
    # Inicializar variables de control
    TOTAL_ALBUMES=${#ALBUMES_IDS[@]}
    ALBUMES_COMPLETOS=0
    TOTAL_CANCIONES=0
    CANCIONES_DESCARGADAS=0
    
    # Recorrer cada álbum
    local contador=1
    for i in "${!ALBUMES_IDS[@]}"; do
        descargar_album "${ALBUMES_IDS[$i]}" "${ALBUMES_NAMES[$i]}" "$contador" "$TOTAL_ALBUMES"
        ((contador++))
        
        if [ $contador -le $TOTAL_ALBUMES ]; then
            echo ""
            echo "⏸️  Pausa de ${PAUSA_ENTRE_ALBUMES} segundos antes del siguiente álbum..."
            sleep "$PAUSA_ENTRE_ALBUMES"
            echo ""
        fi
    done
    
    # Mostrar resumen final
    echo ""
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "📊 RESUMEN FINAL:"
    echo "   Álbumes procesados: $TOTAL_ALBUMES"
    echo "   Álbumes completados: $ALBUMES_COMPLETOS"
    echo "   Total canciones: $TOTAL_CANCIONES"
    echo "   Canciones descargadas: $CANCIONES_DESCARGADAS"
    echo ""
    echo "📁 Archivos guardados en: $DESCARGAS_DIR"
    echo ""
    
    if [ $ALBUMES_COMPLETOS -gt 0 ]; then
        echo "🎉 ¡Descarga completada!"
        exit 0
    else
        echo "⚠️  No se descargaron álbumes completos"
        exit 1
    fi
}

# Ejecutar main
main "$@"
