import json
import os
from datetime import date

from utils.formatter import summarize_vector
from utils.storage import save_entry
from utils.grace_analysis import compare_with_previous
from utils.contextual_analysis import analyze_context
from utils.model_collapse import collapse_neutral
from utils.model_circumplex import analyze_circumplex

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
    y presentadas en orden aleatorio para una interacción más fluida. Incluye colapso
    inmediato de estados Neutral a receptivo (Yin) o activo (Yang).
    """
    import random
    inputs = {}
    bits = {}
    print("\n🧭 Check-in diario de identidad - GRACE\n")
    for dim in ["G", "R", "A", "C", "E"]:
        # Mostrar descripción de la dimensión
        print(DIMENSION_MEANINGS[dim])
        # Preparar y mezclar las opciones disponibles
        options = list(states[dim].items())
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

        # Colapso inmediato si es Neutral (índice 3)
        idx_code = int(selected_code[1]) if len(selected_code) > 1 and selected_code[1].isdigit() else 3
        if idx_code == 3:
            # Pregunta humanamente intuitiva para colapsar
            prompt = (
                f"Tu dimensión {dim} está en estado Neutral.\n"
                "¿Cómo la sientes ahora?\n"
                "  0. Receptiv(a/o), reflexiv(a/o), tranquila (Yin)\n"
                "  1. Activ(a/o), expresiv(a/o), enérgica (Yang)\n"
                "Selecciona 0 o 1: "
            )
            collapse = input(prompt).strip()
            while collapse not in ("0", "1"):
                print("⚠️ Selección inválida. Ingresa 0 o 1.")
                collapse = input(prompt).strip()
            bits[dim] = int(collapse)
        else:
            # Mapeo automático para no neutrales: 1,2 → Yin(0); 4,5 → Yang(1)
            bits[dim] = 1 if idx_code > 3 else 0

    # Nota opcional
    note = input("\n¿Quieres añadir una nota para hoy? (opcional): ")
    inputs["note"] = note.strip()
    return inputs, bits


def main():
    states = load_states()
    entry, _ = ask_for_inputs(states)

    print("\n📋 Resumen del día:")
    summarize_vector(entry, states)

    # Colapsar estados neutrales a bits
    bits = collapse_neutral(entry)
    print("\n🧬 Vector colapsado (Yin=0 / Yang=1):")
    for dim, bit in bits.items():
        label = 'Yin (0)' if bit == 0 else 'Yang (1)'
        print(f"  {dim}: {label}")

    # Análisis circumplex
    valence_label, arousal_label, state_global = analyze_circumplex(entry, bits)
    print("\n🌀 Circumplex emocional:")
    print(f"  Valencia: {valence_label}")
    print(f"  Activación: {arousal_label}")
    print(f"  Estado global: {state_global}")

    # Análisis contextual (nuevo)
    context_result = analyze_context(entry)
    print("\n🔎 Análisis contextual:")
    print(context_result)

    save_entry(entry)
    compare_with_previous(entry)


if __name__ == "__main__":
    main()
