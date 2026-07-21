#!/usr/bin/env bash

###############################################################################
# Script de Instalación de Dependencias
# 
# Instala todas las dependencias necesarias para el procesamiento de audio
# con IA de forma automática.
#
###############################################################################

set -o nounset
set -o pipefail

readonly GREEN='\033[0;32m'
readonly YELLOW='\033[1;33m'
readonly RED='\033[0;31m'
readonly NC='\033[0m'

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "📦 Instalador de Dependencias - Procesador de Audio con IA"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# Verificar Python
if ! command -v python3 >/dev/null 2>&1; then
    echo -e "${RED}❌ Python 3 no está instalado${NC}"
    echo "   Instala con: brew install python3"
    exit 1
fi

echo -e "${GREEN}✅ Python 3 encontrado${NC}"
echo ""

# Instalar dependencias básicas
echo "📦 Instalando dependencias básicas..."
echo "   (numpy, librosa, soundfile, scipy)"
echo ""

# Intentar con --user y --break-system-packages para macOS
if pip3 install --user --break-system-packages numpy librosa soundfile scipy; then
    echo ""
    echo -e "${GREEN}✅ Dependencias básicas instaladas${NC}"
else
    echo ""
    echo -e "${RED}❌ Error instalando dependencias básicas${NC}"
    echo ""
    echo "💡 Alternativa: Crear entorno virtual"
    echo "   python3 -m venv venv_audio"
    echo "   source venv_audio/bin/activate"
    echo "   pip install numpy librosa soundfile scipy"
    exit 1
fi

echo ""

# Preguntar por Demucs (opcional pero recomendado)
read -p "¿Instalar Demucs para separación de fuentes? (recomendado) (s/n): " -n 1 -r
echo ""

if [[ $REPLY =~ ^[SsYy]$ ]]; then
    echo ""
    echo "📦 Instalando Demucs (esto puede tomar varios minutos)..."
    echo ""
    
    echo ""
    echo "ℹ️  Nota: Demucs puede tener problemas con Python 3.14"
    echo "   Intentando instalar versión compatible..."
    echo ""
    
    # Intentar instalar desde git (versión más reciente)
    if pip3 install --user --break-system-packages git+https://github.com/facebookresearch/demucs.git; then
        echo ""
        echo -e "${GREEN}✅ Demucs instalado desde GitHub${NC}"
    elif pip3 install --user --break-system-packages "demucs<4.0"; then
        echo ""
        echo -e "${GREEN}✅ Demucs instalado (versión 3.x)${NC}"
    else
        echo ""
        echo -e "${YELLOW}⚠️  No se pudo instalar Demucs${NC}"
        echo ""
        echo "💡 El procesador funcionará sin Demucs (aún así aplicará mejoras):"
        echo "   - Ecualización automática ✅"
        echo "   - Balance de voz ✅"
        echo "   - Compresión y normalización ✅"
        echo "   - Reducción de ruido ✅"
        echo ""
        echo "   Solo faltará la separación de fuentes (opcional)"
        echo ""
        echo "   Si quieres intentar más tarde:"
        echo "   pip3 install --user --break-system-packages 'demucs<4.0'"
    fi
else
    echo -e "${YELLOW}ℹ️  Demucs omitido. Puedes instalarlo más tarde con:${NC}"
    echo "   pip3 install --user --break-system-packages demucs"
fi

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo -e "${GREEN}🎉 Instalación completada!${NC}"
echo ""
echo "Ahora puedes usar:"
echo "  ./procesar_audio.sh [directorio]"
echo ""
