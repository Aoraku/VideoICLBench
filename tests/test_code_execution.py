"""Course checks run actual submitted Python while excluding host capabilities."""
import pytest
from vic_apps.code_execution import run_checks,syntax_check


def test_real_nested_functions_inputs_and_failures():
    files={'solution.py':'def solve(values):\n    total = 0\n    for value in values:\n        if value > 0:\n            total += value\n    return total\n'}
    tests=[dict(name='mixed',args=[[-3,5,0,8]],expected=13),dict(name='empty',args=[[]],expected=0)]
    result=run_checks(files,tests)
    assert result['passed'] and [r['actual'] for r in result['cases']]==[13,0]
    wrong=run_checks({'solution.py':files['solution.py'].replace('value > 0','value < 0')},tests)
    assert not wrong['passed'] and wrong['status']=='WA' and wrong['cases'][0]['actual']==-3
    error=run_checks({'solution.py':'def solve(values):\n    return 1 // 0\n'},tests)
    assert error['status']=='RE' and 'ZeroDivisionError' in error['cases'][0]['detail']


def test_real_cross_file_imports_and_broken_rename():
    files={'pricing.py':'tax_rate = 8\n\ndef subtotal(items):\n    total = 0\n    for price, quantity in items:\n        total += price * quantity\n    return total\n',
           'invoice.py':'from pricing import subtotal, tax_rate\n\ndef invoice(items):\n    total = subtotal(items)\n    tax = total * tax_rate // 100\n    return {"label": "total tax_rate tax", "amount": total + tax}\n',
           'app.py':'from invoice import invoice\n\ndef solve(items):\n    summary = invoice(items)\n    return summary["amount"]\n'}
    tests=[dict(name='invoice',args=[[[100,2],[250,1]]],expected=486)]
    result=run_checks(files,tests,'app.py');assert result['passed'],result
    broken={**files,'pricing.py':files['pricing.py'].replace('tax_rate','x_tax_rate')}
    result=run_checks(broken,tests,'app.py');assert not result['passed'] and result['status']=='RE'


@pytest.mark.parametrize('code',[
    'import os\ndef solve():\n    return os.environ\n',
    'from os import system\ndef solve():\n    return 1\n',
    'def solve():\n    return (1).__class__\n',
    'def solve():\n    return __builtins__\n',
    'def solve():\n    return open("/etc/passwd")\n',
    'def solve():\n    return eval("1+1")\n',
])
def test_host_capabilities_are_unavailable(code):
    result=run_checks({'solution.py':code},[dict(args=[],expected=1)])
    assert not result['passed'] and result['status'] in ('CE','RE')


def test_syntax_check_is_distinct_from_running_tests():
    valid={'solution.py':'def solve():\n    return 1 // 0\n'}
    assert syntax_check(valid)['passed']
    assert not run_checks(valid,[dict(args=[],expected=0)])['passed']
    invalid={'solution.py':'def solve()\n    return 0\n'}
    assert not syntax_check(invalid)['passed']
    assert run_checks(invalid,[dict(args=[],expected=0)])['status']=='CE'


def test_unbounded_recursion_terminates_as_runtime_error():
    result=run_checks({'solution.py':'def solve():\n    return solve()\n'},[dict(args=[],expected=0)])
    assert not result['passed'] and result['status']=='RE'


def test_long_running_student_program_has_a_time_limit():
    code='def solve():\n    total = 0\n    for i in range(100000):\n        for j in range(100000):\n            total += 1\n    return total\n'
    result=run_checks({'solution.py':code},[dict(args=[],expected=0)])
    assert not result['passed'] and result['status']=='TLE'
