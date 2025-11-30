"""
Ejecutor de tests global del curso.

Permite lanzar todos los tests de los ejercicios con:

    uv run python -m unittest

Cada ejercicio mantiene sus propios tests dentro de su carpeta,
por ejemplo:
- ej1_first_chatbot/tests/
- ej2_4_chatbot_arxiv/tests/

Este módulo solo los agrupa.
"""

import importlib.util
import sys
import unittest
from pathlib import Path


def _load_test_modules_from_dir(
    loader: unittest.TestLoader, suite: unittest.TestSuite, tests_dir: Path
) -> None:
    """
    Carga todos los test_*.py dentro de tests_dir como módulos,
    ajustando sys.path para que las importaciones locales del
    ejercicio funcionen (por ejemplo, `from first_mcp_client import ...`).
    """
    if not tests_dir.is_dir():
        return

    project_root = tests_dir.parent

    # Aseguramos que el proyecto del ejercicio esté en sys.path
    project_root_str = str(project_root.resolve())
    if project_root_str not in sys.path:
        sys.path.insert(0, project_root_str)

    for test_file in tests_dir.glob("test_*.py"):
        module_name = f"{project_root.name.replace('-', '_')}_{test_file.stem}"
        spec = importlib.util.spec_from_file_location(module_name, test_file)
        if spec is None or spec.loader is None:
            continue

        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)  # type: ignore[arg-type]
        suite.addTests(loader.loadTestsFromModule(module))


def load_tests(  # type: ignore[override]
    loader: unittest.TestLoader, tests: unittest.TestSuite, pattern: str | None
) -> unittest.TestSuite:
    """
    Agrupa los tests de todos los ejercicios:

    - ej1_first_chatbot/tests/
    - ej2_4_chatbot_arxiv/tests/
    """
    suite = unittest.TestSuite()
    root = Path(__file__).parent

    _load_test_modules_from_dir(
        loader, suite, root / "ej1_first_chatbot" / "tests"
    )
    _load_test_modules_from_dir(
        loader, suite, root / "ej2_4_chatbot_arxiv" / "tests"
    )
    _load_test_modules_from_dir(
        loader, suite, root / "ej5_6_chatbot_omdb" / "tests"
    )
    _load_test_modules_from_dir(
        loader, suite, root / "ej7_mcp_rag_db" / "tests"
    )
    _load_test_modules_from_dir(
        loader, suite, root / "ej8_sakila_streaming" / "tests"
    )
    _load_test_modules_from_dir(
        loader, suite, root / "ej9_orquestador" / "tests"
    )

    return suite
