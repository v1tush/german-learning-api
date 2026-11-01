"""Import supported German word forms from the pinned UniMorph dataset."""

import csv
import hashlib
import unicodedata
from collections import defaultdict
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from words.choices import InflectionTypeChoices, LanguageChoices, PartOfSpeechChoices
from words.models import Word, WordInflection

SOURCE_REVISION = "d226d2112d3490d8f04ece10d4538123d4297a39"
SOURCE_URL = f"https://raw.githubusercontent.com/unimorph/deu/{SOURCE_REVISION}/deu"
SOURCE_SHA256 = "8bc98487e3caf86188e2c072ebf2dc734f2ca35afef016bb399eb5a43e69d7c0"
GERMAN_TYPES = (
    InflectionTypeChoices.DE_PARTIZIP_2,
    InflectionTypeChoices.DE_PRATERITUM,
    InflectionTypeChoices.DE_PLURAL,
)


def normalize(value: str) -> str:
    return unicodedata.normalize("NFC", value.strip())


def form_type(features: str) -> tuple[str, str] | None:
    if features == "V.PTCP;PST":
        return PartOfSpeechChoices.VERB, InflectionTypeChoices.DE_PARTIZIP_2
    if features == "V;IND;SG;1;PST":
        return PartOfSpeechChoices.VERB, InflectionTypeChoices.DE_PRATERITUM
    tags = features.split(";")
    if len(tags) == 4 and tags[0] == "N" and tags[1] == "NOM" and tags[3] == "PL":
        return PartOfSpeechChoices.NOUN, InflectionTypeChoices.DE_PLURAL
    return None


def parse_forms(lines) -> tuple[dict[tuple[str, str, str], str], dict[tuple[str, str, str], list[str]]]:
    candidates = defaultdict(set)
    for line_number, line in enumerate(lines, start=1):
        parts = line.rstrip("\r\n").split("\t")
        if len(parts) != 3:
            raise CommandError(f"Malformed UniMorph row at line {line_number}")
        lemma, value, features = parts
        matched = form_type(features)
        if matched is None:
            continue
        lemma, value = normalize(lemma), normalize(value)
        if not lemma or not value or len(lemma) > 255 or len(value) > 255:
            raise CommandError(f"Invalid supported form at line {line_number}")
        part_of_speech, inflection_type = matched
        candidates[(lemma, part_of_speech, inflection_type)].add(value)

    unique = {}
    ambiguous = {}
    for key, values in candidates.items():
        if len(values) == 1:
            unique[key] = next(iter(values))
        else:
            ambiguous[key] = sorted(values)
    return unique, ambiguous


def load_source(source_file: str | None) -> str:
    if source_file:
        try:
            return Path(source_file).read_text(encoding="utf-8-sig")
        except (OSError, UnicodeError) as error:
            raise CommandError(f"Could not read UniMorph file: {error}") from error

    try:
        with urlopen(SOURCE_URL, timeout=60) as response:
            content = response.read()
    except (OSError, URLError) as error:
        raise CommandError(f"Could not download UniMorph: {error}") from error
    if hashlib.sha256(content).hexdigest() != SOURCE_SHA256:
        raise CommandError("UniMorph download checksum mismatch")
    try:
        return content.decode("utf-8-sig")
    except UnicodeError as error:
        raise CommandError("UniMorph download is not UTF-8") from error


def database_words() -> dict[tuple[str, str], Word]:
    return {
        (word.word, word.part_of_speech): word
        for word in Word.objects.filter(
            language=LanguageChoices.GERMAN,
            part_of_speech__in=(PartOfSpeechChoices.NOUN, PartOfSpeechChoices.VERB),
        )
    }


def database_forms() -> dict[tuple[int, str], str]:
    return {
        (inflection.word_id, inflection.type): inflection.value
        for inflection in WordInflection.objects.filter(word__language=LanguageChoices.GERMAN, type__in=GERMAN_TYPES)
    }


class Command(BaseCommand):
    help = "Preview or import German Partizip II, Präteritum and plural forms from UniMorph/deu."

    def add_arguments(self, parser):
        parser.add_argument("--file", help="Local UniMorph/deu file; otherwise download the pinned revision")
        parser.add_argument("--scope", choices=("existing", "all"), required=True)
        parser.add_argument("--apply", action="store_true", help="Write changes; otherwise only preview")
        parser.add_argument("--report", help="Write skipped ambiguous and conflicting forms to a UTF-8 TSV file")

    def handle(self, *args, **options):
        unique, ambiguous = parse_forms(load_source(options["file"]).splitlines())
        words = database_words()
        if options["scope"] == "existing":
            unique = {key: value for key, value in unique.items() if key[:2] in words}
            ambiguous = {key: values for key, values in ambiguous.items() if key[:2] in words}

        existing = database_forms()
        missing_words = {key[:2] for key in unique if key[:2] not in words}
        to_create = []
        conflicts = []
        unchanged = 0
        for key, value in sorted(unique.items()):
            word = words.get(key[:2])
            stored = existing.get((word.pk, key[2])) if word else None
            if stored is None:
                to_create.append((key, value))
            elif normalize(stored) == value:
                unchanged += 1
            else:
                conflicts.append((key, stored, value))

        self.stdout.write(f"UniMorph revision: {SOURCE_REVISION}")
        self.stdout.write(f"Scope: {options['scope']}; apply: {options['apply']}")
        self.stdout.write(
            f"New words: {len(missing_words)}; new forms: {len(to_create)}; "
            f"unchanged: {unchanged}; ambiguous: {len(ambiguous)}; conflicts: {len(conflicts)}"
        )
        if options["report"]:
            self.write_report(options["report"], ambiguous, conflicts)

        if not options["apply"]:
            return

        with transaction.atomic():
            if missing_words:
                Word.objects.bulk_create(
                    [
                        Word(word=lemma, language=LanguageChoices.GERMAN, part_of_speech=part_of_speech)
                        for lemma, part_of_speech in sorted(missing_words)
                    ],
                    batch_size=1000,
                    ignore_conflicts=True,
                )
                words = database_words()

            # Recheck before writing: existing manual forms always win.
            existing = database_forms()
            WordInflection.objects.bulk_create(
                [
                    WordInflection(word=words[key[:2]], type=key[2], value=value)
                    for key, value in to_create
                    if (words[key[:2]].pk, key[2]) not in existing
                ],
                batch_size=1000,
                ignore_conflicts=True,
            )
        self.stdout.write("Import complete")

    @staticmethod
    def write_report(path: str, ambiguous, conflicts):
        try:
            with Path(path).open("w", encoding="utf-8", newline="") as output:
                writer = csv.writer(output, delimiter="\t")
                writer.writerow(("reason", "lemma", "part_of_speech", "type", "existing", "source_values"))
                for (lemma, part_of_speech, inflection_type), values in sorted(ambiguous.items()):
                    writer.writerow(("ambiguous", lemma, part_of_speech, inflection_type, "", " | ".join(values)))
                for (lemma, part_of_speech, inflection_type), stored, value in conflicts:
                    writer.writerow(("conflict", lemma, part_of_speech, inflection_type, stored, value))
        except OSError as error:
            raise CommandError(f"Could not write import report: {error}") from error
