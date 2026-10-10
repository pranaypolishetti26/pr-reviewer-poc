"""Offline, deterministic review scoring. No credentials, model calls, or publishing."""

import argparse
import json
from pathlib import Path
import re
import sys

from publish_pr_review import validate_review


def evaluate(scenario, review):
    if not isinstance(review, dict) or not isinstance(review.get('head_sha'), str) or not re.fullmatch(r'[0-9a-f]{40}', review['head_sha']):
        raise ValueError('Invalid review commit SHA')
    validate_review(review, scenario['gradle_exit_code'], review.get('head_sha'))
    findings = review['findings']
    expected = scenario['expected_findings']
    # Each term group needs one matching phrase. A finding may cover several issues.
    matches = []
    for issue in expected:
        indexes = []
        for index, finding in enumerate(findings):
            body = ' '.join(finding[key] for key in
                            ('title', 'requirement', 'implementation', 'why_it_matters')).casefold()
            if finding['severity'] == issue['severity'] and all(
                any(term.casefold() in body for term in group) for group in issue['term_groups']
            ):
                indexes.append(index)
        matches.append(indexes)
    detected = [issue['id'] for issue, indexes in zip(expected, matches) if indexes]
    missed = [issue['id'] for issue, indexes in zip(expected, matches) if not indexes]
    matched_findings = {index for indexes in matches for index in indexes}
    false_positives = [index for index in range(len(findings)) if index not in matched_findings]
    verdict_match = review['verdict'] == scenario['expected_verdict']
    tests_match = ('expected_test_result' not in scenario or
                   review['build_tests']['test_result'] == scenario['expected_test_result'])
    return {'scenario': scenario['id'], 'detected_issues': detected, 'missed_issues': missed,
            'false_positive_finding_indexes': false_positives, 'verdict_match': verdict_match,
            'test_result_match': tests_match,
            'recall': len(detected) / len(expected) if expected else 1.0,
            'precision': len(matched_findings) / len(findings) if findings else (0.0 if expected else 1.0),
            'passed': verdict_match and tests_match and not missed and not false_positives}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dataset', type=Path, default=Path(__file__).resolve().parents[1] / 'evals/scenarios.json')
    parser.add_argument('--scenario', required=True)
    parser.add_argument('--review', type=Path, required=True)
    args = parser.parse_args()
    try:
        scenarios = json.loads(args.dataset.read_text())['scenarios']
        scenario = next(item for item in scenarios if item['id'] == args.scenario)
        report = evaluate(scenario, json.loads(args.review.read_text()))
    except (OSError, ValueError, KeyError, TypeError, StopIteration):
        print(json.dumps({'error': 'Invalid dataset, scenario, or structured review'}))
        return 2
    print(json.dumps(report, indent=2))
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    sys.exit(main())
