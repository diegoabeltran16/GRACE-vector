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
