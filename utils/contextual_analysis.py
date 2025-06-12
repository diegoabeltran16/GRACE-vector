# utils/contextual_analysis.py
"""
Módulo `contextual_analysis` para GRACE-vector

Este módulo ofrece una función para realizar un análisis contextual
simbólico y descriptivo del vector diario GRACE, proporcionando un
resumen neutral y científico del estado interno.
"""
from datetime import date
from utils.model_plutchik import analyze_plutchik as plutchik_emotion


def analyze_context(entry: dict) -> str:
    """
    Analiza el vector GRACE y retorna una interpretación contextuada.

    Parámetros:
    - entry: dict con claves 'G', 'R', 'A', 'C', 'E', 'note'

    Retorna:
    - str: Texto analítico y descriptivo.
    """
    G = entry.get("G")
    R = entry.get("R")
    A = entry.get("A")
    C = entry.get("C")
    E = entry.get("E")

    lines = []
    lines.append(f"Fecha: {date.today().isoformat()}")
    lines.append(f"• Género: {G}")
    lines.append(f"• Relaciones: {R}")
    lines.append(f"• Aprendizaje cognitivo: {A}")
    lines.append(f"• Cuerpo: {C}")
    lines.append(f"• Experiencia personal: {E}")
    if note := entry.get("note"):
        lines.append(f"• Nota: {note}")

    # Análisis emocional usando Plutchik
    emotion = plutchik_emotion(entry)  
    lines.append(f"• Emoción Plutchik dominante: {emotion}")

    return "\n".join(lines)
