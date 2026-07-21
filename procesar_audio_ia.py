#!/usr/bin/env python3
"""
Script profesional de procesamiento de audio con IA
===================================================

Este script procesa archivos de audio descargados aplicando:
- Separación de fuentes con Demucs (voz, instrumental)
- Ecualización automática inteligente
- Balance de voz/instrumental
- Normalización y mejora de calidad
- Reducción de ruido
- Compresión dinámica profesional

Autor: Sistema de procesamiento de audio profesional
"""

import os
import sys
import argparse
import subprocess
import shutil
from pathlib import Path
from typing import Optional, Tuple, List
import json

try:
    import numpy as np
    import librosa
    import soundfile as sf
    from scipy import signal
    from scipy.signal import butter, lfilter
    from scipy.ndimage import gaussian_filter1d
except ImportError as e:
    print(f"❌ Error: Faltan dependencias. Instala con: pip install numpy librosa soundfile scipy")
    print(f"   Error específico: {e}")
    sys.exit(1)

# Configuración profesional de procesamiento (ajustada para evitar saturación)
CONFIG = {
    'sample_rate': 44100,  # Calidad profesional
    'hop_length': 512,
    'n_fft': 2048,
    'vocal_boost_db': 1.5,  # Aumentar voz en 1.5dB (conservador)
    'instrumental_reduce_db': -1.0,  # Reducir instrumental en 1dB (conservador)
    'target_lufs': -18.0,  # Nivel de loudness más conservador (evita saturación)
    'compression_ratio': 2.5,  # Compresión más suave
    'compression_threshold': -15.0,  # Threshold más bajo (menos agresivo)
    'max_peak_db': -0.3,  # Límite máximo de picos para evitar clipping
}


