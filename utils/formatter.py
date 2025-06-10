# utils/formatter.py
"""
Módulo `formatter` para GRACE-vector

Este módulo contiene funciones que genera un resumen textual del vector de identidad diario,
mostrando de forma clara y pedagógica cada dimensión sin emitir juicios ni sugerencias.
"""

# Etiquetas legibles de cada dimensión para el usuario
DIMENSION_LABELS = {
    "G": "Género",
    "R": "Relaciones",
    "A": "Aprendizaje cognitivo",
    "C": "Cuerpo",
    "E": "Experiencia personal"
}


def summarize_vector(entry: dict, states: dict) -> None:
    """
    Imprime en consola un resumen del estado diario de identidad basado en el vector GRACE.

    Parámetros:
    - entry: diccionario con las claves 'G','R','A','C','E' y opcionalmente 'note'.
             Cada clave de dimensión (ej. 'G') tiene como valor un código (ej. 'G3').
    - states: diccionario que asocia cada dimensión a un mapping de códigos a etiquetas.

    El formato de salida es:
      - G (Género): G3 – Conectada
      - R (Relaciones): R2 – Tensa
      ...
    Opcionalmente, muestra la nota si existe.
    """
    print()
    print("📋 Resumen simbólico de tu vector de identidad:")
    # Recorrer cada dimensión en orden GRACE
    for dim in ["G", "R", "A", "C", "E"]:
        code = entry.get(dim)
        # Obtener etiqueta larga desde el archivo de estados
        label = states.get(dim, {}).get(code, "")
        # Nombre legible de la dimensión
        dim_label = DIMENSION_LABELS.get(dim, dim)
        # Formato pedagógico y claro
        print(f"- {dim} ({dim_label}): {code} – {label}")

    # Si el usuario añadió una nota, mostrarla abajo
    note = entry.get("note", "").strip()
    if note:
        print()
        print(f"💬 Nota del día: {note}")
