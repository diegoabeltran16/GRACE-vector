# utils/model_collapse.py

"""
Módulo `model_collapse` para GRACE-vector

Este módulo gestiona el "colapso" de estados Neutral en el vector GRACE,
permitiendo al usuario decidir si neutral es Yin (0) o Yang (1) y mapea
los estados no neutrales automáticamente a su bit correspondiente.
Es un módulo de utilidades que gestiona el colapso de estados 'Neutral' en GRACE hacia un bit Yin (0) o Yang (1).
¿Por qué es importante? - Porque en física cuántica y en filosofía oriental, un estado neutral o potencial “colapsa” en un 
valor observable solo cuando se toma una decisión. Aquí aplicamos esta metáfora al vector de identidad.
"""

def collapse_neutral(entry: dict) -> dict:
    """
    Convierte cada dimensión del vector GRACE en un bit Yin (0) o Yang (1).

    - Para estados "Neutral" (código terminando en '3'), solicita al usuario
      elegir Yin (0) o Yang (1).
    - Para otros estados, mapea automáticamente: códigos 1 y 2 → Yin (0); 4 y 5 → Yang (1).

    Parámetros:
    - entry: dict con claves 'G','R','A','C','E' (códigos tipo 'G3', 'A5', etc.)

    Retorna:
    - dict: {dimensión: bit} donde bit es 0 o 1.
    """
    bits = {}
    for dim, code in entry.items():
        # Omitir la nota si existe
        if dim == 'note':
            continue
        # Extraer índice (1-5) del código, p.ej. 'G3' -> 3
        try:
            idx = int(code[1])
        except (IndexError, ValueError):
            # En caso de código inválido, asumir Yin
            idx = 1

        # Estado Neutral (índice 3) → colapso por input
        if idx == 3:
            prompt = (
                f"Tu dimensión {dim} está en estado Neutral. "
                "Selecciona 0 para Yin o 1 para Yang: "
            )
            choice = input(prompt).strip()
            while choice not in ("0", "1"):
                print("⚠️ Selección inválida. Ingresa 0 para Yin o 1 para Yang.")
                choice = input(prompt).strip()
            bit = int(choice)
        else:
            # Mapeo automático para no neutrales
            bit = 1 if idx > 3 else 0

        bits[dim] = bit
    return bits


def map_state_to_bit(dim: str, code: str) -> int:
    """
    Alias de collapse_neutral para mapeo automático de un solo estado.
    Útil si solo quieres conocer el bit de un código sin colapso de input.

    Parámetros:
    - dim: letra de la dimensión ('G','R','A','C','E')
    - code: código de estado ('G1'...'E5')

    Retorna:
    - bit: 0 o 1 según el índice del código
    """
    try:
        idx = int(code[1])
    except (IndexError, ValueError):
        return 0
    return 1 if idx > 3 else 0