class AudioProcessor:
    """Procesador profesional de audio con IA"""
    
    def __init__(self, input_path: Path, output_path: Path, verbose: bool = True):
        self.input_path = Path(input_path)
        self.output_path = Path(output_path)
        self.verbose = verbose
        self.temp_dir = None
        
    def log(self, message: str):
        """Log con formato profesional"""
        if self.verbose:
            print(f"   {message}")
    
    def check_demucs(self) -> bool:
        """Verificar si Demucs está instalado"""
        try:
            result = subprocess.run(
                ['python3', '-m', 'demucs', '--help'],
                capture_output=True,
                timeout=5
            )
            return result.returncode == 0
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return False
    
    def separate_sources(self, audio_file: Path) -> Optional[Path]:
        """
        Separar fuentes de audio usando Demucs
        Retorna la ruta al archivo de voz separado
        """
        if not self.check_demucs():
            # No usar Demucs, el procesador avanzado funciona mejor sin él
            return None
        
        self.log("🔬 Separando fuentes de audio con Demucs...")
        
        # Crear directorio temporal para Demucs
        if not self.temp_dir:
            self.temp_dir = Path(self.output_path.parent) / f".temp_demucs_{os.getpid()}"
            self.temp_dir.mkdir(exist_ok=True)
        
        try:
            # Ejecutar Demucs
            cmd = [
                'python3', '-m', 'demucs',
                '--out', str(self.temp_dir),
                '--two-stems=vocals',  # Solo separar voz
                str(audio_file)
            ]
            
            result = subprocess.run(
                cmd,
                capture_output=True,
                timeout=300,  # 5 minutos máximo
                text=True
            )
            
            if result.returncode != 0:
                self.log(f"⚠️  Demucs falló: {result.stderr[:200]}")
                return None
            
            # Buscar el archivo de voz separado
            # Demucs crea: temp_dir/separated/htdemucs/archivo/vocals.wav
            separated_dir = self.temp_dir / 'separated'
            if separated_dir.exists():
                for model_dir in separated_dir.iterdir():
                    if model_dir.is_dir():
                        audio_name = audio_file.stem
                        vocals_file = model_dir / audio_name / 'vocals.wav'
                        if vocals_file.exists():
                            return vocals_file
            
            return None
            
        except subprocess.TimeoutExpired:
            self.log("⏱️  Timeout en separación de fuentes")
            return None
        except Exception as e:
            self.log(f"⚠️  Error en separación: {str(e)[:100]}")
            return None
    
    def load_audio(self, file_path: Path) -> Tuple[np.ndarray, int]:
        """Cargar audio con librosa (optimizado para memoria)"""
        try:
            self.log(f"   Cargando: {file_path.name}...")
            
            # Verificar tamaño del archivo
            file_size_mb = file_path.stat().st_size / (1024 * 1024)
            if file_size_mb > 100:
                self.log(f"   ⚠️  Archivo grande ({file_size_mb:.1f} MB), cargando con cuidado...")
            
            # Cargar audio (mono=False para mantener estéreo si está disponible)
            y, sr = librosa.load(
                str(file_path), 
                sr=CONFIG['sample_rate'], 
                mono=False,
                duration=None  # Cargar todo el archivo
            )
            
            # Asegurar formato estéreo y tipo de dato eficiente
            if len(y.shape) == 1:
                y = np.array([y, y], dtype=np.float32)  # Usar float32 para ahorrar memoria
            elif y.shape[0] > 2:
                # Si tiene más de 2 canales, tomar solo los primeros 2
                y = y[:2].astype(np.float32)
            else:
                y = y.astype(np.float32)
            
            self.log(f"   ✅ Audio cargado: {y.shape}, duración: {len(y[0])/sr:.1f}s")
            return y, sr
        except MemoryError as e:
            raise Exception(f"Error de memoria cargando audio: {e}")
        except Exception as e:
            raise Exception(f"Error cargando audio: {e}")
    
    def create_shelf_filter(self, freq: float, gain_db: float, sr: int, shelf_type: str = 'low') -> Tuple[np.ndarray, np.ndarray]:
        """
        Crear filtro shelf moderno (low shelf o high shelf)
        Más musical que los filtros simples
        """
        # Calcular parámetros del filtro shelf
        A = 10 ** (gain_db / 40.0)  # Pre-warping
        w = 2 * np.pi * freq / sr
        
        if shelf_type == 'low':
            # Low shelf (para graves)
            alpha = np.sin(w) / 2 * np.sqrt((A + 1/A) * (1/0.9 - 1) + 2)
            cos_w = np.cos(w)
            
            b0 = A * ((A + 1) - (A - 1) * cos_w + 2 * np.sqrt(A) * alpha)
            b1 = 2 * A * ((A - 1) - (A + 1) * cos_w)
            b2 = A * ((A + 1) - (A - 1) * cos_w - 2 * np.sqrt(A) * alpha)
            a0 = (A + 1) + (A - 1) * cos_w + 2 * np.sqrt(A) * alpha
            a1 = -2 * ((A - 1) + (A + 1) * cos_w)
            a2 = (A + 1) + (A - 1) * cos_w - 2 * np.sqrt(A) * alpha
        else:
            # High shelf (para agudos)
            alpha = np.sin(w) / 2 * np.sqrt((A + 1/A) * (1/0.9 - 1) + 2)
            cos_w = np.cos(w)
            
            b0 = A * ((A + 1) + (A - 1) * cos_w + 2 * np.sqrt(A) * alpha)
            b1 = -2 * A * ((A - 1) + (A + 1) * cos_w)
            b2 = A * ((A + 1) + (A - 1) * cos_w - 2 * np.sqrt(A) * alpha)
            a0 = (A + 1) - (A - 1) * cos_w + 2 * np.sqrt(A) * alpha
            a1 = 2 * ((A - 1) - (A + 1) * cos_w)
            a2 = (A + 1) - (A - 1) * cos_w - 2 * np.sqrt(A) * alpha
        
        # Normalizar
        b = np.array([b0, b1, b2]) / a0
        a = np.array([1, a1/a0, a2/a0])
        
        return b, a
    
    def create_bell_filter(self, freq: float, gain_db: float, q: float, sr: int) -> Tuple[np.ndarray, np.ndarray]:
        """
        Crear filtro bell (peaking EQ) con Q ajustable
        Para ajustes precisos en frecuencias específicas
        """
        A = 10 ** (gain_db / 40.0)
        w = 2 * np.pi * freq / sr
        alpha = np.sin(w) / (2 * q)
        cos_w = np.cos(w)
        
        b0 = 1 + alpha * A
        b1 = -2 * cos_w
        b2 = 1 - alpha * A
        a0 = 1 + alpha / A
        a1 = -2 * cos_w
        a2 = 1 - alpha / A
        
        b = np.array([b0, b1, b2]) / a0
        a = np.array([1, a1/a0, a2/a0])
        
        return b, a
    
    def analyze_audio_needs(self, audio: np.ndarray, sr: int, magnitude: np.ndarray, freqs: np.ndarray) -> dict:
        """
        Análisis espectral moderno y detallado
        Detecta problemas específicos y sugiere correcciones musicales
        """
        # Bandas de frecuencia más detalladas (estilo profesional)
        freq_mask_sub = (freqs >= 20) & (freqs < 60)      # Sub-graves
        freq_mask_low = (freqs >= 60) & (freqs < 200)     # Graves
        freq_mask_low_mid = (freqs >= 200) & (freqs < 500)  # Medios-bajos
        freq_mask_mid = (freqs >= 500) & (freqs < 2000)   # Medios
        freq_mask_upper_mid = (freqs >= 2000) & (freqs < 5000)  # Medios-altos
        freq_mask_high = (freqs >= 5000) & (freqs < 10000)  # Agudos
        freq_mask_air = (freqs >= 10000) & (freqs < 20000)  # Aire/brillo
        
        # Rango vocal específico
        freq_mask_vocal_low = (freqs >= 300) & (freqs < 800)   # Voces graves
        freq_mask_vocal_mid = (freqs >= 800) & (freqs < 2500)   # Voces principales
        freq_mask_vocal_high = (freqs >= 2500) & (freqs < 4000)  # Voces agudas
        
        # Calcular energía por bandas
        energies = {
            'sub': np.mean(magnitude[freq_mask_sub, :]) if np.any(freq_mask_sub) else 0,
            'low': np.mean(magnitude[freq_mask_low, :]) if np.any(freq_mask_low) else 0,
            'low_mid': np.mean(magnitude[freq_mask_low_mid, :]) if np.any(freq_mask_low_mid) else 0,
            'mid': np.mean(magnitude[freq_mask_mid, :]) if np.any(freq_mask_mid) else 0,
            'upper_mid': np.mean(magnitude[freq_mask_upper_mid, :]) if np.any(freq_mask_upper_mid) else 0,
            'high': np.mean(magnitude[freq_mask_high, :]) if np.any(freq_mask_high) else 0,
            'air': np.mean(magnitude[freq_mask_air, :]) if np.any(freq_mask_air) else 0,
            'vocal_low': np.mean(magnitude[freq_mask_vocal_low, :]) if np.any(freq_mask_vocal_low) else 0,
            'vocal_mid': np.mean(magnitude[freq_mask_vocal_mid, :]) if np.any(freq_mask_vocal_mid) else 0,
            'vocal_high': np.mean(magnitude[freq_mask_vocal_high, :]) if np.any(freq_mask_vocal_high) else 0,
        }
        
        energy_total = np.mean(magnitude)
        
        # Calcular ratios y detectar problemas
        needs = {
            # Shelf filters (más musicales)
            'low_shelf_freq': 80.0,
            'low_shelf_gain': 0.0,
            'high_shelf_freq': 8000.0,
            'high_shelf_gain': 0.0,
            
            # Bell filters (ajustes precisos)
            'vocal_bell_freq': 2000.0,
            'vocal_bell_gain': 0.0,
            'vocal_bell_q': 1.5,
            
            'presence_bell_freq': 3500.0,
            'presence_bell_gain': 0.0,
            'presence_bell_q': 2.0,
            
            'warmth_bell_freq': 250.0,
            'warmth_bell_gain': 0.0,
            'warmth_bell_q': 1.0,
            
            # Notch filters (problemas específicos)
            'problem_freqs': [],  # Lista de frecuencias problemáticas
        }
        
        # Análisis inteligente moderno
        # Low shelf: analizar sub-graves y graves
        ratio_low = (energies['sub'] + energies['low']) / energy_total if energy_total > 0 else 0
        if ratio_low < 0.18:  # Muy débiles
            needs['low_shelf_gain'] = 2.0
        elif ratio_low < 0.25:  # Débiles
            needs['low_shelf_gain'] = 1.2
        elif ratio_low > 0.40:  # Demasiado fuertes
            needs['low_shelf_gain'] = -1.0
        
        # High shelf: analizar agudos y aire
        ratio_high = (energies['high'] + energies['air']) / energy_total if energy_total > 0 else 0
        if ratio_high < 0.12:  # Muy débiles
            needs['high_shelf_gain'] = 1.5
        elif ratio_high < 0.20:  # Débiles
            needs['high_shelf_gain'] = 0.8
        elif ratio_high > 0.30:  # Demasiado fuertes
            needs['high_shelf_gain'] = -0.8
        
        # Vocal bell: analizar rango vocal principal
        ratio_vocal = energies['vocal_mid'] / energy_total if energy_total > 0 else 0
        if ratio_vocal < 0.22:  # Voces muy débiles
            needs['vocal_bell_gain'] = 2.5
            needs['vocal_bell_freq'] = 2000.0
        elif ratio_vocal < 0.30:  # Voces débiles
            needs['vocal_bell_gain'] = 1.5
            needs['vocal_bell_freq'] = 1800.0
        elif ratio_vocal > 0.45:  # Voces muy fuertes
            needs['vocal_bell_gain'] = -1.0
            needs['vocal_bell_freq'] = 2000.0
        
        # Presence bell: brillo y claridad
        ratio_presence = energies['upper_mid'] / energy_total if energy_total > 0 else 0
        if ratio_presence < 0.15:  # Falta presencia
            needs['presence_bell_gain'] = 1.2
        elif ratio_presence > 0.28:  # Demasiada presencia
            needs['presence_bell_gain'] = -0.8
        
        # Warmth bell: calidez en medios-bajos
        ratio_warmth = energies['low_mid'] / energy_total if energy_total > 0 else 0
        if ratio_warmth < 0.20:  # Falta calidez
            needs['warmth_bell_gain'] = 1.0
        elif ratio_warmth > 0.35:  # Demasiada calidez (puede sonar boomy)
            needs['warmth_bell_gain'] = -1.2
        
        # Detectar resonancias problemáticas (notch filters)
        # Buscar picos anormales en el espectro
        magnitude_mean = np.mean(magnitude, axis=1)
        magnitude_std = np.std(magnitude, axis=1)
        peaks = magnitude_mean > (magnitude_mean.mean() + 2 * magnitude_std)
        
        # Frecuencias problemáticas comunes
        problem_ranges = [
            (200, 300, 'resonancia baja'),
            (400, 500, 'resonancia media'),
            (800, 1000, 'resonancia alta'),
        ]
        
        for low_freq, high_freq, _ in problem_ranges:
            mask = (freqs >= low_freq) & (freqs < high_freq)
            if np.any(mask):
                range_energy = np.mean(magnitude_mean[mask])
                if range_energy > energy_total * 0.4:  # Muy fuerte
                    needs['problem_freqs'].append((low_freq + high_freq) / 2)
        
        return needs
    
    def apply_eq(self, audio: np.ndarray, sr: int) -> np.ndarray:
        """
        Ecualización moderna profesional usando shelf filters, bell curves y spectral shaping
        Técnicas de mastering modernas aplicadas canción por canción
        """
        self.log("🎚️  Ecualización moderna profesional (shelf + bell filters)...")
        
        try:
            # Determinar n_fft según tamaño del archivo
            audio_length = len(audio[0]) if len(audio.shape) == 2 else len(audio)
            duration_seconds = audio_length / sr
            
            n_fft = CONFIG['n_fft']
            if duration_seconds > 300:
                n_fft = 1024
            elif duration_seconds > 180:
                n_fft = 1536
            
            # Analizar espectro
            if len(audio.shape) == 2:
                mono_audio = np.mean(audio, axis=0)
            else:
                mono_audio = audio
            
            # Calcular espectro
            self.log("   📊 Análisis espectral detallado...")
            stft = librosa.stft(mono_audio, n_fft=n_fft, hop_length=CONFIG['hop_length'])
            magnitude = np.abs(stft)
            
            # Limpiar memoria
            del mono_audio
            import gc
            gc.collect()
            
            # Frecuencias
            freqs = librosa.fft_frequencies(sr=sr, n_fft=n_fft)
            
            # Analizar necesidades específicas
            needs = self.analyze_audio_needs(audio, sr, magnitude, freqs)
            
            # Mostrar diagnóstico moderno
            self.log(f"   🎛️  Low Shelf ({needs['low_shelf_freq']:.0f}Hz): {needs['low_shelf_gain']:+.1f}dB")
            if needs['vocal_bell_gain'] != 0:
                self.log(f"   🎤 Vocal Bell ({needs['vocal_bell_freq']:.0f}Hz, Q={needs['vocal_bell_q']:.1f}): {needs['vocal_bell_gain']:+.1f}dB")
            if needs['presence_bell_gain'] != 0:
                self.log(f"   ✨ Presence Bell ({needs['presence_bell_freq']:.0f}Hz): {needs['presence_bell_gain']:+.1f}dB")
            if needs['warmth_bell_gain'] != 0:
                self.log(f"   🔥 Warmth Bell ({needs['warmth_bell_freq']:.0f}Hz): {needs['warmth_bell_gain']:+.1f}dB")
            self.log(f"   🌟 High Shelf ({needs['high_shelf_freq']:.0f}Hz): {needs['high_shelf_gain']:+.1f}dB")
            
            # Aplicar filtros modernos en el dominio del tiempo (más musical)
            self.log("   🎵 Aplicando filtros profesionales...")
            
            if len(audio.shape) == 2:
                processed_channels = []
                for channel in audio:
                    processed = channel.copy()
                    
                    # Low Shelf Filter (graves)
                    if needs['low_shelf_gain'] != 0:
                        b, a = self.create_shelf_filter(needs['low_shelf_freq'], needs['low_shelf_gain'], sr, 'low')
                        processed = lfilter(b, a, processed)
                    
                    # Warmth Bell (calidez)
                    if needs['warmth_bell_gain'] != 0:
                        b, a = self.create_bell_filter(needs['warmth_bell_freq'], needs['warmth_bell_gain'], needs['warmth_bell_q'], sr)
                        processed = lfilter(b, a, processed)
                    
                    # Vocal Bell (voces)
                    if needs['vocal_bell_gain'] != 0:
                        b, a = self.create_bell_filter(needs['vocal_bell_freq'], needs['vocal_bell_gain'], needs['vocal_bell_q'], sr)
                        processed = lfilter(b, a, processed)
                    
                    # Presence Bell (brillo)
                    if needs['presence_bell_gain'] != 0:
                        b, a = self.create_bell_filter(needs['presence_bell_freq'], needs['presence_bell_gain'], needs['presence_bell_q'], sr)
                        processed = lfilter(b, a, processed)
                    
                    # High Shelf Filter (agudos/aire)
                    if needs['high_shelf_gain'] != 0:
                        b, a = self.create_shelf_filter(needs['high_shelf_freq'], needs['high_shelf_gain'], sr, 'high')
                        processed = lfilter(b, a, processed)
                    
                    # Notch filters para problemas específicos
                    for problem_freq in needs['problem_freqs']:
                        b, a = self.create_bell_filter(problem_freq, -3.0, 5.0, sr)  # Q alto para notch
                        processed = lfilter(b, a, processed)
                    
                    processed_channels.append(processed)
                
                audio = np.array(processed_channels, dtype=audio.dtype)
            else:
                # Mono: mismo proceso
                processed = audio.copy()
                
                if needs['low_shelf_gain'] != 0:
                    b, a = self.create_shelf_filter(needs['low_shelf_freq'], needs['low_shelf_gain'], sr, 'low')
                    processed = lfilter(b, a, processed)
                
                if needs['warmth_bell_gain'] != 0:
                    b, a = self.create_bell_filter(needs['warmth_bell_freq'], needs['warmth_bell_gain'], needs['warmth_bell_q'], sr)
                    processed = lfilter(b, a, processed)
                
                if needs['vocal_bell_gain'] != 0:
                    b, a = self.create_bell_filter(needs['vocal_bell_freq'], needs['vocal_bell_gain'], needs['vocal_bell_q'], sr)
                    processed = lfilter(b, a, processed)
                
                if needs['presence_bell_gain'] != 0:
                    b, a = self.create_bell_filter(needs['presence_bell_freq'], needs['presence_bell_gain'], needs['presence_bell_q'], sr)
                    processed = lfilter(b, a, processed)
                
                if needs['high_shelf_gain'] != 0:
                    b, a = self.create_shelf_filter(needs['high_shelf_freq'], needs['high_shelf_gain'], sr, 'high')
                    processed = lfilter(b, a, processed)
                
                for problem_freq in needs['problem_freqs']:
                    b, a = self.create_bell_filter(problem_freq, -3.0, 5.0, sr)
                    processed = lfilter(b, a, processed)
                
                audio = processed
            
            # Limpiar memoria
            gc.collect()
            
            return audio
            
        except MemoryError as e:
            self.log(f"❌ Error de memoria: {e}")
            return self._apply_simple_eq(audio, sr)
        except Exception as e:
            self.log(f"❌ Error: {str(e)[:200]}")
            return self._apply_simple_eq(audio, sr)
    
    def _apply_simple_eq(self, audio: np.ndarray, sr: int) -> np.ndarray:
        """Ecualización simple usando filtros IIR (usa menos memoria)"""
        if len(audio.shape) == 2:
            mono = np.mean(audio, axis=0)
        else:
            mono = audio
        
        # Filtros simples para cada banda
        # Graves
        b_low, a_low = butter(2, [60, 250], btype='band', fs=sr)
        low_boost = lfilter(b_low, a_low, mono) * 1.5
        
        # Medios (voz)
        b_mid, a_mid = butter(2, [500, 2000], btype='band', fs=sr)
        mid_boost = lfilter(b_mid, a_mid, mono) * 2.0
        
        # Agudos
        b_high, a_high = butter(2, [2000, 8000], btype='band', fs=sr)
        high_boost = lfilter(b_high, a_high, mono) * 0.5
        
        # Mezclar
        enhanced = mono + low_boost + mid_boost + high_boost
        
        # Normalizar
        max_val = np.max(np.abs(enhanced))
        if max_val > 0.95:
            enhanced = enhanced * (0.95 / max_val)
        
        if len(audio.shape) == 2:
            return np.array([enhanced, enhanced], dtype=audio.dtype)
        else:
            return enhanced
    
    def separate_vocals_advanced(self, audio: np.ndarray, sr: int) -> Tuple[np.ndarray, np.ndarray]:
        """
        Separación avanzada de voces usando técnicas de procesamiento de señal
        Basado en diferencias espectrales y correlación entre canales (optimizado)
        """
        try:
            if len(audio.shape) == 2:
                # Estéreo: usar técnica de cancelación de centro
                # La voz suele estar en el centro (mismo en ambos canales)
                center = (audio[0] + audio[1]) / 2
                sides = (audio[0] - audio[1]) / 2
                
                # La voz está principalmente en el centro
                # Filtrar frecuencias vocales del centro
                b_vocal, a_vocal = butter(4, [300, 3400], btype='band', fs=sr)
                vocals_center = lfilter(b_vocal, a_vocal, center)
                
                # El instrumental está en los lados y en frecuencias fuera del rango vocal
                b_instr, a_instr = butter(4, [80, 200], btype='band', fs=sr)
                instrumental_low = lfilter(b_instr, a_instr, center)
                
                # Combinar instrumental (lados + graves del centro)
                instrumental = sides * 1.5 + instrumental_low * 0.5
                
                # Ajustar niveles
                vocals = vocals_center * 1.2
                instrumental = instrumental * 0.8
                
                # Limpiar memoria intermedia
                del center, sides, vocals_center, instrumental_low
                import gc
                gc.collect()
                
                return vocals.astype(np.float32), instrumental.astype(np.float32)
            else:
                # Mono: usar filtros espectrales
                b_vocal, a_vocal = butter(6, [300, 3400], btype='band', fs=sr)
                vocals = lfilter(b_vocal, a_vocal, audio)
                
                # Instrumental = original - voces (con filtro para evitar cancelación)
                b_instr, a_instr = butter(4, [80, 8000], btype='band', fs=sr)
                instrumental = lfilter(b_instr, a_instr, audio - vocals * 0.7)
                
                return vocals.astype(np.float32), instrumental.astype(np.float32)
        except Exception as e:
            # Fallback: retornar audio original como voces y silencio como instrumental
            self.log(f"⚠️  Error en separación avanzada: {str(e)[:100]}")
            if len(audio.shape) == 2:
                return audio[0], np.zeros_like(audio[0])
            else:
                return audio, np.zeros_like(audio)
    
    def balance_vocals(self, audio: np.ndarray, vocals_file: Optional[Path] = None) -> np.ndarray:
        """
        Balancear voz e instrumental con técnicas avanzadas
        """
        if vocals_file and vocals_file.exists():
            self.log("🎤 Balanceando voz e instrumental (con separación)...")
            try:
                vocals, _ = self.load_audio(vocals_file)
                
                # Aumentar voz
                vocals_boosted = vocals * (10 ** (CONFIG['vocal_boost_db'] / 20))
                
                # Reducir instrumental (audio original - voz)
                if len(audio.shape) == 2:
                    instrumental = audio - vocals
                    instrumental_reduced = instrumental * (10 ** (CONFIG['instrumental_reduce_db'] / 20))
                    # Mezclar
                    audio = vocals_boosted + instrumental_reduced
                else:
                    # Mono
                    instrumental = audio - vocals
                    instrumental_reduced = instrumental * (10 ** (CONFIG['instrumental_reduce_db'] / 20))
                    audio = vocals_boosted + instrumental_reduced
                
            except Exception as e:
                self.log(f"⚠️  Error en balance: {str(e)[:100]}. Usando separación avanzada...")
                # Fallback a separación avanzada
                vocals, instrumental = self.separate_vocals_advanced(audio, CONFIG['sample_rate'])
                vocals_boosted = vocals * (10 ** (CONFIG['vocal_boost_db'] / 20))
                instrumental_reduced = instrumental * (10 ** (CONFIG['instrumental_reduce_db'] / 20))
                
                if len(audio.shape) == 2:
                    audio = np.array([vocals_boosted + instrumental_reduced, 
                                    vocals_boosted + instrumental_reduced])
                else:
                    audio = vocals_boosted + instrumental_reduced
        else:
            # Separación avanzada sin IA
            self.log("🎤 Separando y balanceando voz/instrumental (técnica avanzada)...")
            vocals, instrumental = self.separate_vocals_advanced(audio, CONFIG['sample_rate'])
            
            # Aumentar voces y reducir instrumental
            vocals_boosted = vocals * (10 ** (CONFIG['vocal_boost_db'] / 20))
            instrumental_reduced = instrumental * (10 ** (CONFIG['instrumental_reduce_db'] / 20))
            
            # Mezclar inteligentemente
            if len(audio.shape) == 2:
                # Mantener estéreo
                mixed = vocals_boosted + instrumental_reduced
                audio = np.array([mixed, mixed])
            else:
                audio = vocals_boosted + instrumental_reduced
        
        return audio
    
    def apply_compression(self, audio: np.ndarray) -> np.ndarray:
        """Aplicar compresión dinámica profesional"""
        self.log("🔧 Aplicando compresión dinámica...")
        
        if len(audio.shape) == 2:
            # Procesar cada canal
            processed = []
            for channel in audio:
                # Compresor simple
                threshold = CONFIG['compression_threshold']
                ratio = CONFIG['compression_ratio']
                
                # Convertir a dB
                db_audio = 20 * np.log10(np.abs(channel) + 1e-10)
                
                # Aplicar compresión
                over_threshold = db_audio > threshold
                compressed_db = np.where(
                    over_threshold,
                    threshold + (db_audio - threshold) / ratio,
                    db_audio
                )
                
                # Convertir de vuelta
                compressed = np.sign(channel) * (10 ** (compressed_db / 20))
                processed.append(compressed)
            
            return np.array(processed)
        else:
            # Mono
            threshold = CONFIG['compression_threshold']
            ratio = CONFIG['compression_ratio']
            
            db_audio = 20 * np.log10(np.abs(audio) + 1e-10)
            over_threshold = db_audio > threshold
            compressed_db = np.where(
                over_threshold,
                threshold + (db_audio - threshold) / ratio,
                db_audio
            )
            
            return np.sign(audio) * (10 ** (compressed_db / 20))
    
    def apply_peak_limiter(self, audio: np.ndarray) -> np.ndarray:
        """Aplicar limitador de picos para prevenir clipping"""
        max_peak_linear = 10 ** (CONFIG['max_peak_db'] / 20)  # -0.3dB
        
        # Encontrar el pico máximo
        max_val = np.max(np.abs(audio))
        
        if max_val > max_peak_linear:
            # Reducir ganancia para que el pico esté en el límite
            gain_reduction = max_peak_linear / max_val
            audio = audio * gain_reduction
            self.log(f"   ⚠️  Limitando picos: {20*np.log10(max_val):.1f}dB → {CONFIG['max_peak_db']:.1f}dB")
        
        return audio
    
    def normalize_lufs(self, audio: np.ndarray, sr: int) -> np.ndarray:
        """Normalizar a nivel LUFS profesional (conservador para evitar saturación)"""
        self.log("📊 Normalizando a nivel profesional (LUFS)...")
        
        # Aplicar limitador de picos primero
        audio = self.apply_peak_limiter(audio)
        
        # Calcular LUFS aproximado (simplificado)
        if len(audio.shape) == 2:
            mono = np.mean(audio, axis=0)
        else:
            mono = audio
        
        # RMS
        rms = np.sqrt(np.mean(mono ** 2))
        current_lufs = 20 * np.log10(rms + 1e-10) - 23  # Aproximación
        
        # Ajustar a target (más conservador)
        gain_db = CONFIG['target_lufs'] - current_lufs
        
        # Limitar ganancia máxima para evitar saturación
        gain_db = min(gain_db, 6.0)  # Máximo +6dB (más conservador que antes)
        gain_db = max(gain_db, -12.0)  # Mínimo -12dB (no reducir demasiado)
        
        gain_linear = 10 ** (gain_db / 20)
        
        audio_normalized = audio * gain_linear
        
        # Aplicar limitador de picos final
        audio_normalized = self.apply_peak_limiter(audio_normalized)
        
        return audio_normalized
    
    def reduce_noise(self, audio: np.ndarray, sr: int) -> np.ndarray:
        """Reducir ruido de fondo"""
        self.log("🔇 Reduciendo ruido de fondo...")
        
        if len(audio.shape) == 2:
            mono = np.mean(audio, axis=0)
        else:
            mono = audio
        
        # Filtro de reducción de ruido simple (high-pass suave)
        b, a = butter(2, 80, btype='high', fs=sr)
        filtered = lfilter(b, a, mono)
        
        # Mezclar con original (70% filtrado, 30% original)
        if len(audio.shape) == 2:
            audio = audio * 0.3 + np.array([filtered, filtered]) * 0.7
        else:
            audio = audio * 0.3 + filtered * 0.7
        
        return audio
    
    def process_file(self, input_file: Path) -> bool:
        """Procesar un archivo de audio completo (con manejo robusto de errores)"""
        output_wav = None
        audio = None
        vocals_file = None
        
        try:
            self.log(f"🎵 Procesando: {input_file.name}")
            
            # Verificar tamaño del archivo antes de procesar
            file_size_mb = input_file.stat().st_size / (1024 * 1024)
            if file_size_mb > 50:
                self.log(f"⚠️  Archivo grande ({file_size_mb:.1f} MB), procesando con cuidado...")
            
            # 1. Separar fuentes (si Demucs está disponible)
            try:
                vocals_file = self.separate_sources(input_file)
            except Exception as e:
                self.log(f"⚠️  Error en separación de fuentes: {str(e)[:100]}. Continuando sin separación...")
                vocals_file = None
            
            # 2. Cargar audio
            try:
                self.log("📥 Cargando audio...")
                audio, sr = self.load_audio(input_file)
            except MemoryError as e:
                self.log(f"❌ Error de memoria cargando archivo: {e}")
                return False
            except Exception as e:
                self.log(f"❌ Error cargando audio: {e}")
                return False
            
            # 3. Reducir ruido
            try:
                self.log("🔇 Reduciendo ruido...")
                audio = self.reduce_noise(audio, sr)
                audio = self.apply_peak_limiter(audio)  # Prevenir clipping
                import gc
                gc.collect()
            except Exception as e:
                self.log(f"⚠️  Error reduciendo ruido: {str(e)[:100]}. Continuando...")
            
            # 4. Aplicar ecualización
            try:
                audio = self.apply_eq(audio, sr)
                audio = self.apply_peak_limiter(audio)  # Prevenir clipping después de EQ
                import gc
                gc.collect()
            except MemoryError as e:
                self.log(f"❌ Error de memoria en ecualización: {e}")
                return False
            except Exception as e:
                self.log(f"❌ Error en ecualización: {str(e)[:200]}")
                return False
            
            # 5. Balancear voz/instrumental
            try:
                audio = self.balance_vocals(audio, vocals_file)
                audio = self.apply_peak_limiter(audio)  # Prevenir clipping
                import gc
                gc.collect()
            except Exception as e:
                self.log(f"⚠️  Error balanceando voces: {str(e)[:100]}. Continuando...")
            
            # 6. Compresión dinámica
            try:
                audio = self.apply_compression(audio)
                audio = self.apply_peak_limiter(audio)  # Prevenir clipping
                import gc
                gc.collect()
            except Exception as e:
                self.log(f"⚠️  Error en compresión: {str(e)[:100]}. Continuando...")
            
            # 7. Normalización (ya incluye limitador de picos)
            try:
                audio = self.normalize_lufs(audio, sr)
                import gc
                gc.collect()
            except Exception as e:
                self.log(f"⚠️  Error en normalización: {str(e)[:100]}. Continuando...")
            
            # 8. Guardar
            try:
                output_file = self.output_path / input_file.name
                output_file.parent.mkdir(parents=True, exist_ok=True)
                
                # Guardar en formato de alta calidad
                # Primero guardar como WAV temporal para procesamiento
                output_wav = output_file.with_suffix('.wav')
                self.log("💾 Guardando archivo procesado...")
                
                # Asegurar que el audio esté en el formato correcto para soundfile
                if len(audio.shape) == 2:
                    # Estéreo: transponer para soundfile (frames, channels)
                    sf.write(str(output_wav), audio.T, sr, format='WAV', subtype='PCM_24')
                else:
                    # Mono: agregar dimensión de canal
                    sf.write(str(output_wav), audio, sr, format='WAV', subtype='PCM_24')
                
                # Limpiar memoria después de guardar
                del audio
                import gc
                gc.collect()
            except MemoryError as e:
                self.log(f"❌ Error de memoria guardando archivo: {e}")
                return False
            except Exception as e:
                self.log(f"❌ Error guardando archivo: {e}")
                return False
            
            # Convertir al formato original si no es WAV
            if input_file.suffix.lower() != '.wav':
                original_suffix = input_file.suffix.lower()
                final_output = output_file.with_suffix(original_suffix)
                
                # Determinar codec y bitrate según formato
                if original_suffix == '.mp3':
                    codec = 'libmp3lame'
                    bitrate = '320k'
                elif original_suffix == '.opus':
                    codec = 'libopus'
                    bitrate = '256k'
                elif original_suffix in ['.m4a', '.aac']:
                    codec = 'aac'
                    bitrate = '256k'
                else:
                    # Mantener WAV si no se reconoce el formato
                    if output_wav.exists():
                        output_wav.rename(output_file)
                    return True
                
                # Convertir con ffmpeg
                self.log(f"🔄 Convirtiendo a {original_suffix}...")
                cmd = [
                    'ffmpeg', '-i', str(output_wav),
                    '-codec:a', codec,
                    '-b:a', bitrate,
                    '-y', str(final_output)
                ]
                
                result = subprocess.run(cmd, capture_output=True, check=False, timeout=300)
                if result.returncode == 0 and final_output.exists():
                    if output_wav.exists():
                        output_wav.unlink()  # Eliminar WAV temporal
                else:
                    # Si falla la conversión, mantener WAV
                    self.log(f"⚠️  Error en conversión, manteniendo WAV")
                    if output_wav.exists():
                        output_wav.rename(output_file)
            else:
                # Ya es WAV, solo renombrar
                if output_wav.exists():
                    output_wav.rename(output_file)
            
            self.log(f"✅ Completado: {output_file.name}")
            return True
            
        except MemoryError:
            self.log(f"❌ Error de memoria procesando {input_file.name}")
            return False
        except KeyboardInterrupt:
            self.log("⚠️  Interrumpido por el usuario")
            raise
        except Exception as e:
            self.log(f"❌ Error procesando {input_file.name}: {str(e)[:200]}")
            import traceback
            if self.verbose:
                traceback.print_exc()
            return False
        finally:
            # Limpiar archivos temporales
            if output_wav and output_wav.exists() and output_wav.suffix == '.wav':
                try:
                    # Solo eliminar si no se convirtió exitosamente
                    final_file = output_wav.with_suffix(input_file.suffix if input_file.suffix.lower() != '.wav' else '.wav')
                    if not final_file.exists():
                        output_wav.unlink()
                except:
                    pass
            
            if self.temp_dir and self.temp_dir.exists():
                try:
                    shutil.rmtree(self.temp_dir)
                except:
                    pass
    
    def process_directory(self, input_dir: Path) -> Tuple[int, int]:
        """Procesar todos los archivos de audio en un directorio"""
        audio_extensions = {'.mp3', '.wav', '.flac', '.m4a', '.opus', '.ogg'}
        
        audio_files = [
            f for f in input_dir.iterdir()
            if f.is_file() and f.suffix.lower() in audio_extensions
        ]
        
        if not audio_files:
            self.log("⚠️  No se encontraron archivos de audio")
            return 0, 0
        
        self.log(f"📁 Encontrados {len(audio_files)} archivos de audio")
        
        success = 0
        failed = 0
        
        for audio_file in sorted(audio_files):
            if self.process_file(audio_file):
                success += 1
            else:
                failed += 1
        
        return success, failed


