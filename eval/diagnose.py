"""
Diagnose: Two-layer failure attribution for web agent evaluation

Layer A (Reasoning): Model failed to correctly identify/describe the target
  - target not found in page elements (grounding mismatch)
  - page didn't change after successful execution (wrong action direction)

Layer B (Execution): Target was found but technical execution failed
  - element found but click/type failed
  - timing issues, iframe, Playwright-level errors
"""

from typing import Dict, Any, List, Optional
import re


# ─────────────────────────────────────────
# Fuzzy Matching
# ─────────────────────────────────────────

def fuzzy_match(target: str, element_name: str, threshold: float = 0.6) -> bool:
    """
    Check if target loosely matches an element name.
    Uses three strategies in order:
      1. Substring match (either direction)
      2. Word overlap ratio
      3. Acronym / abbreviation check
    """
    if not target or not element_name:
        return False

    t = target.lower().strip()
    e = element_name.lower().strip()

    # Strategy 1: substring
    if t in e or e in t:
        return True

    # Strategy 2: word overlap
    t_words = set(re.findall(r'\w+', t))
    e_words = set(re.findall(r'\w+', e))
    if t_words and e_words:
        overlap = len(t_words & e_words) / max(len(t_words), len(e_words))
        if overlap >= threshold:
            return True

    return False


# ─────────────────────────────────────────
# Error classification
# ─────────────────────────────────────────

# Maps raw Playwright error keywords → readable error_type
# error_type also signals likely layer:
#   'element_not_found', 'ambiguous_target'  → supports Layer A
#   everything else                          → supports Layer B
_ERROR_PATTERNS = [
    ('element_not_found',  ['not found', 'no element', 'unable to find']),
    ('ambiguous_target',   ['strict mode violation', 'multiple elements']),
    ('timeout',            ['timeout', 'timed out']),
    ('not_visible',        ['not visible', 'outside viewport', 'hidden']),
    ('element_detached',   ['detached', 'destroyed', 'navigating']),
    ('iframe_issue',       ['frame', 'iframe', 'cross-origin']),
    ('click_intercepted',  ['intercepted', 'obscured', 'covered']),
]

def classify_error(error_msg: str) -> str:
    """
    Map a raw Playwright / executor error message to a readable error_type.

    Layer A signals : element_not_found, ambiguous_target
    Layer B signals : timeout, not_visible, element_detached,
                      iframe_issue, click_intercepted, other
    """
    if not error_msg:
        return 'unknown'

    e = error_msg.lower()
    for error_type, keywords in _ERROR_PATTERNS:
        if any(kw in e for kw in keywords):
            return error_type

    return 'other'


# Error types that suggest the model got the target wrong (→ Layer A)
_LAYER_A_ERROR_TYPES = {'element_not_found', 'ambiguous_target'}


def find_matching_element(target: str, elements: List[Dict]) -> Optional[Dict]:
    """
    Return the best-matching element for a given target string.
    Returns None if no match found.
    """
    if not target or not elements:
        return None

    for elem in elements:
        if fuzzy_match(target, elem.get('name', '')):
            return elem

    return None


# ─────────────────────────────────────────
# Step-level diagnosis
# ─────────────────────────────────────────

ACTIONS_NEEDING_TARGET = {'click', 'type', 'select'}


