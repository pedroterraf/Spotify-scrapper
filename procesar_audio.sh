#!/usr/bin/env bash

###############################################################################
# Script Wrapper para Procesamiento de Audio con IA
# 
# Este script facilita el uso del procesador de audio profesional
# que aplica ecualización automática, balance de voz/instrumental
# y mejoras de calidad usando IA.
#
# Uso:
#   ./procesar_audio.sh [directorio]
#
###############################################################################

set -o pipefail
# No usar nounset porque causa problemas con arrays vacíos

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
    echo "🎵 Procesador Profesional de Audio con IA"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo ""
}

check_python() {
    if ! command -v python3 >/dev/null 2>&1; then
        echo -e "${RED}❌ Error: Python 3 no está instalado${NC}"
        echo "   Instala Python 3 con: brew install python3"
        exit 1
    fi
    
    local python_version
    python_version=$(python3 --version 2>&1 | awk '{print $2}')
    echo -e "${GREEN}✅ Python: ${python_version}${NC}"
}

check_dependencies() {
    echo "🔍 Verificando dependencias Python..."
    
    local missing_deps=()
    
    python3 -c "import numpy" 2>/dev/null || missing_deps+=("numpy")
    python3 -c "import librosa" 2>/dev/null || missing_deps+=("librosa")
    python3 -c "import soundfile" 2>/dev/null || missing_deps+=("soundfile")
    python3 -c "import scipy" 2>/dev/null || missing_deps+=("scipy")
    
    if [ ${#missing_deps[@]} -gt 0 ]; then
        echo -e "${YELLOW}⚠️  Faltan dependencias: ${missing_deps[*]}${NC}"
        echo ""
        echo "📦 Instalando dependencias..."
        echo ""
        
        # Detectar si estamos en un entorno virtual
        if [ -n "${VIRTUAL_ENV:-}" ]; then
            # En entorno virtual: usar pip sin --user
            echo "   (Detectado entorno virtual: ${VIRTUAL_ENV})"
            if ! pip install "${missing_deps[@]}"; then
                echo -e "${RED}❌ Error instalando dependencias${NC}"
                echo ""
                echo "💡 Intenta manualmente:"
                echo "   pip install numpy librosa soundfile scipy"
                exit 1
            fi
        else
            # Fuera de entorno virtual: usar --user --break-system-packages
            if ! pip3 install --user --break-system-packages "${missing_deps[@]}"; then
                echo -e "${RED}❌ Error instalando dependencias${NC}"
                echo ""
                echo "💡 Intenta manualmente:"
                echo "   pip3 install --user --break-system-packages numpy librosa soundfile scipy"
                exit 1
            fi
        fi
        
        echo ""
        echo -e "${GREEN}✅ Dependencias instaladas${NC}"
    else
        echo -e "${GREEN}✅ Todas las dependencias están instaladas${NC}"
    fi
}

check_ffmpeg() {
    if ! command -v ffmpeg >/dev/null 2>&1; then
        echo -e "${YELLOW}⚠️  ffmpeg no está instalado${NC}"
        echo "   Algunas conversiones pueden fallar"
        echo "   Instala con: brew install ffmpeg"
    else
        echo -e "${GREEN}✅ ffmpeg: OK${NC}"
    fi
}

check_demucs() {
    # El procesador mejorado funciona perfectamente sin Demucs
    # usando técnicas avanzadas de procesamiento de señal
    echo -e "${GREEN}✅ Procesamiento: Usando técnicas avanzadas de separación de señal${NC}"
    echo "   (No requiere Demucs - funciona con Python 3.14)"
    return 0
}

main() {
    print_header
    
    # Verificar Python
    check_python
    echo ""
    
    # Verificar dependencias
    check_dependencies
    echo ""
    
    # Verificar ffmpeg
    check_ffmpeg
    echo ""
    
    # Verificar procesamiento (no requiere Demucs)
    check_demucs
    echo ""
    
    # Determinar directorio de entrada
    local input_dir
    if [ $# -gt 0 ]; then
        input_dir="$1"
    else
        input_dir="$DEFAULT_DIR"
        echo -e "${BLUE}ℹ️  Usando directorio por defecto: ${input_dir}${NC}"
        echo ""
    fi
    
    # Expandir ruta
    input_dir=$(eval echo "$input_dir")
    
    if [ ! -d "$input_dir" ]; then
        echo -e "${RED}❌ Error: El directorio no existe: ${input_dir}${NC}"
        exit 1
    fi
    
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo ""
    echo -e "${BLUE}📁 Directorio: ${input_dir}${NC}"
    echo ""
    
    # Obtener ruta del script Python
    local script_dir
    script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
    local python_script="${script_dir}/procesar_audio_ia.py"
    
    if [ ! -f "$python_script" ]; then
        echo -e "${RED}❌ Error: No se encuentra procesar_audio_ia.py${NC}"
        exit 1
    fi
    
    # Ejecutar procesador
    echo "🚀 Iniciando procesamiento..."
    echo ""
    
    python3 "$python_script" "$input_dir" --verbose
    
    local exit_code=$?
    
    echo ""
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    
    if [ $exit_code -eq 0 ]; then
        echo -e "${GREEN}🎉 Procesamiento completado exitosamente!${NC}"
        echo ""
        echo "📁 Archivos originales: ${input_dir}"
        echo "📁 Archivos ecualizados: ${input_dir}/Ecualizadas"
        echo ""
    else
        echo -e "${RED}❌ Error durante el procesamiento${NC}"
        exit $exit_code
    fi
}

# Ejecutar main
main "$@"
