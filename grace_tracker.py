import json
import os
from datetime import date

from utils.formatter import summarize_vector
from utils.storage import save_entry

CONFIG_PATH = "config/estados_grace.json"


def load_states():
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def ask_for_inputs(states):
    inputs = {}
    print("\n🧭 Check-in diario de identidad - GRACE\n")
    for dim in ["G", "R", "A", "C", "E"]:
        print(f"{dim} - Estados disponibles:")
        for code, label in states[dim].items():
            print(f"  {code}: {label}")
        choice = input(f"Selecciona tu estado para {dim}: ").strip().upper()
        while choice not in states[dim]:
            print("⚠️ Código inválido. Intenta nuevamente.")
            choice = input(f"Selecciona tu estado para {dim}: ").strip().upper()
        inputs[dim] = choice
    note = input("\n¿Quieres añadir una nota para hoy? (opcional): ")
    inputs["note"] = note.strip()
    return inputs


def main():
    states = load_states()
    entry = ask_for_inputs(states)
    print("\n📋 Resumen del día:")
    summarize_vector(entry, states)
    save_entry(entry)


if __name__ == "__main__":
    main()
