#!/usr/bin/env bash

###############################################################################
# Script para convertir canciones ecualizadas a MP3
# 
# Convierte todos los archivos de audio en "Ecualizadas/" a MP3 320kbps
# y los guarda en "Ecualizadas MP3/" manteniendo la estructura de álbumes
#
# Uso:
#   ./convertir_a_mp3.sh [directorio_base]
#
###############################################################################

set -o pipefail

# Colores para output
readonly RED='\033[0;31m'
readonly GREEN='\033[0;32m'
readonly YELLOW='\033[1;33m'
readonly BLUE='\033[0;34m'
readonly NC='\033[0m' # No Color

# Directorio por defecto
readonly DEFAULT_DIR="$HOME/Desktop/Canciones Oscar"

###############################################################################
# FUNCIONES
###############################################################################

print_header() {
    echo ""
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "🎵 Convertidor de Audio a MP3"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo ""
}

check_ffmpeg() {
    if ! command -v ffmpeg >/dev/null 2>&1; then
        echo -e "${RED}❌ Error: ffmpeg no está instalado${NC}"
        echo "   Instala con: brew install ffmpeg"
        exit 1
    fi
    echo -e "${GREEN}✅ ffmpeg: OK${NC}"
}

convert_file() {
    local input_file="$1"
    local output_file="$2"
    
    # Crear directorio de salida si no existe
    mkdir -p "$(dirname "$output_file")"
    
    # Verificar que el archivo de entrada existe
    if [ ! -f "$input_file" ]; then
        return 1
    fi
    
    # Convertir a MP3 320kbps (usar comillas para manejar espacios)
    if ffmpeg -i "$input_file" \
        -codec:a libmp3lame \
        -b:a 320k \
        -q:a 0 \
        -y \
        "$output_file" \
        -loglevel error -stats 2>&1; then
        return 0
    else
        return 1
    fi
}

convert_directory() {
    local base_dir="$1"
    local ecualizadas_dir="${base_dir}/Ecualizadas"
    local output_dir="${base_dir}/Ecualizadas MP3"
    
    if [ ! -d "$ecualizadas_dir" ]; then
        echo -e "${RED}❌ Error: No se encuentra la carpeta 'Ecualizadas'${NC}"
        echo "   Buscando en: $ecualizadas_dir"
        exit 1
    fi
    
    echo -e "${BLUE}📁 Directorio de entrada: ${ecualizadas_dir}${NC}"
    echo -e "${BLUE}📁 Directorio de salida: ${output_dir}${NC}"
    echo ""
    
    # Contadores
    local total_files=0
    local converted=0
    local failed=0
    local skipped=0
    
    # Extensiones de audio soportadas
    local audio_extensions=("opus" "m4a" "aac" "flac" "wav" "ogg" "wma")
    
    # Procesar cada álbum
    while IFS= read -r -d '' album_dir; do
        album_name=$(basename "$album_dir")
        
        # Excluir archivos ocultos y carpetas especiales
        if [[ "$album_name" =~ ^\. ]]; then
            continue
        fi
        
        echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        echo -e "${BLUE}📀 Procesando álbum: ${album_name}${NC}"
        echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        
        # Crear directorio de salida para el álbum
        album_output_dir="${output_dir}/${album_name}"
        mkdir -p "$album_output_dir"
        
        # Procesar cada archivo de audio en el álbum
        while IFS= read -r -d '' audio_file; do
            total_files=$((total_files + 1))
            
            filename=$(basename "$audio_file")
            name_without_ext="${filename%.*}"
            ext="${filename##*.}"
            ext_lower=$(echo "$ext" | tr '[:upper:]' '[:lower:]')
            
            # Si ya es MP3, verificar si existe en destino
            if [ "$ext_lower" = "mp3" ]; then
                output_file="${album_output_dir}/${filename}"
                if [ -f "$output_file" ]; then
                    echo -e "   ⏭️  [${total_files}] ${filename} (ya es MP3, copiando...)"
                    if cp "$audio_file" "$output_file" 2>/dev/null; then
                        converted=$((converted + 1))
                    else
                        failed=$((failed + 1))
                    fi
                else
                    echo -e "   ⏭️  [${total_files}] ${filename} (ya es MP3, copiando...)"
                    if cp "$audio_file" "$output_file" 2>/dev/null; then
                        converted=$((converted + 1))
                    else
                        failed=$((failed + 1))
                    fi
                fi
                continue
            fi
            
            # Verificar si la extensión es de audio
            is_audio=false
            for ext_check in "${audio_extensions[@]}"; do
                if [ "$ext_lower" = "$ext_check" ]; then
                    is_audio=true
                    break
                fi
            done
            
            if [ "$is_audio" = false ]; then
                skipped=$((skipped + 1))
                continue
            fi
            
            # Archivo de salida
            output_file="${album_output_dir}/${name_without_ext}.mp3"
            
            # Verificar si ya existe
            if [ -f "$output_file" ]; then
                echo -e "   ⏭️  [${total_files}] ${filename} (ya convertido, omitiendo...)"
                skipped=$((skipped + 1))
                continue
            fi
            
            # Convertir
            echo -e "   🎵 [${total_files}] ${filename} → ${name_without_ext}.mp3"
            if convert_file "$audio_file" "$output_file"; then
                echo -e "      ${GREEN}✅ Convertido${NC}"
                converted=$((converted + 1))
            else
                echo -e "      ${RED}❌ Error en conversión${NC}"
                failed=$((failed + 1))
            fi
            
        done < <(find "$album_dir" -maxdepth 1 -type f -print0 | sort -z)
        
        echo ""
        
    done < <(find "$ecualizadas_dir" -mindepth 1 -maxdepth 1 -type d -print0 | sort -z)
    
    # Resumen
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo -e "${GREEN}📊 RESUMEN:${NC}"
    echo "   Total archivos: ${total_files}"
    echo -e "   ${GREEN}✅ Convertidos: ${converted}${NC}"
    echo -e "   ${YELLOW}⏭️  Omitidos: ${skipped}${NC}"
    if [ $failed -gt 0 ]; then
        echo -e "   ${RED}❌ Fallidos: ${failed}${NC}"
    fi
    echo ""
    echo -e "${GREEN}📁 Archivos MP3 guardados en: ${output_dir}${NC}"
    echo ""
}

main() {
    print_header
    
    # Verificar ffmpeg
    check_ffmpeg
    echo ""
    
    # Determinar directorio base
    local base_dir
    if [ $# -gt 0 ]; then
        base_dir="$1"
    else
        base_dir="$DEFAULT_DIR"
        echo -e "${BLUE}ℹ️  Usando directorio por defecto: ${base_dir}${NC}"
        echo ""
    fi
    
    # Expandir ruta
    base_dir=$(eval echo "$base_dir")
    
    if [ ! -d "$base_dir" ]; then
        echo -e "${RED}❌ Error: El directorio no existe: ${base_dir}${NC}"
        exit 1
    fi
    
    # Convertir
    convert_directory "$base_dir"
    
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo -e "${GREEN}🎉 Conversión completada!${NC}"
    echo ""
}

# Ejecutar main
main "$@"
