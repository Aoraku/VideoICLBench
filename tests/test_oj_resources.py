"""Exercise assets must agree with the problem statement and their displayed count."""
import itertools
import pytest
from vic_apps.oj_resources import PROBLEMS, example_input, samples, solve
from vic.teaching import NAMES, QUERY_NAMES


@pytest.mark.parametrize('title', sorted(PROBLEMS))
def test_problem_examples_are_distinct_counted_and_known_answer_agrees(title):
    known=PROBLEMS[title]['example']
    assert solve(title,known['input'])==known['output']
    rows=samples(title,39)
    assert len(rows)==len({row['input'] for row in rows})==39
    assert all(isinstance(row['output'],str) and row['output'] for row in rows)
    assert samples(title,4)==rows[:4]


def test_all_demo_and_query_problem_titles_have_real_examples():
    assert set(NAMES['code']+QUERY_NAMES['code'])==set(PROBLEMS)


def test_generated_two_sum_guarantees_unique_solution_and_correct_indices():
    for row in samples('两数之和',39):
        head,values=row['input'].splitlines();n,target=map(int,head.split());a=list(map(int,values.split()))
        pairs=[(i,j) for i,j in itertools.combinations(range(n),2) if a[i]+a[j]==target]
        assert len(pairs)==1 and tuple(map(int,row['output'].split()))==pairs[0]


def test_shortest_path_samples_match_independent_all_pairs_distances():
    for row in samples('最短路径',39):
        lines=row['input'].splitlines();n,m,start=map(int,lines[0].split())
        assert len(lines)==m+1
        d=[[0 if i==j else float('inf') for j in range(n)] for i in range(n)]
        for line in lines[1:]:
            x,y,w=map(int,line.split());d[x-1][y-1]=min(d[x-1][y-1],w)
        for k in range(n):
            for i in range(n):
                for j in range(n):d[i][j]=min(d[i][j],d[i][k]+d[k][j])
        assert list(map(int,row['output'].split()))==[-1 if v==float('inf') else v for v in d[start-1]]


@pytest.mark.parametrize('title',['括号匹配','数独验证','地图着色','课程安排','矩阵搜索','字母异位词','子序列匹配','路径总和'])
def test_boolean_problems_include_success_and_failure_examples(title):
    assert {row['output'] for row in samples(title,39)}=={'YES','NO'}


def test_queue_cache_and_palindrome_edge_cases():
    assert solve('环形队列','1\npop\npush 7\npush 9\npop\npop')=='EMPTY\n7\nEMPTY'
    assert solve('缓存设计','2\n1 2 1 3')=='1 3'
    assert solve('最长回文子串','babad')=='bab'
    assert solve('乘积最大子数组','-2 0 -1')=='0'
    assert solve('二叉树遍历','1 null 2 3')=='1 2 3'
