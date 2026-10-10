import importlib.util
import json
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
spec = importlib.util.spec_from_file_location('evaluator', ROOT / 'scripts/evaluate_reviews.py')
evaluator = importlib.util.module_from_spec(spec)
spec.loader.exec_module(evaluator)


class EvaluationTests(unittest.TestCase):
    def setUp(self):
        self.scenarios = json.loads((ROOT / 'evals/scenarios.json').read_text())['scenarios']
        self.review = json.loads((ROOT / 'evals/example-good-review.json').read_text())

    def test_good_review_and_false_positive(self):
        self.assertTrue(evaluator.evaluate(self.scenarios[0], self.review)['passed'])
        self.review['findings'] = [self.finding('Unnecessary rename', 'INFO')]
        report = evaluator.evaluate(self.scenarios[0], self.review)
        self.assertFalse(report['passed'])
        self.assertEqual(report['false_positive_finding_indexes'], [0])

    @staticmethod
    def finding(title, severity='BLOCKING'):
        return {'title': title, 'severity': severity, 'requirement': 'Project requirements',
                'implementation': title, 'why_it_matters': 'Required behavior missing', 'file': ''}

    def test_detected_and_missed_issues(self):
        self.review['verdict'] = 'NEEDS_CHANGES'
        self.review['findings'] = [self.finding('Missing unit tests')]
        report = evaluator.evaluate(self.scenarios[2], self.review)
        self.assertEqual(report['detected_issues'], ['missing-unit-tests'])
        self.assertEqual(report['missed_issues'], ['missing-integration-tests'])
        self.assertEqual(report['false_positive_finding_indexes'], [])

    def test_combined_finding_can_cover_multiple_issues(self):
        self.review['verdict'] = 'NEEDS_CHANGES'
        self.review['findings'] = [self.finding('Missing unit and integration tests')]
        self.assertTrue(evaluator.evaluate(self.scenarios[2], self.review)['passed'])

    def test_all_bad_scenarios_have_expected_findings(self):
        for scenario in self.scenarios[1:]:
            review = json.loads(json.dumps(self.review))
            review['verdict'] = 'NEEDS_CHANGES'
            review['findings'] = [self.finding(' '.join(group[0] for group in issue['term_groups']))
                                  for issue in scenario['expected_findings']]
            if scenario['gradle_exit_code']:
                review['build_tests'].update(exit_code=1, build_result='FAIL', test_result='NOT_RUN')
            with self.subTest(scenario=scenario['id']):
                self.assertTrue(evaluator.evaluate(scenario, review)['passed'])

    def test_invalid_review_is_rejected(self):
        with self.assertRaises(ValueError):
            evaluator.evaluate(self.scenarios[0], {})
