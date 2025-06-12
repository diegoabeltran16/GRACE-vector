# utils/grace_analysis.py
"""
Módulo `grace_analysis` para GRACE-vector

Este módulo se encarga de realizar análisis comparativo entre el vector GRACE del día
actual y el del día anterior, permitiendo detectar cambios, estabilidad y dimensiones activas.
"""
import os
import json
from datetime import date

DATA_FILE = os.path.join("data", "registros", "registro.jsonl")

# Orden de dimensiones para asegurar consistencia
GRACE_ORDER = ["G", "R", "A", "C", "E"]


def load_previous_vector():
    """
    Carga la entrada GRACE anterior desde el archivo .jsonl.
    Retorna None si no hay suficientes entradas.
    """
    if not os.path.exists(DATA_FILE):
        return None

    with open(DATA_FILE, "r", encoding="utf-8") as f:
        lines = f.readlines()

    if len(lines) < 2:
        return None  # no hay comparación posible

    previous_line = lines[-2]  # penúltima línea
    return json.loads(previous_line)


def compare_with_previous(current_entry):
    """
    Compara el vector actual con el anterior y muestra un resumen lógico.
    """
    previous = load_previous_vector()
    if not previous:
        print("\nℹ️ Este es tu primer día o no hay entrada previa para comparar.")
        return

    def code_to_index(code):
        return int(code[1]) - 1

    prev_vector = [code_to_index(previous[dim]) for dim in GRACE_ORDER]
    curr_vector = [code_to_index(current_entry[dim]) for dim in GRACE_ORDER]

    # Detectar dimensiones que cambiaron
    changes = [(dim, previous[dim], current_entry[dim])
               for dim in GRACE_ORDER if previous[dim] != current_entry[dim]]

    # Calcular distancia euclidiana
    distance = sum((c - p) ** 2 for c, p in zip(curr_vector, prev_vector)) ** 0.5

    print("\n📊 Comparación con el día anterior:")
    print(f"→ Dimensiones que cambiaron: {len(changes)}")
    for dim, prev, curr in changes:
        print(f"   {dim}: {prev} → {curr}")

    print(f"→ Magnitud del cambio (distancia vectorial): {distance:.2f}")

    if distance == 0:
        print("→ Tu estado interno es idéntico al de ayer.")
    elif distance <= 2:
        print("→ Cambio leve: pequeños ajustes en tu identidad.")
    elif distance <= 4:
        print("→ Cambio moderado: tu estado se está reorganizando.")
    else:
        print("→ Cambio significativo: gran diferencia entre días.")
