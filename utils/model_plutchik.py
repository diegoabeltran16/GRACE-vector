# utils/model_plutchik.py
"""
Módulo `model_plutchik` para GRACE-vector

Este módulo traduce combinaciones de pares de dimensiones GRACE
en emociones básicas del modelo de Plutchik, usando un mapeo
configurable en `config/plutchik_map.json`.
"""
import json
import os

# Ruta al archivo de mapeo
MAP_PATH = os.path.join("config", "plutchik_map.json")

# Pares de dimensiones a considerar
PAIRS = [
    ("A", "E"),  # Aprendizaje + Experiencia
    ("C", "R"),  # Cuerpo + Relaciones
    ("G", "R"),  # Género + Relaciones
    ("C", "E"),  # Cuerpo + Experiencia
    ("G", "E"),  # Género + Experiencia
]


def load_mappings():
    """
    Carga el diccionario de mapeo (dim1_code, dim2_code) -> emoción.
    El archivo JSON debe tener llaves de la forma "A5_E3": "Alegría".
    """
    if not os.path.exists(MAP_PATH):
        raise FileNotFoundError(f"No se encontró el archivo de mapeo {MAP_PATH}")
    with open(MAP_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def analyze_plutchik(entry: dict) -> list:
    """
    Analiza la entrada GRACE y retorna una lista de emociones detectadas
    basadas en pares de dimensiones.

    Parámetros:
    - entry: dict con claves 'G','R','A','C','E'

    Retorna:
    - List[str]: lista de emociones encontradas (puede estar vacía)
    """
    mappings = load_mappings()
    emotions = []

    # Recorrer pares y buscar mapeo de combinaciones
    for d1, d2 in PAIRS:
        code1 = entry.get(d1)
        code2 = entry.get(d2)
        if not code1 or not code2:
            continue
        # Clave unida con guión bajo
        key = f"{d1}{code1[-1]}_{d2}{code2[-1]}"
        # También probar clave invertida para simetría
        alt_key = f"{d2}{code2[-1]}_{d1}{code1[-1]}"
        emotion = mappings.get(key) or mappings.get(alt_key)
        if emotion:
            emotions.append(emotion)
    return emotions
