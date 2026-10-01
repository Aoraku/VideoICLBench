"""Execute the published course Python subset in a bounded, isolated child process.

The course supports ordinary functions, loops, conditionals, arithmetic and
imports between the provided files. No file, network, attribute or host import
access is available to submitted code. Each test receives fresh module globals.
"""
import ast
import json
from pathlib import Path
import re
import subprocess
import sys

ALLOWED={ast.Module,ast.FunctionDef,ast.arguments,ast.arg,ast.Return,ast.Assign,
         ast.AugAssign,ast.For,ast.If,ast.Expr,ast.Pass,ast.Constant,ast.Name,
         ast.Load,ast.Store,ast.List,ast.Tuple,ast.Dict,ast.Subscript,ast.Slice,
         ast.BinOp,ast.UnaryOp,ast.BoolOp,ast.Compare,ast.Call,ast.keyword,
         ast.IfExp,ast.Add,ast.Sub,ast.Mult,ast.Div,ast.FloorDiv,ast.Mod,
         ast.USub,ast.UAdd,ast.Not,ast.And,ast.Or,ast.Eq,ast.NotEq,ast.Lt,
         ast.LtE,ast.Gt,ast.GtE,ast.In,ast.NotIn,ast.ImportFrom,ast.alias,
         ast.Break,ast.Continue}


def validate(files):
    if not isinstance(files,dict) or not 1<=len(files)<=8:raise ValueError('需要一至八个 Python 文件')
    trees={}
    for name,code in files.items():
        if not re.fullmatch(r'[a-z][a-z0-9_]*\.py',name) or not isinstance(code,str) or len(code)>30000:raise ValueError('文件名或代码长度不符合课程运行要求')
        tree=ast.parse(code,filename=name)
        for node in ast.walk(tree):
            if type(node) not in ALLOWED:raise ValueError('课程环境不支持 '+type(node).__name__)
            names=[]
            if isinstance(node,ast.Name):names=[node.id]
            elif isinstance(node,ast.FunctionDef):names=[node.name]
            elif isinstance(node,ast.arg):names=[node.arg]
            elif isinstance(node,ast.alias):names=[node.name,node.asname or node.name]
            if any(n.startswith('_') for n in names):raise ValueError('课程环境不支持私有运行时名称')
            if isinstance(node,ast.ImportFrom) and (node.level or (node.module or '')+'.py' not in files):raise ValueError('只能导入项目中给出的模块')
            if isinstance(node,ast.Call) and not isinstance(node.func,ast.Name):raise ValueError('课程环境仅支持按名称调用函数')
        trees[name]=tree
    return trees


def syntax_check(files):
    try:
        for name,code in files.items():ast.parse(code,filename=name)
        return dict(passed=True,status='PASS',detail='全部文件的 Python 语法检查通过')
    except (SyntaxError,ValueError,TypeError) as exc:
        return dict(passed=False,status='FAIL',detail=str(exc))


def run_checks(files,tests,entry='solution.py',function='solve'):
    try:validate(files)
    except (SyntaxError,ValueError,TypeError) as exc:
        return dict(passed=False,status='CE',cases=[],detail=str(exc))
    payload=dict(files=files,tests=tests,entry=entry,function=function)
    try:
        child=subprocess.run([sys.executable,'-I','-S',str(Path(__file__).resolve())],input=json.dumps(payload),text=True,capture_output=True,timeout=4,env={'PYTHONIOENCODING':'utf-8'},close_fds=True)
        if child.returncode:return dict(passed=False,status='TLE' if child.returncode<0 else 'RE',cases=[],detail='课程运行超出限制或异常结束')
        return json.loads(child.stdout)
    except subprocess.TimeoutExpired:return dict(passed=False,status='TLE',cases=[],detail='运行超过时间限制')
    except (ValueError,OSError):return dict(passed=False,status='RE',cases=[],detail='无法取得课程运行结果')


def _worker(payload):
    import resource
    resource.setrlimit(resource.RLIMIT_CPU,(2,2))
    if sys.platform.startswith('linux'):resource.setrlimit(resource.RLIMIT_AS,(256*1024*1024,256*1024*1024))
    trees=validate(payload['files']);cases=[]
    safe=dict(abs=abs,min=min,max=max,sum=sum,len=len,range=range,enumerate=enumerate,
              sorted=sorted,reversed=reversed,int=int,str=str,bool=bool,list=list,tuple=tuple,dict=dict)
    compiled={name:compile(tree,name,'exec') for name,tree in trees.items()}
    for index,test in enumerate(payload['tests']):
        modules={};loading=set()
        def load(name):
            if name in modules:return modules[name]
            if name in loading:raise ValueError('项目存在循环导入')
            loading.add(name);namespace={'__builtins__':dict(safe,__import__=import_module)}
            exec(compiled[name+'.py'],namespace)
            loading.remove(name);modules[name]=namespace;return namespace
        def import_module(name,globals=None,locals=None,fromlist=(),level=0):
            from types import SimpleNamespace
            if level or name+'.py' not in compiled:raise ValueError('不支持的项目导入')
            namespace=load(name)
            return SimpleNamespace(**{n:namespace[n] for n in fromlist})
        row=dict(name=test.get('name',f'T{index+1}'),input=test['args'],expected=test['expected'])
        try:
            namespace=load(payload['entry'][:-3]);actual=namespace[payload['function']](*test['args'])
            # Only plain JSON outputs cross the subprocess boundary.
            encoded=json.dumps(actual);actual=json.loads(encoded)
            row.update(actual=actual,status='AC' if actual==test['expected'] else 'WA',detail='')
        except Exception as exc:row.update(actual=None,status='RE',detail=type(exc).__name__+': '+str(exc))
        cases.append(row)
    passed=bool(cases) and all(r['status']=='AC' for r in cases)
    return dict(passed=passed,status='AC' if passed else next((r['status'] for r in cases if r['status']!='AC'),'RE'),cases=cases,detail='')


if __name__=='__main__':
    try:result=_worker(json.loads(sys.stdin.read()))
    except Exception as exc:result=dict(passed=False,status='CE',cases=[],detail=type(exc).__name__+': '+str(exc))
    print(json.dumps(result,ensure_ascii=False))
