from sqlmodel import Field, SQLModel
from typing import Optional, Dict, Any, List
from pydantic import BaseModel
import json

# 在若干id中，Problem User Submission的id是str，而Language Log的id是int
class Sample(SQLModel):
    input: str
    output: str

class Problem(SQLModel, table=True):
    id: str = Field(primary_key=True)
    title: str
    description: str
    input_description: str
    output_description: str
    samples: str # 之前用list，会报错无法识别
    constraints: str
    testcases: str # 之前用list，会报错无法识别

    # 可见性
    public_cases: bool = False
    
    # 评测模式
    judge_mode: str = 'standard'  # standard, strict, spj
    spj_code: Optional[str] = None  # 存储上传的SPJ脚本代码
    spj_language: Optional[str] = None  # SPJ脚本的语言
    
    hint: Optional[str] = None
    source: Optional[str] = None
    tags: Optional[str] = None # 之前用list，会报错无法识别
    time_limit: Optional[float] = None
    memory_limit: Optional[int] = None
    author: Optional[str] = None
    difficulty: Optional[str] = None
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Problem":
        new_data = data.copy()
        new_data["samples"] = json.dumps(new_data["samples"])
        new_data["testcases"] = json.dumps(new_data["testcases"])
        new_data["tags"] = json.dumps(new_data["tags"])
        return cls(**new_data)
    
    # X@classmethodX 传入了self参数，应当是实例方法，而非类方法
    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "description": self.description,
            "input_description": self.input_description,
            "output_description": self.output_description,
            "samples": json.loads(self.samples or "[]"),
            "constraints": self.constraints,
            "testcases": json.loads(self.testcases or "[]"),
            "judge_mode": self.judge_mode,
            "hint": self.hint,
            "source": self.source,
            "tags": json.loads(self.tags or "[]"),
            "time_limit": self.time_limit,
            "memory_limit": self.memory_limit,
            "author": self.author,
            "difficulty": self.difficulty,
        }
    
class FrontEnd_Sample(BaseModel):
    input: str
    output: str

class FrontEnd_Problem(BaseModel):
    # 前端逻辑，可以不输入，所以这些必输的也都改成optional，手工判断（避免pydantic自动帮我们判断422而非400）
    id: Optional[str] = None
    title: Optional[str] = None
    description: Optional[str] = None
    input_description: Optional[str] = None
    output_description: Optional[str] = None
    samples: Optional[List[FrontEnd_Sample]] = None
    constraints: Optional[str] = None
    testcases: Optional[List[FrontEnd_Sample]] = None
    
    hint: Optional[str] = None
    source: Optional[str] = None
    tags: Optional[List[str]] = []
    time_limit: Optional[float] = None
    memory_limit: Optional[int] = None
    author: Optional[str] = None
    difficulty: Optional[str] = None

class User(SQLModel, table=True):
    user_id: str = Field(primary_key=True)
    username: str = Field(index=True, unique=True)
    password: str
    role: str = "user" # default="user" 还可能为"admin""banned"
    join_time: str
    submit_count: int = 0
    resolve_count: int = 0

class FrontEnd_User(BaseModel):
    username: Optional[str] = None
    password: Optional[str] = None
    
class FrontEnd_Role(BaseModel):
    role: Optional[str] = None
    
class Submission(SQLModel, table=True):
    id: str = Field(primary_key=True)
    user_id: str
    problem_id: str
    code: str
    language: str
    status_short: str
    status: str
    score: int # 该题的得分
    counts: int # 该题的满分
    submit_time: str
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Submission":
        new_data = data.copy()
        new_data["status"] = json.dumps(new_data["status"])
        return cls(**new_data)
    
    def to_dict(self):
        return {
            "id": self.id,
            "user_id": self.user_id,
            "problem_id": self.problem_id,
            "code": self.code,
            "language": self.language,
            "status": json.loads(self.status),
            "score": self.score,
            "counts": self.counts,
            "submit_time": self.submit_time,
        }
       
    # "status": [
    #     {"id": 1, "result": "AC", "time": 1.01, "memory": 130},
    #     {"id": 2, "result": "TLE", "time": 1.01, "memory": 130},
    #     {"id": 3, "result": "MLE", "time": 1.01, "memory": 130},
    #     ],
class FrontEnd_Submission(BaseModel):
    problem_id: Optional[str] = None
    language: Optional[str] = None
    code: Optional[str] = None

class Language(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str
    file_ext: str
    compile_cmd: Optional[str] = None
    run_cmd: str
    source_template: Optional[str] = None
    time_limit: Optional[float] = None
    memory_limit: Optional[int] = None

class FrontEnd_Language(BaseModel):
    name: Optional[str] = None
    file_ext: Optional[str] = None
    compile_cmd: Optional[str] = None
    run_cmd: Optional[str] = None
    source_template: Optional[str] = None
    time_limit: Optional[float] = None
    memory_limit: Optional[int] = None
    
class FrontEnd_Visibility(BaseModel):
    public_cases: Optional[bool] = None
    
class Log(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: str
    problem_id: str
    action: str = 'view_log'
    time: str
    status: str = ''