def organize_files(source_dir: Path, base_output_dir: Path):
    """
    Organizar archivos procesados manteniendo estructura original
    Crea: Ecualizadas/album/canciones
    Mantiene: album/canciones (originales)
    """
    source_dir = Path(source_dir)
    base_output_dir = Path(base_output_dir)
    
    ecualizadas_dir = base_output_dir / "Ecualizadas"
    ecualizadas_dir.mkdir(parents=True, exist_ok=True)
    
    # Carpetas a excluir del procesamiento
    excluded_dirs = {'Ecualizadas', '.DS_Store', '__pycache__', '.git'}
    
    # Procesar cada álbum
    for album_dir in source_dir.iterdir():
        if not album_dir.is_dir():
            continue
        
        album_name = album_dir.name
        
        # Excluir carpetas especiales
        if album_name in excluded_dirs or album_name.startswith('.'):
            continue
        
        output_album_dir = ecualizadas_dir / album_name
        output_album_dir.mkdir(parents=True, exist_ok=True)
        
        print(f"\n📀 Procesando álbum: {album_name}")
        print("=" * 60)
        
        try:
            processor = AudioProcessor(album_dir, output_album_dir, verbose=True)
            success, failed = processor.process_directory(album_dir)
            
            print(f"\n✅ Completadas: {success} | ❌ Fallidas: {failed}")
        except KeyboardInterrupt:
            print("\n⚠️  Procesamiento interrumpido por el usuario")
            raise
        except Exception as e:
            print(f"\n❌ Error procesando álbum {album_name}: {str(e)}")
            import traceback
            traceback.print_exc()
            continue


