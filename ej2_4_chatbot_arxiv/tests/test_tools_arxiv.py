import os
import shutil
import tempfile
import unittest
from datetime import datetime
from unittest.mock import MagicMock, patch

from ej2_4_chatbot_arxiv import tools_arxiv
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


class TestSearchPapers(unittest.TestCase):
    """search_papers / extract_info contra un PAPER_DIR temporal y arXiv mockeado."""

    def setUp(self) -> None:
        self.tmp = tempfile.mkdtemp(prefix="papers_test_")
        self._patcher = patch.object(tools_arxiv, "PAPER_DIR", self.tmp)
        self._patcher.start()

    def tearDown(self) -> None:
        self._patcher.stop()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _fake_paper(self, short_id: str = "2401.00001v1") -> MagicMock:
        author = MagicMock()
        author.name = "Ada Lovelace"
        paper = MagicMock()
        paper.get_short_id.return_value = short_id
        paper.title = "Un paper de prueba"
        paper.authors = [author]
        paper.summary = "Resumen del paper."
        paper.pdf_url = "http://arxiv.org/pdf/2401.00001v1"
        paper.published = datetime(2024, 1, 2)
        paper.primary_category = "cs.AI"
        return paper

    def _patch_arxiv(self, papers: list) -> tuple:
        fake_client = MagicMock()
        fake_client.results.return_value = papers
        return (
            patch.object(tools_arxiv.arxiv, "Client", return_value=fake_client),
            patch.object(tools_arxiv.arxiv, "Search", return_value=MagicMock()),
        )

    def test_search_papers_guarda_indice_y_devuelve_resultados(self) -> None:
        client_p, search_p = self._patch_arxiv([self._fake_paper()])
        with client_p, search_p:
            result = tools_arxiv.search_papers("Deep Learning", max_results=1)

        self.assertEqual(result["topic"], "Deep Learning")
        self.assertEqual(result["topic_slug"], "deep_learning")
        self.assertEqual(len(result["papers"]), 1)
        paper = result["papers"][0]
        self.assertEqual(paper["id"], "2401.00001v1")
        self.assertEqual(paper["authors"], ["Ada Lovelace"])
        self.assertEqual(paper["published"], "2024-01-02")
        # El índice debe quedar persistido en disco.
        self.assertTrue(os.path.isfile(os.path.join(result["dir"], "papers_info.json")))

    def test_extract_info_encuentra_paper_indexado(self) -> None:
        client_p, search_p = self._patch_arxiv([self._fake_paper("2401.00001v1")])
        with client_p, search_p:
            tools_arxiv.search_papers("Deep Learning", max_results=1)

        found = tools_arxiv.extract_info("2401.00001v1")
        self.assertTrue(found["found"])
        self.assertEqual(found["paper"]["title"], "Un paper de prueba")
        self.assertEqual(found["topic_slug"], "deep_learning")

    def test_extract_info_con_indice_pero_paper_inexistente(self) -> None:
        client_p, search_p = self._patch_arxiv([self._fake_paper("2401.00001v1")])
        with client_p, search_p:
            tools_arxiv.search_papers("Deep Learning", max_results=1)

        res = tools_arxiv.extract_info("9999.99999v1")
        self.assertFalse(res["found"])
        self.assertIn("No se ha encontrado", res["message"])


if __name__ == "__main__":
    unittest.main()
