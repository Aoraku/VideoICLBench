"""Concrete OJ example inputs and executable reference answers, independent of task rules."""
from collections import Counter, deque, OrderedDict
from functools import lru_cache
import heapq
import itertools
import json
from pathlib import Path

PROBLEMS = json.loads(Path(__file__).with_name('oj_problems.json').read_text())


def problem_content(title):
    data = dict(PROBLEMS[title])
    if title == '数独验证':
        constraint = '棋盘大小为 4×4；格值为 0–4。'
    elif title == '括号匹配':
        constraint = '字符串仅包含 ()、[]、{}，长度为 1–100000。'
    elif title in ('字符串压缩', '编辑距离', '字母异位词', '子序列匹配', '前缀树查询', '最长回文子串'):
        constraint = '字符串由小写英文字母组成；长度为 1–1000。'
    else:
        constraint = '数组、节点和操作数量为 1–100000；编号及输入格式以题面说明为准。'
    return {**data, 'constraints': constraint}


def words(values):
    return ' '.join(map(str, values))


def example_input(title, k):
    a = k + 1
    n = 3 + k % 5
    values = [((j * 7 + k * 3) % 23) - 8 for j in range(n)]
    if title == '两数之和':
        target = a + a + 11
        items = [a, a+11] + [target+j+1 for j in range(n-2)]
        shift = k % n
        items = items[shift:] + items[:shift]
        return f'{n} {target}\n' + words(items)
    if title == '合并有序数组':
        return f'{n} {n+1}\n' + words(a+j*2 for j in range(n)) + '\n' + words(a-1+j*3 for j in range(n+1))
    if title == '括号匹配':
        text = '(' * (a//2+1) + '[]{}' + ')' * (a//2+1)
        return text if k % 2 == 0 else text[:-1] + ']'
    if title in ('二叉树遍历', '路径总和'):
        tree = [a+j*2 for j in range(n)]
        if title == '二叉树遍历':
            return words(tree)
        pos, target = n-1, 0
        while True:
            target += tree[pos]
            if pos == 0: break
            pos = (pos-1)//2
        return f'{target if k%2==0 else -target}\n' + words(tree)
    if title == '最短路径':
        edges = [(j,j+1,a+j) for j in range(1,n)] + [(1,n,a if k%2 else a*n*2)]
        return f'{n} {len(edges)} 1\n' + '\n'.join(words(e) for e in edges)
    if title == '区间合并':
        return f'3\n{a} {a+3}\n{a+2} {a+6}\n{a+8} {a+9}'
    if title in ('旋转数组', '窗口最大值'):
        amount = k % n if title == '旋转数组' else k % n + 1
        return f'{n} {amount}\n' + words(v+a*30 for v in values)
    if title == '字符串压缩':
        return 'a' * a + 'b' * (1+k%5) + 'c' * (1+k%3)
    if title in ('链表反转', '单调栈练习', '堆排序'):
        return words(v + a*30 for v in values)
    if title == '乘积最大子数组':
        return words([a, -2, 0 if k%3==0 else -3, 4, -1])
    if title == '岛屿数量':
        grid = [[(k >> (r*4+c)) & 1 for c in range(4)] for r in range(3)]
        return '3 4\n' + '\n'.join(words(row) for row in grid)
    if title == '矩阵搜索':
        target = a+2 if k%2==0 else a+20
        return f'2 3 {target}\n' + words(range(a,a+3)) + '\n' + words(range(a+3,a+6))
    if title in ('课程安排', '拓扑排序', '地图着色', '航班路线规划'):
        n = 3 + k//2
        edges = [(j,j+1) for j in range(1,n)]
        if title == '课程安排':
            edges = [(x-1,y-1) for x,y in edges]
            if k%2: edges.append((n-1,0))
        elif title == '地图着色' and k%2:
            edges.append((1,3))
        elif title == '拓扑排序' and k%2:
            edges = [(x,n) for x in range(1,n)]
        elif title == '航班路线规划' and k%2:
            edges = edges[:-1]
        head = f'{n} {len(edges)}' + (' 1 '+str(n) if title=='航班路线规划' else '')
        return head + '\n' + '\n'.join(words(e) for e in edges)
    if title == '编辑距离':
        return 'a'*a+'bc\n'+'a'*(a+k%3)+'bd'
    if title == '环形队列':
        return f'2\npush {a}\npush {a+3}\npush {a+9}\npop\npush {a+5}\npop\npop\npop'
    if title == '位运算入门':
        return str(k)
    if title == '数独验证':
        board = [[1,2,3,4],[3,4,1,2],[2,1,4,3],[4,3,2,1]]
        for p in range(12):
            if (k//2) >> p & 1: board[1+p//4][p%4] = 0
        if k%2: board[0][1] = 1
        return '\n'.join(words(row) for row in board)
    if title == '字母异位词':
        return 'a'*a+'bc\n'+'bc'+'a'*a+('d' if k%2 else '')
    if title == '缓存设计':
        return '2\n'+words([a,a+1,a,a+2,a+1,a+3])
    if title == '子序列匹配':
        return 'a'*a+'z\n'+'ab'*a+('z' if k%2==0 else '')
    if title == '前缀树查询':
        prefix = 'a'*a
        return f'4\n{prefix}cat\n{prefix}car\ndog\n{prefix}dog\n{prefix}'
    if title == '最长回文子串':
        return 'a'*a+'bc'+'a'*a
    if title == '区间查询':
        return f'{n} 3\n'+words(v+a*30 for v in values)+f'\n1 {n}\n2 {n}\n1 1'
    raise KeyError(title)


def solve(title, text):
    lines = text.splitlines()
    nums = lambda line: list(map(int, line.split()))
    if title == '两数之和':
        _, target = nums(lines[0]); values = nums(lines[1])
        return next(words([i,j]) for i in range(len(values)) for j in range(i+1,len(values)) if values[i]+values[j]==target)
    if title == '合并有序数组': return words(sorted(nums(lines[1])+nums(lines[2])))
    if title == '括号匹配':
        stack=[]
        for c in text:
            if c in '([{': stack.append(c)
            elif not stack or stack.pop() != {')':'(',']':'[','}':'{'}[c]: return 'NO'
        return 'NO' if stack else 'YES'
    if title in ('二叉树遍历', '路径总和'):
        tokens=lines[-1].split(); root=[int(tokens[0]),None,None]; queue=deque([root]); i=1
        while queue and i<len(tokens):
            node=queue.popleft()
            for child in (1,2):
                if i>=len(tokens): break
                if tokens[i]!='null': node[child]=[int(tokens[i]),None,None];queue.append(node[child])
                i+=1
        def preorder(node):
            return [] if node is None else [node[0]]+preorder(node[1])+preorder(node[2])
        def sums(node, value=0):
            if node is None:return []
            value+=node[0]
            return [value] if not node[1] and not node[2] else sums(node[1],value)+sums(node[2],value)
        return words(preorder(root)) if title=='二叉树遍历' else ('YES' if int(lines[0]) in sums(root) else 'NO')
    if title == '最短路径':
        n,_,start=nums(lines[0]); dist=[float('inf')]*(n+1);dist[start]=0;queue=[(0,start)];graph=[[] for _ in range(n+1)]
        for line in lines[1:]:
            x,y,w=nums(line);graph[x].append((y,w))
        while queue:
            cost,x=heapq.heappop(queue)
            if cost!=dist[x]:continue
            for y,w in graph[x]:
                if cost+w<dist[y]:dist[y]=cost+w;heapq.heappush(queue,(dist[y],y))
        return words(-1 if d==float('inf') else d for d in dist[1:])
    if title == '区间合并':
        merged=[]
        for left,right in sorted(nums(line) for line in lines[1:]):
            if merged and left<=merged[-1][1]:merged[-1][1]=max(merged[-1][1],right)
            else:merged.append([left,right])
        return '\n'.join(words(row) for row in merged)
    if title == '旋转数组':
        n,k=nums(lines[0]);a=nums(lines[1]);k%=n
        return words(a[-k:]+a[:-k] if k else a)
    if title == '字符串压缩': return ''.join(c+str(len(list(group))) for c,group in itertools.groupby(text))
    if title == '链表反转':return words(nums(text)[::-1])
    if title == '岛屿数量':
        rows,cols=nums(lines[0]);grid=[nums(line) for line in lines[1:]];seen=set();count=0
        for r in range(rows):
            for c in range(cols):
                if not grid[r][c] or (r,c) in seen:continue
                count+=1;queue=[(r,c)];seen.add((r,c))
                while queue:
                    x,y=queue.pop()
                    for u,v in ((x-1,y),(x+1,y),(x,y-1),(x,y+1)):
                        if 0<=u<rows and 0<=v<cols and grid[u][v] and (u,v) not in seen:seen.add((u,v));queue.append((u,v))
        return str(count)
    if title == '矩阵搜索':return 'YES' if nums(lines[0])[2] in [v for line in lines[1:] for v in nums(line)] else 'NO'
    if title in ('课程安排','拓扑排序'):
        n,_=nums(lines[0]);start=0 if title=='课程安排' else 1;graph={i:[] for i in range(start,n+start)};degree=dict.fromkeys(graph,0)
        for line in lines[1:]:
            x,y=nums(line);graph[x].append(y);degree[y]+=1
        queue=[i for i in graph if not degree[i]];heapq.heapify(queue);order=[]
        while queue:
            x=heapq.heappop(queue);order.append(x)
            for y in graph[x]:
                degree[y]-=1
                if not degree[y]:heapq.heappush(queue,y)
        return ('YES' if len(order)==n else 'NO') if title=='课程安排' else words(order)
    if title == '窗口最大值':
        n,k=nums(lines[0]);a=nums(lines[1]);return words(max(a[i:i+k]) for i in range(n-k+1))
    if title == '编辑距离':
        a,b=lines;row=list(range(len(b)+1))
        for i,x in enumerate(a,1):
            nxt=[i]
            for j,y in enumerate(b,1):nxt.append(min(nxt[-1]+1,row[j]+1,row[j-1]+(x!=y)))
            row=nxt
        return str(row[-1])
    if title == '环形队列':
        size=int(lines[0]);queue=deque();out=[]
        for line in lines[1:]:
            if line=='pop':out.append(str(queue.popleft()) if queue else 'EMPTY')
            elif len(queue)<size:queue.append(int(line.split()[1]))
        return '\n'.join(out)
    if title == '位运算入门':return str(int(text).bit_count())
    if title == '数独验证':
        grid=[nums(line) for line in lines]
        units=grid+list(zip(*grid))+[[grid[r+i][c+j] for i in range(2) for j in range(2)] for r in (0,2) for c in (0,2)]
        return 'YES' if all(len([x for x in row if x])==len({x for x in row if x}) for row in units) else 'NO'
    if title == '字母异位词':return 'YES' if Counter(lines[0])==Counter(lines[1]) else 'NO'
    if title == '缓存设计':
        size=int(lines[0]);cache=OrderedDict()
        for x in nums(lines[1]):
            cache[x]=None;cache.move_to_end(x)
            if len(cache)>size:cache.popitem(last=False)
        return words(cache)
    if title == '子序列匹配':
        it=iter(lines[1]);return 'YES' if all(any(x==y for y in it) for x in lines[0]) else 'NO'
    if title == '前缀树查询':return str(sum(word.startswith(lines[-1]) for word in lines[1:-1]))
    if title == '单调栈练习':
        a=nums(text);return words(next((v for v in a[i+1:] if v>x),-1) for i,x in enumerate(a))
    if title == '最长回文子串':
        candidates=[text[i:j] for i in range(len(text)) for j in range(i+1,len(text)+1) if text[i:j]==text[i:j][::-1]]
        return max(candidates,key=len)
    if title == '乘积最大子数组':
        a=nums(text);best=lo=hi=a[0]
        for x in a[1:]:lo,hi=min(x,lo*x,hi*x),max(x,lo*x,hi*x);best=max(best,hi)
        return str(best)
    if title in ('地图着色','航班路线规划'):
        head=nums(lines[0]);n=head[0];graph={i:[] for i in range(1,n+1)}
        for line in lines[1:]:
            x,y=nums(line);graph[x].append(y);graph[y].append(x)
        if title=='航班路线规划':
            start,end=head[2:];dist={start:0};queue=deque([start])
            while queue:
                x=queue.popleft()
                for y in graph[x]:
                    if y not in dist:dist[y]=dist[x]+1;queue.append(y)
            return str(dist.get(end,-1))
        colors={}
        for start in graph:
            if start in colors:continue
            colors[start]=0;queue=[start]
            while queue:
                x=queue.pop()
                for y in graph[x]:
                    if y in colors and colors[y]==colors[x]:return 'NO'
                    if y not in colors:colors[y]=1-colors[x];queue.append(y)
        return 'YES'
    if title == '堆排序':return words(sorted(nums(text)))
    if title == '区间查询':
        a=nums(lines[1]);return '\n'.join(str(sum(a[left-1:right])) for left,right in map(nums,lines[2:]))
    raise KeyError(title)


@lru_cache(maxsize=1200)
def samples(title, count):
    if not 1<=count<=100:raise ValueError('Sample count must be between 1 and 100')
    first=PROBLEMS[title]['example'];result=[dict(first)];seen={first['input']}
    for index in range(10000):
        if len(result)==count:return result
        text=example_input(title,index)
        if text in seen:continue
        result.append(dict(input=text,output=solve(title,text)));seen.add(text)
    raise ValueError('Insufficient distinct OJ examples')
