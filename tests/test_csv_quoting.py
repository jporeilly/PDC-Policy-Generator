"""Dictionary CSVs must survive the values that are actually in the estate.

Field-caught 2026-08-21 deploying the Arizona contract. The emitter built a
one-column CSV by joining values with newlines, and `water_systems`
.conservation_focus holds "Expanding metro area, new customer acquisition,
infrastructure growth" — three fields on a one-field header. PDC's importer
threw CSVFieldNumDifferentException and abandoned the rest of the zip: 13
dictionaries queued before the bad row landed, the 18 after it did not, and
Deploy reported COMPLETED over the top of it.
"""
import csv
import io

from policy_generator.author import _csv, _index_lines


def parse(text):
    return list(csv.reader(io.StringIO(text)))


class TestValuesWithSeparators:
    def test_a_comma_stays_one_field(self):
        rows = parse(_csv([("Term",), ("Expanding metro area, new customer acquisition",)]))
        assert rows[1] == ["Expanding metro area, new customer acquisition"], \
            "a comma in a value split it into extra columns - the import-killing bug"

    def test_every_row_has_the_same_field_count(self):
        """The importer's actual complaint: 1 field on the header, 3 on row 2."""
        values = ["Groundwater", "Wells + Local Surface Water",
                  "Rural agriculture, small system management, reliability focus",
                  'He said "mixed"', "Pinal"]
        rows = parse(_csv([("Term",)] + [(v,) for v in values]))
        widths = {len(r) for r in rows}
        assert widths == {1}, f"ragged CSV: row widths {widths}"
        assert [r[0] for r in rows[1:]] == values, "a value did not survive the round trip"

    def test_a_quote_is_escaped_not_dropped(self):
        rows = parse(_csv([("Term",), ('12" main',)]))
        assert rows[1] == ['12" main']

    def test_a_newline_inside_a_value_stays_inside_it(self):
        rows = parse(_csv([("Term",), ("line one\nline two",)]))
        assert len(rows) == 2 and rows[1] == ["line one\nline two"]


class TestIndexManifest:
    def test_a_term_name_with_a_comma_does_not_shift_the_columns(self):
        art = {"patterns": [{"rule": {"name": "Arizona Flow"}, "filename": "f.json",
                             "term": "Flow, measured", "term_id": "t-1"}],
               "dictionaries": []}
        rows = parse("\n".join(_index_lines(art)))
        assert rows[0] == ["kind", "name", "file", "term", "term_id"]
        assert len(rows[1]) == 5, f"manifest row split into {len(rows[1])} columns"
        assert rows[1][3] == "Flow, measured" and rows[1][4] == "t-1"
