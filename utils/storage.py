# utils/storage.py
"""
Módulo `storage` para GRACE-vector

Este módulo gestiona el guardado de las entradas diarias en formato JSONL,
creando las carpetas necesarias y agregando cada registro como una nueva línea
en un archivo único `registro.jsonl`.
"""
import os
import json

# Carpeta base donde se almacenan los registros diarios
DATA_DIR = os.path.join("data", "registros")
# Archivo JSONL donde se agregan las entradas
JSONL_FILE = "registro.jsonl"


def save_entry(entry: dict) -> None:
    """
    Guarda la entrada diaria de identidad en formato JSONL.

    Parámetros:
    - entry: diccionario con las claves 'G','R','A','C','E' y opcionalmente 'note'.

    El archivo se crea (si no existe) y luego se agrega una línea con la entrada:
    data/registros/registro.jsonl
    """
    # Asegurar que la carpeta exista
    os.makedirs(DATA_DIR, exist_ok=True)

    # Ruta completa al archivo JSONL
    filepath = os.path.join(DATA_DIR, JSONL_FILE)

    # Preparar datos a guardar: incluir fecha y todo el contenido de entry
    # No usamos date.today() directamente para permitir probar con otras fechas si se necesita
    from datetime import date
    record = {"date": date.today().isoformat()}
    record.update(entry)

    # Agregar como nueva línea JSON al archivo
    with open(filepath, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False))
        f.write("\n")

    # Confirmación al usuario
    print(f"\n💾 Entrada agregada en {filepath}")
