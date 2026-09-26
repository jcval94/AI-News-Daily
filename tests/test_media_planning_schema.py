import unittest

from pydantic import ValidationError
from app.agent import EditorialMultimediaPlan, MultimediaPlan


class DocumentaryPlanningSchemaTests(unittest.TestCase):
    def test_exact_roles_require_subject_but_context_and_legacy_remain_readable(self):
        segment = dict(slot_number=1, start_seconds=0, end_seconds=3.5,
                       visual_query='ancient parchment', visual_role='historical_mirror')
        with self.assertRaises(ValidationError):
            EditorialMultimediaPlan.model_validate({'segments': [segment]})
        with self.assertRaises(ValidationError):
            EditorialMultimediaPlan.model_validate({'segments': [{**segment, 'retrieval_subject': ''}]})
        EditorialMultimediaPlan.model_validate({'segments': [{**segment, 'retrieval_subject': 'Platón'}]})
        EditorialMultimediaPlan.model_validate({'segments': [{**segment, 'visual_role': 'context'}]})
        MultimediaPlan.model_validate({'segments': [segment]})


if __name__ == '__main__': unittest.main()
