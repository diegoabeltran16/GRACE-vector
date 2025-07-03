"""
Pruebas unitarias consolidadas para diversos módulos de utils de GRACE-vector.
"""
import datetime
import pytest
import json
import os
import sys
sys.path.append(os.path.abspath("."))  # Asegura path raíz

# =========================
# utils/contextual_analysis.py
# =========================

import utils.contextual_analysis as ca
from utils.contextual_analysis import analyze_context

class TestContextualAnalysis:
    def test_analyze_context_with_note(self, monkeypatch):
        class FakeDate:
            @classmethod
            def today(cls): return datetime.date(2025, 6, 13)
            def isoformat(self): return "2025-06-13"
        monkeypatch.setattr(ca, 'date', FakeDate)
        monkeypatch.setattr(ca, 'plutchik_emotion', lambda entry: 'Alegría')
        entry = {
            'G': 'G1', 'R': 'R2', 'A': 'A3', 'C': 'C4', 'E': 'E5',
            'note': 'Prueba de nota'
        }
        result = analyze_context(entry)
        lines = result.split('\n')
        assert lines[0] == 'Fecha: 2025-06-13'
        assert '• Género: G1' in lines
        assert '• Nota: Prueba de nota' in lines
        assert '• Emoción Plutchik dominante: Alegría' in lines

    def test_analyze_context_without_note(self, monkeypatch):
        class FakeDate:
            @classmethod
            def today(cls): return datetime.date(2025, 6, 14)
            def isoformat(self): return "2025-06-14"
        monkeypatch.setattr(ca, 'date', FakeDate)
        monkeypatch.setattr(ca, 'plutchik_emotion', lambda entry: 'Miedo')
        entry = {'G': 'G3', 'R': 'R3', 'A': 'A4', 'C': 'C2', 'E': 'E1'}
        result = analyze_context(entry)
        lines = result.split('\n')
        assert lines[0] == 'Fecha: 2025-06-14'
        assert '• Nota:' not in result
        assert '• Emoción Plutchik dominante: Miedo' in lines

# =========================
# utils/model_plutchik.py
# =========================

from utils.model_plutchik import analyze_plutchik

class TestModelPlutchik:
    def test_analyze_plutchik_detects_emotions(self, monkeypatch):
        fake_map = {
            "A1_E1": "Tristeza",
            "C5_R5": "Confianza"
        }
        monkeypatch.setattr("utils.model_plutchik.load_mappings", lambda: fake_map)
        entry = {"A": "A1", "E": "E1", "C": "C5", "R": "R5", "G": "G3"}
        emotions = analyze_plutchik(entry)
        assert "Tristeza" in emotions
        assert "Confianza" in emotions

# =========================
# utils/model_collapse.py
# =========================

import utils.model_collapse as mc
from utils.model_collapse import collapse_neutral, map_state_to_bit

class TestModelCollapse:
    def test_collapse_neutral_input(self, monkeypatch):
        # Simula input del usuario para Neutral: primero 0 (Yin), luego 1 (Yang)
        entry = {'G': 'G3', 'R': 'R1', 'A': 'A3', 'C': 'C4', 'E': 'E2'}
        inputs = iter(['0', '1'])  # G3->0, A3->1
        monkeypatch.setattr('builtins.input', lambda _: next(inputs))
        bits = collapse_neutral(entry)
        assert bits['G'] == 0  # Neutral colapsado a Yin
        assert bits['A'] == 1  # Neutral colapsado a Yang
        assert bits['R'] == 0  # No-neutral (1) → Yin
        assert bits['C'] == 1  # No-neutral (4) → Yang
        assert bits['E'] == 0  # No-neutral (2) → Yin

    def test_collapse_neutral_non_neutral(self):
        entry = {'G': 'G1', 'R': 'R2', 'A': 'A4', 'C': 'C5', 'E': 'E1'}
        # No input necesario, todo automático
        bits = collapse_neutral(entry)
        assert bits == {'G': 0, 'R': 0, 'A': 1, 'C': 1, 'E': 0}

    def test_collapse_neutral_robustness(self, monkeypatch):
        # Código mal formado y estado inexistente
        entry = {'G': 'Gx', 'R': '', 'A': 'A3', 'C': 'C4', 'E': 'E2'}
        inputs = iter(['1'])  # Solo A3 es neutral
        monkeypatch.setattr('builtins.input', lambda _: next(inputs))
        bits = collapse_neutral(entry)
        # Gx y '' deben mapear a Yin (por fallback)
        assert bits['G'] == 0
        assert bits['R'] == 0
        assert bits['A'] == 1  # Neutral colapsado a Yang
        assert bits['C'] == 1
        assert bits['E'] == 0

    def test_map_state_to_bit(self):
        assert map_state_to_bit('G', 'G1') == 0
        assert map_state_to_bit('G', 'G4') == 1
        assert map_state_to_bit('G', 'G3') == 0
        assert map_state_to_bit('G', 'bad') == 0

# =========================
# utils/model_circumplex.py
# =========================

import utils.model_circumplex as mcp
from utils.model_circumplex import (
    load_circumplex_mapping,
    apply_modulation,
    analyze_circumplex
)

class TestModelCircumplex:
    def test_load_circumplex_mapping(self, monkeypatch, tmp_path):
        # Crea un mapping temporal
        fake_map = {"G1": {"valence": 1, "arousal": 0.5}}
        mapping_path = tmp_path / "circumplex_map.json"
        mapping_path.write_text(json.dumps(fake_map), encoding="utf-8")
        monkeypatch.setattr(mcp, "MAPPING_PATH", str(mapping_path))
        loaded = load_circumplex_mapping()
        assert loaded == fake_map

    def test_apply_modulation(self):
        # Yin (0) → factor 0.8, Yang (1) → factor 1.2
        assert apply_modulation(1.0, 0.5, 0) == (0.8, 0.4)
        assert apply_modulation(1.0, 0.5, 1) == (1.2, 0.6)

    def test_analyze_circumplex_complete(self, monkeypatch):
        # Simula mapping y prueba etiquetas y estado global
        fake_map = {
            "G1": {"valence": 1, "arousal": 0.6},
            "R4": {"valence": -1, "arousal": 0.7},
            "A2": {"valence": 0.5, "arousal": 0.3},
            "C5": {"valence": 0.5, "arousal": 0.9},
            "E1": {"valence": -0.5, "arousal": 0.2}
        }
        monkeypatch.setattr(mcp, "load_circumplex_mapping", lambda: fake_map)
        entry = {"G": "G1", "R": "R4", "A": "A2", "C": "C5", "E": "E1"}
        bits = {"G": 1, "R": 0, "A": 0, "C": 1, "E": 0}
        valence_label, arousal_label, state_global = analyze_circumplex(entry, bits)
        assert valence_label in ("Positiva", "Negativa")
        assert arousal_label in ("Alta", "Baja")
        assert isinstance(state_global, str)

    def test_analyze_circumplex_fallback(self, monkeypatch):
        # Si el código no existe, usa valence=0.0, arousal=0.5
        monkeypatch.setattr(mcp, "load_circumplex_mapping", lambda: {})
        entry = {"G": "G9", "R": "R9", "A": "A9", "C": "C9", "E": "E9"}
        bits = {"G": 0, "R": 1, "A": 0, "C": 1, "E": 0}
        valence_label, arousal_label, state_global = analyze_circumplex(entry, bits)
        assert valence_label in ("Positiva", "Negativa")
        assert arousal_label in ("Alta", "Baja")
        assert isinstance(state_global, str)
