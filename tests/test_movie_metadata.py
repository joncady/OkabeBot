import tempfile
import unittest
from unittest.mock import patch
from okabebot.movie_metadata import MovieMetadata


def claim(q):
    return dict(mainsnak=dict(datavalue=dict(value=dict(id=q))))


class MovieMetadataTests(unittest.TestCase):
    def resolver(self, folder, ambiguous=False, wrong_type=False):
        def fetch(url):
            if "wbsearchentities" in url:
                return dict(search=[dict(id="Q1")] + ([dict(id="Q2")] if ambiguous else []))
            if "EntityData/" in url:
                qid = url.split("/")[-1].split(".")[0]
                return dict(
                    entities={
                        qid: dict(
                            labels=dict(en=dict(value="Example Movie")),
                            claims=dict(P31=[claim("QTYPE")], P136=[claim("QGENRE")]),
                        )
                    }
                )
            if "wbgetentities" in url:
                return dict(
                    entities=dict(
                        QTYPE=dict(
                            labels=dict(en=dict(value="human" if wrong_type else "feature film"))
                        ),
                        QGENRE=dict(labels=dict(en=dict(value="comedy film"))),
                    )
                )
            raise AssertionError(url)

        return MovieMetadata(folder, fetch=fetch)

    def test_exact_movie_verified_type_and_genre(self):
        with tempfile.TemporaryDirectory() as folder:
            m = self.resolver(folder)
            try:
                result = m.lookup(dict(title="Example Movie"))
                self.assertEqual(result["context"]["genres"], ["comedy"])
                self.assertEqual(result["source"], "wikidata")
                self.assertIsNone(m.lookup(dict(title="Different title")))
            finally:
                m.close()

    def test_remakes_and_wrong_entity_types_abstain(self):
        for ambiguous, wrong in [(True, False), (False, True)]:
            with tempfile.TemporaryDirectory() as folder:
                m = self.resolver(folder, ambiguous, wrong)
                try:
                    self.assertIsNone(m.lookup(dict(title="Example Movie")))
                finally:
                    m.close()

    def test_disk_cache_and_provider_failure_do_not_block_or_leak_to_new_title(self):
        with tempfile.TemporaryDirectory() as folder:
            m = self.resolver(folder)
            try:
                v = dict(app="Max", title="Example Movie")
                m.get(v, {})
                m.future.result(timeout=3)
                self.assertEqual(m.get(v, {})["context"]["genres"], ["comedy"])
                m.results.clear()
                m.fetch = lambda _: self.fail("Cache should avoid network")
                self.assertEqual(m.get(v, {})["source"], "wikidata")
                with patch.object(m, "lookup", side_effect=OSError("offline")):
                    m._run("unavailable", v)
                self.assertIsNone(m.results["unavailable"][0])
                self.assertEqual(m.get(dict(app="YouTube", title="Example Movie"), {}), {})
            finally:
                m.close()
