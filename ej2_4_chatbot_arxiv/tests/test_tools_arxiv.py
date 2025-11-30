import os
import shutil
import unittest

from ej2_4_chatbot_arxiv.tools_arxiv import PAPER_DIR, _slugify_topic, extract_info


class TestToolsArxiv(unittest.TestCase):
    def setUp(self) -> None:
        # Dejamos el directorio de papers en un estado limpio
        if os.path.isdir(PAPER_DIR):
            shutil.rmtree(PAPER_DIR)

    def test_slugify_topic_simplifica_bien(self) -> None:
        # Comprobamos que genera un slug estable y en minúsculas.
        self.assertEqual(_slugify_topic("  Deep Learning!!! "), "deep_learning_")
        self.assertEqual(_slugify_topic(""), "topic")

    def test_extract_info_sin_indice_devuelve_mensaje_amigable(self) -> None:
        result = extract_info("1234.5678v1")
        self.assertFalse(result["found"])
        self.assertIn("No hay ningún índice local", result["message"])


if __name__ == "__main__":
    unittest.main()