def main():
    parser = argparse.ArgumentParser(
        description='Procesador profesional de audio con IA',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=r"""
Ejemplos de uso:
  # Procesar todas las canciones descargadas
  python3 procesar_audio_ia.py ~/Desktop/Canciones\ Oscar
  
  # Procesar un álbum específico
  python3 procesar_audio_ia.py ~/Desktop/Canciones\ Oscar/proyecto-identidad
        """
    )
    
    parser.add_argument(
        'input_dir',
        type=str,
        help='Directorio con las canciones a procesar'
    )
    
    parser.add_argument(
        '--output-dir',
        type=str,
        default=None,
        help='Directorio de salida (por defecto: mismo que input_dir)'
    )
    
    parser.add_argument(
        '--verbose', '-v',
        action='store_true',
        default=True,
        help='Mostrar información detallada'
    )
    
    args = parser.parse_args()
    
    input_dir = Path(args.input_dir).expanduser().resolve()
    output_dir = Path(args.output_dir).expanduser().resolve() if args.output_dir else input_dir
    
    if not input_dir.exists():
        print(f"❌ Error: El directorio {input_dir} no existe")
        sys.exit(1)
    
    print("🎵 Procesador Profesional de Audio con IA")
    print("=" * 60)
    print(f"📁 Directorio de entrada: {input_dir}")
    print(f"📁 Directorio de salida: {output_dir}")
    print()
    
    # Verificar dependencias
    print("🔍 Verificando dependencias...")
    try:
        import numpy
        import librosa
        import soundfile
        from scipy import signal
        print("✅ Dependencias Python: OK")
    except ImportError as e:
        print(f"❌ Faltan dependencias: {e}")
        print("   Instala con: pip install numpy librosa soundfile scipy")
        sys.exit(1)
    
    # Verificar ffmpeg
    if not shutil.which('ffmpeg'):
        print("⚠️  ffmpeg no encontrado. Algunas conversiones pueden fallar.")
    else:
        print("✅ ffmpeg: OK")
    
    # Verificar Demucs (opcional, no necesario)
    try:
        result = subprocess.run(
            ['python3', '-m', 'demucs', '--help'],
            capture_output=True,
            timeout=5
        )
        if result.returncode == 0:
            print("ℹ️  Demucs: Instalado (no necesario, usando procesamiento avanzado)")
        else:
            print("✅ Procesamiento: Usando técnicas avanzadas de separación de señal")
    except:
        print("✅ Procesamiento: Usando técnicas avanzadas de separación de señal")
    
    print()
    
    # Procesar
    organize_files(input_dir, output_dir)
    
    print("\n" + "=" * 60)
    print("🎉 Procesamiento completado!")
    print(f"📁 Archivos originales: {input_dir}")
    print(f"📁 Archivos ecualizados: {output_dir}/Ecualizadas")
    print()


if __name__ == '__main__':
    main()
