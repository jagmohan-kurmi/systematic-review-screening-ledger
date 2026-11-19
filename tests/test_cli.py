import json,tempfile,unittest
from pathlib import Path
from systematic_review_screening_ledger.cli import import_into,conflicts,summary,parse_records,main
class ScreeningTests(unittest.TestCase):
    def test_dedup_preserves_originals(self):
        l={"records":[],"votes":[]}; a={"title":"A Study!","doi":"10.1234/ABC","source_text":"original1","source_file":"a","fields":{}}
        b={"title":"different title","doi":"https://doi.org/10.1234/abc","source_text":"original2","source_file":"b","fields":{}}
        import_into(l,[a,b]); self.assertEqual(len(l["records"]),1); self.assertEqual(len(l["records"][0]["source_records"]),2); self.assertEqual(l["records"][0]["source_records"][0]["source_text"],"original1")
    def test_conflict_requires_two_distinct_votes(self):
        l={"records":[{"record_id":"x","source_records":[]}],"votes":[{"record_id":"x","reviewer":"A","decision":"include"}]}
        self.assertEqual(conflicts(l),[]); l["votes"].append({"record_id":"x","reviewer":"B","decision":"exclude","reason":"wrong population"}); self.assertEqual(conflicts(l),["x"]); self.assertEqual(summary(l)["conflicts"],1)
    def test_ris_and_invalid_vote(self):
        with tempfile.TemporaryDirectory() as td:
            td=Path(td); ris=td/"in.ris"; ris.write_text("TY  - JOUR\nTI  - A title\nDO  - 10.1/xyz\nER  -\n",encoding="utf-8"); self.assertEqual(parse_records(ris)[0]["title"],"A title")
            ledger=td/"l.json"; ledger.write_text('{"records":[],"votes":[]}',encoding="utf-8"); vote=td/"v.json"; vote.write_text('{"record_id":"none","reviewer":"R","decision":"include"}',encoding="utf-8"); self.assertEqual(main(["vote",str(vote),"--ledger",str(ledger)]),2)
    def test_csv_export_retains_both_reasons_and_counts(self):
        with tempfile.TemporaryDirectory() as td:
            td=Path(td); ledger=td/"ledger.json"; out=td/"report.csv"
            row={"record_id":"x","fields":{"title":"Study"},"source_records":[{"source_text":"original"}]}
            votes=[{"record_id":"x","reviewer":"A","decision":"include","reason":"supports scope"},{"record_id":"x","reviewer":"B","decision":"exclude","reason":"wrong design"}]
            ledger.write_text(json.dumps({"records":[row],"votes":votes}),encoding="utf-8")
            self.assertEqual(main(["export","--ledger",str(ledger),"--format","csv","--output",str(out)]),0)
            content=out.read_text(encoding="utf-8")
            self.assertIn("supports scope",content); self.assertIn("wrong design",content); self.assertIn("conflict_count",content); self.assertIn(",1,",content)
if __name__=="__main__":unittest.main()
