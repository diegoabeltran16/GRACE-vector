# utils/storage.py
"""
Módulo `storage` para GRACE-vector

Este módulo gestiona el guardado de las entradas diarias en formato JSON,
creando las carpetas necesarias y nombrando automáticamente los archivos
según la fecha.
"""
import os
import json
from datetime import date

# Carpeta base donde se almacenan los registros diarios
DATA_DIR = os.path.join("data", "registros")


def save_entry(entry: dict) -> None:
    """
    Guarda la entrada diaria de identidad en un archivo JSON.

    Parámetros:
    - entry: diccionario con las claves 'G','R','A','C','E' y opcionalmente 'note'.

    El archivo se crea en: data/registros/YYYY-MM-DD_GRACE.json
    """
    # Asegurar que la carpeta exista
    os.makedirs(DATA_DIR, exist_ok=True)

    # Nombre del archivo con la fecha actual
    today = date.today().isoformat()
    filename = f"{today}_GRACE.json"
    filepath = os.path.join(DATA_DIR, filename)

    # Preparar datos a guardar: incluir fecha y todo el contenido de entry
    data_to_save = {"date": today}
    data_to_save.update(entry)

    # Escritura en JSON legible
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data_to_save, f, ensure_ascii=False, indent=2)

    # Confirmación al usuario
    print(f"\n💾 Entrada guardada en {filepath}")
