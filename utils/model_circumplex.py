# utils/model_circumplex.py
"""
Módulo `model_circumplex` para GRACE-vector

Implementa un modelo híbrido que:
1. Carga un mapa de valencia y activación (arousal) desde `config/circumplex_map.json`.
2. Aplica modulación Yin/Yang (bits GRACE) para ajustar estos valores.
3. Calcula etiquetas de valencia/arousal y un estado global interpretativo.
"""
import json
import os
from statistics import mean

# Ruta al archivo de mapeo
MAPPING_PATH = os.path.join("config", "circumplex_map.json")


def load_circumplex_mapping() -> dict:
    """
    Carga el archivo JSON con mapeos de estado GRACE a valencia y arousal.

    El JSON debe tener la forma:
      {
        "A1": {"valence": -0.5, "arousal": -0.3},
        "C5": {"valence": 0.7,  "arousal": 0.8},
        ...
      }

    Retorna:
      dict: mapeo de códigos a sus valores.
    """
    if not os.path.exists(MAPPING_PATH):
        raise FileNotFoundError(f"No se encontró el archivo de mapeo: {MAPPING_PATH}")
    with open(MAPPING_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def apply_modulation(valence: float, arousal: float, bit: int) -> tuple[float, float]:
    """
    Ajusta valence y arousal según el bit Yin/Yang.

    Parámetros:
      valence (float): valor base de valencia
      arousal (float): valor base de activación
      bit (int): 1 para Yang (multiplicador 1.2), 0 para Yin (multiplicador 0.8)

    Retorna:
      tuple: (valence_mod, arousal_mod)
    """
    factor = 1.2 if bit == 1 else 0.8
    return valence * factor, arousal * factor


def analyze_circumplex(entry: dict, bits: dict) -> tuple[str, str, str]:
    """
    Analiza un vector GRACE con bits Yin/Yang y retorna:
      - Etiqueta de valencia (Positiva/Negativa)
      - Etiqueta de arousal (Alta/Baja)
      - Estado global descriptivo

    Parámetros:
      entry (dict): vector GRACE con claves 'G','R','A','C','E'
      bits (dict): diccionario {dim: 0|1} generado por collapse_neutral

    Retorna:
      tuple: (valence_label, arousal_label, state_global)
    """
    mapping = load_circumplex_mapping()
    valences = []
    arousals = []

    for dim, code in entry.items():
        if dim == 'note':
            continue
        base = mapping.get(code, {"valence": 0.0, "arousal": 0.5})
        val = base.get("valence", 0.0)
        aro = base.get("arousal", 0.5)
        bit = bits.get(dim, 0)
        v_mod, a_mod = apply_modulation(val, aro, bit)
        valences.append(v_mod)
        arousals.append(a_mod)

    valence_avg = mean(valences)
    arousal_avg = mean(arousals)

    # Etiquetas
    valence_label = "Positiva" if valence_avg >= 0 else "Negativa"
    arousal_label = "Alta" if arousal_avg >= 0.5 else "Baja"

    # Estado global interpretativo
    if valence_avg > 0 and arousal_avg > 0.5:
        state = "Activación creativa con potencial de ansiedad si no se regula."
    elif valence_avg < 0 and arousal_avg < 0.5:
        state = "Desgano reflexivo con baja energía."
    else:
        state = "Equilibrio emocional moderado."

    return valence_label, arousal_label, state
