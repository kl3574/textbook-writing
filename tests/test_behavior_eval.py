from pathlib import Path
import json
import sys
import tempfile
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from behavior_eval import prepare,collect
from release_contract import affected_objects,digest

class BehaviorToolTests(unittest.TestCase):
    def test_prepare_and_missing_runs(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t)
            for name in ('old','new'):
                (root/name).mkdir();(root/name/'SKILL.md').write_text(name)
            cases=root/'cases.json';cases.write_text(json.dumps({'cases':[{'id':'fixture','prompt':'synthetic test; not a model run'}]}))
            result=prepare(cases,root/'old',root/'new',root/'work',7)
            self.assertEqual(result['packet_count'],3)
            report=collect(root/'work')
            self.assertEqual(report['status'],'INCOMPLETE')
            self.assertEqual([x['status'] for x in report['runs']],['NOT_RUN']*3)
            self.assertEqual(len(list((root/'work'/'fixture').glob('*/skill/SKILL.md'))),2)

    def test_fabricated_receipt_without_logs_rejected(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t)
            (root/'private').mkdir();(root/'A').mkdir()
            (root/'private'/'mapping.json').write_text(json.dumps({'runs':[{'case_id':'fixture','label':'A','condition':'new','path':'A','prompt_sha256':'fixed'}]}))
            (root/'A'/'receipt.json').write_text(json.dumps({'schema':'TextbookBehaviorRun/v1','prompt_sha256':'fixed','status':'PASS'}))
            self.assertEqual(collect(root)['runs'][0]['status'],'INVALID_EVIDENCE')

    def test_source_change_invalidates_users(self):
        before={'sources':[{'id':'paper','version':'1'}],'objects':[{'id':'thm','source_ids':['paper']},{'id':'example','depends_on':['thm']}]}
        after={'sources':[{'id':'paper','version':'2'}],'objects':before['objects']}
        result=affected_objects(before,after)
        self.assertEqual(result['changed_sources'],['paper'])
        self.assertEqual(result['requires_review'],['example','thm'])

if __name__=='__main__':unittest.main()
