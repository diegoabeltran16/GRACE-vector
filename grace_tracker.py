import json
import os
from datetime import date

from utils.formatter import summarize_vector
from utils.storage import save_entry
from utils.grace_analysis import compare_with_previous
from utils.contextual_analysis import analyze_context

CONFIG_PATH = "config/estados_grace.json"

# Explicación clara de las dimensiones GRACE
DIMENSION_MEANINGS = {
    "G": "Género: cómo te sientes respecto a tu identidad y expresión",
    "R": "Relaciones: calidad de tus vínculos hoy",
    "A": "Aprendizaje cognitivo: claridad mental y capacidad de comprender",
    "C": "Cuerpo: percepción física, energía, tensión o desconexión",
    "E": "Experiencia personal: estado emocional o narrativo dominante"
}


def load_states():
    """Carga los estados de config/estados_grace.json"""
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def ask_for_inputs(states):
    """
    Solicita al usuario un check-in para cada dimensión GRACE usando opciones numeradas
    y presentadas en orden aleatorio para una interacción más fluida.
    """
    import random
    inputs = {}
    print("\n🧭 Check-in diario de identidad - GRACE\n")
    for dim in ["G", "R", "A", "C", "E"]:
        # Mostrar descripción de la dimensión
        print(DIMENSION_MEANINGS[dim])
        # Preparar y mezclar las opciones disponibles
        options = list(states[dim].items())  # [(codigo, etiqueta), ...]
        random.shuffle(options)
        # Mostrar opciones numeradas al usuario
        for idx, (code, label) in enumerate(options, start=1):
            print(f"  {idx}. {label}")
        # Solicitar selección numérica
        choice = input(f"Selecciona una opción (1-{len(options)}) para {dim}: ").strip()
        while not (choice.isdigit() and 1 <= int(choice) <= len(options)):
            print("⚠️ Selección inválida. Ingresa un número válido.")
            choice = input(f"Selecciona una opción (1-{len(options)}) para {dim}: ").strip()
        # Mapear número a código real
        selected_code = options[int(choice) - 1][0]
        inputs[dim] = selected_code
    # Nota opcional
    note = input("\n¿Quieres añadir una nota para hoy? (opcional): ")
    inputs["note"] = note.strip()
    return inputs


def main():
    states = load_states()
    entry = ask_for_inputs(states)
    print("\n📋 Resumen del día:")
    summarize_vector(entry, states)
    
    # Análisis contextual (nuevo)
    context_result = analyze_context(entry)
    print("\n🔎 Análisis contextual:")
    print(context_result)
    
    save_entry(entry)
    compare_with_previous(entry)


if __name__ == "__main__":
    main()