def diagnose_step(step_record: Dict[str, Any]) -> Dict[str, Any]:
    """
    Diagnose a single step and return a diagnosis dict.

    Input step_record fields expected:
      action          - the action dict (type, target, ...)
      elements_before - interactive elements snapshot before execution
      result          - execution result (success, error)
      url_before      - URL before execution
      url_after       - URL after execution

    Returns:
      {
        layer: "A" | "B" | "ok" | "skip",
        symptom: str,
        detail: str,
        matched_element: dict | None
      }
    """
    action = step_record.get('action', {})
    action_type = action.get('type', '')
    result = step_record.get('result', {})
    elements = step_record.get('elements_before', [])
    url_before = step_record.get('url_before', '')
    url_after = step_record.get('url_after', '')

    error_msg = result.get('error', '')

    # Actions that don't need a target (goto, scroll, done)
    if action_type not in ACTIONS_NEEDING_TARGET:
        if not result.get('success'):
            error_type = classify_error(error_msg)
            return {
                'layer': 'B',
                'symptom': 'execution_error_no_target',
                'error_type': error_type,
                'detail': error_msg or 'Unknown error',
                'matched_element': None
            }
        return {
            'layer': 'ok', 'symptom': '', 'error_type': None,
            'detail': '', 'matched_element': None
        }

    # Get the target string from action
    target = action.get('target') or action.get('dropdown') or ''

    # Try to find matching element in page
    matched = find_matching_element(target, elements)

    # ── Case 1: execution failed ──────────────────────────────
    if not result.get('success'):
        error_type = classify_error(error_msg)

        if matched and error_type not in _LAYER_A_ERROR_TYPES:
            # Element found in AXTree AND error is not "not found" type
            # → something went wrong at the Playwright level → Layer B
            return {
                'layer': 'B',
                'symptom': 'execution_failed',
                'error_type': error_type,
                'detail': (
                    f"Matched element '{matched['name']}' in AXTree "
                    f"but Playwright error: {error_msg}"
                ),
                'matched_element': matched
            }
        else:
            # Either no match found, or error itself says "element not found"
            # Both point to the model naming the wrong target → Layer A
            return {
                'layer': 'A',
                'symptom': 'target_not_found',
                'error_type': error_type,
                'detail': (
                    f"Target '{target}' not found "
                    f"({len(elements)} elements on page). "
                    f"Error: {error_msg}"
                ),
                'matched_element': None
            }

    # ── Case 2: execution succeeded but page didn't change ────
    if action_type == 'click' and url_before == url_after and url_before != '':
        return {
            'layer': 'A',
            'symptom': 'no_page_change',
            'error_type': None,
            'detail': f"Clicked '{target}' successfully but URL unchanged: {url_before}",
            'matched_element': matched
        }

    # ── Case 3: everything looks fine ─────────────────────────
    return {
        'layer': 'ok',
        'symptom': '',
        'error_type': None,
        'detail': '',
        'matched_element': matched
    }


# ─────────────────────────────────────────
# Task-level diagnosis
# ─────────────────────────────────────────

def diagnose_task(task_result: Dict[str, Any]) -> Dict[str, Any]:
    """
    Diagnose an entire task run.

    Expects task_result to contain:
      success       - bool
      history       - list of step_records (each with fields from diagnose_step)
      task          - the original task dict

    Returns:
      {
        task_id: str,
        success: bool,
        total_steps: int,
        failure_layer: "A" | "B" | None,
        failure_symptom: str,
        failure_detail: str,
        step_diagnoses: list,
        first_failure_step: int | None,
      }
    """
    history = task_result.get('history', [])
    success = task_result.get('success', False)
    task = task_result.get('task', {})

    step_diagnoses = []
    first_failure_step = None
    failure_layer = None
    failure_symptom = ''
    failure_detail = ''

    for record in history:
        diag = diagnose_step(record)
        diag['step'] = record.get('step')
        step_diagnoses.append(diag)

        # Record the first non-ok step as the likely failure point
        if diag['layer'] in ('A', 'B') and first_failure_step is None:
            first_failure_step = record.get('step')
            failure_layer = diag['layer']
            failure_symptom = diag['symptom']
            failure_detail = diag['detail']

    # If no specific step failure found but task still failed → planning issue (Layer A)
    if not success and failure_layer is None:
        failure_layer = 'A'
        failure_symptom = 'planning_failed'
        failure_detail = 'All steps executed without error but goal was not achieved'

    return {
        'task_id': task.get('id', 'unknown'),
        'task_goal': task.get('goal', ''),
        'task_level': task.get('level'),
        'success': success,
        'total_steps': len(history),
        'failure_layer': failure_layer if not success else None,
        'failure_symptom': failure_symptom if not success else '',
        'failure_detail': failure_detail if not success else '',
        'step_diagnoses': step_diagnoses,
        'first_failure_step': first_failure_step,
    }


# ─────────────────────────────────────────
# Batch report
# ─────────────────────────────────────────

