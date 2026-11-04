from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory

from django.core.management import call_command
from django.test import TestCase

from words.choices import InflectionTypeChoices, PartOfSpeechChoices
from words.models import Word, WordInflection


class UniMorphImportTests(TestCase):
    def setUp(self):
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.source = Path(directory.name) / "deu"
        self.report = Path(directory.name) / "report.tsv"
        self.source.write_text(
            "gehen\tgehen\tV;NFIN\n"
            "gehen\tgegangen\tV.PTCP;PST\n"
            "gehen\tging\tV;IND;SG;1;PST\n"
            "senden\tgesendet\tV.PTCP;PST\n"
            "senden\tgesandt\tV.PTCP;PST\n"
            "Haus\tHäuser\tN;NOM;NEUT;PL\n"
            "Haus\tHäuser\tN;ACC;NEUT;PL\n",
            encoding="utf-8",
        )

    def test_all_scope_previews_then_imports_supported_unique_forms_without_overwriting(self):
        gehen = Word.objects.create(word="gehen", part_of_speech=PartOfSpeechChoices.VERB)
        WordInflection.objects.create(word=gehen, type=InflectionTypeChoices.DE_PARTIZIP_2, value="manual")
        output = StringIO()

        call_command("import_unimorph_de", file=str(self.source), scope="all", report=str(self.report), stdout=output)

        self.assertEqual(Word.objects.count(), 1)
        self.assertEqual(WordInflection.objects.count(), 1)
        self.assertIn("New words: 1; new forms: 2; unchanged: 0; ambiguous: 1; conflicts: 1", output.getvalue())
        report = self.report.read_text(encoding="utf-8")
        self.assertIn("ambiguous\tsenden\tverb\tde_partizip_2", report)
        self.assertIn("conflict\tgehen\tverb\tde_partizip_2\tmanual\tgegangen", report)

        call_command("import_unimorph_de", file=str(self.source), scope="all", apply=True, stdout=StringIO())
        call_command("import_unimorph_de", file=str(self.source), scope="all", apply=True, stdout=StringIO())

        self.assertEqual(set(Word.objects.values_list("word", flat=True)), {"gehen", "Haus"})
        self.assertEqual(
            set(WordInflection.objects.values_list("word__word", "type", "value")),
            {
                ("gehen", InflectionTypeChoices.DE_PARTIZIP_2, "manual"),
                ("gehen", InflectionTypeChoices.DE_PRATERITUM, "ging"),
                ("Haus", InflectionTypeChoices.DE_PLURAL, "Häuser"),
            },
        )

    def test_existing_scope_does_not_create_dictionary_words(self):
        Word.objects.create(word="gehen", part_of_speech=PartOfSpeechChoices.VERB)

        call_command("import_unimorph_de", file=str(self.source), scope="existing", apply=True, stdout=StringIO())

        self.assertEqual(Word.objects.count(), 1)
        self.assertEqual(
            set(WordInflection.objects.values_list("type", "value")),
            {
                (InflectionTypeChoices.DE_PARTIZIP_2, "gegangen"),
                (InflectionTypeChoices.DE_PRATERITUM, "ging"),
            },
        )