def generate_report(task_diagnoses: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Aggregate diagnoses across all tasks into a summary report.
    """
    total = len(task_diagnoses)
    if total == 0:
        return {}

    successes = [d for d in task_diagnoses if d['success']]
    failures = [d for d in task_diagnoses if not d['success']]

    # Layer distribution among failures
    layer_a = [d for d in failures if d['failure_layer'] == 'A']
    layer_b = [d for d in failures if d['failure_layer'] == 'B']

    # Symptom breakdown (task level)
    symptom_counts: Dict[str, int] = {}
    for d in failures:
        s = d['failure_symptom']
        symptom_counts[s] = symptom_counts.get(s, 0) + 1

    # Error type breakdown (step level, Layer B steps only)
    error_type_counts: Dict[str, int] = {}
    for d in task_diagnoses:
        for step_diag in d.get('step_diagnoses', []):
            if step_diag.get('layer') == 'B' and step_diag.get('error_type'):
                et = step_diag['error_type']
                error_type_counts[et] = error_type_counts.get(et, 0) + 1

    # By task level
    by_level: Dict[int, Dict] = {}
    for d in task_diagnoses:
        lvl = d.get('task_level')
        if lvl not in by_level:
            by_level[lvl] = {'total': 0, 'success': 0}
        by_level[lvl]['total'] += 1
        if d['success']:
            by_level[lvl]['success'] += 1

    for lvl, stats in by_level.items():
        stats['success_rate'] = round(stats['success'] / stats['total'], 2)

    report = {
        'total_tasks': total,
        'success_count': len(successes),
        'failure_count': len(failures),
        'overall_success_rate': round(len(successes) / total, 2),

        'failure_attribution': {
            'layer_A_reasoning': len(layer_a),
            'layer_B_execution': len(layer_b),
            'layer_A_pct': round(len(layer_a) / len(failures), 2) if failures else 0,
            'layer_B_pct': round(len(layer_b) / len(failures), 2) if failures else 0,
        },

        'symptom_breakdown': symptom_counts,
        'error_type_breakdown': error_type_counts,   # Layer B step-level detail
        'by_level': by_level,

        'failed_cases': [
            {
                'task_id': d['task_id'],
                'goal': d['task_goal'],
                'level': d['task_level'],
                'layer': d['failure_layer'],
                'symptom': d['failure_symptom'],
                'detail': d['failure_detail'],
                'failed_at_step': d['first_failure_step'],
            }
            for d in failures
        ]
    }

    return report


def print_report(report: Dict[str, Any]):
    """Pretty print the evaluation report."""
    print("\n" + "="*60)
    print("EVALUATION REPORT")
    print("="*60)
    print(f"Total Tasks:    {report['total_tasks']}")
    print(f"Success Rate:   {report['overall_success_rate']*100:.0f}%  "
          f"({report['success_count']}/{report['total_tasks']})")

    print("\nBy Level:")
    for lvl, stats in sorted(report['by_level'].items()):
        bar = "✅" if stats['success_rate'] >= 0.8 else ("⚠️ " if stats['success_rate'] >= 0.5 else "❌")
        print(f"  Level {lvl}: {stats['success']}/{stats['total']} = "
              f"{stats['success_rate']*100:.0f}%  {bar}")

    fa = report['failure_attribution']
    if report['failure_count'] > 0:
        print(f"\nFailure Attribution ({report['failure_count']} failures):")
        print(f"  Layer A (Reasoning):  {fa['layer_A_reasoning']}  "
              f"({fa['layer_A_pct']*100:.0f}%)  → fix prompt / observation")
        print(f"  Layer B (Execution):  {fa['layer_B_execution']}  "
              f"({fa['layer_B_pct']*100:.0f}%)  → fix executor / wait strategy")

        print("\nLayer A symptom breakdown:")
        for symptom, count in sorted(report['symptom_breakdown'].items(),
                                     key=lambda x: -x[1]):
            print(f"  {symptom:<30} {count}")

        if report.get('error_type_breakdown'):
            print("\nLayer B error type breakdown:")
            hint = {
                'element_not_found':  '→ name mismatch (check Layer A boundary)',
                'timeout':            '→ increase wait time',
                'not_visible':        '→ scroll or viewport issue',
                'element_detached':   '→ dynamic page, add explicit wait',
                'iframe_issue':       '→ iframe handling needed',
                'click_intercepted':  '→ element obscured, try scroll first',
                'ambiguous_target':   '→ target name too generic',
                'other':              '→ inspect raw error',
            }
            for et, count in sorted(report['error_type_breakdown'].items(),
                                    key=lambda x: -x[1]):
                tip = hint.get(et, '')
                print(f"  {et:<25} {count}  {tip}")

        print("\nFailed Cases:")
        for case in report['failed_cases']:
            print(f"  [{case['layer']}] Step {case['failed_at_step']} | "
                  f"L{case['level']} | {case['symptom']}")
            print(f"       Goal:   {case['goal'][:60]}")
            print(f"       Detail: {case['detail'][:80]}")

    print("="*60)