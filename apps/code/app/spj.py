import tempfile
import os
import uuid
import json
import math
from typing import Tuple, Optional

def execute_spj_script(spj_code: str, input_str: str, expected_output: str, user_output: str, spj_language: str = "python") -> bool:
    """
    Args:
        spj_code: 上传的SPJ脚本代码
        input_str: 测试用例的输入
        expected_output: 标准输出
        user_output: 用户输出
        spj_language: SPJ脚本语言 (默认为python)
        
    Returns:
        bool: 用户输出是否正确
    """

    if spj_language.lower() != "python":
        # 不支持的语言，用默认SPJ
        return check_set_equal(expected_output, user_output)
    
    # 创建临时脚本和环境
    work_dir = None
    try:
        # 临时目录
        work_dir = os.path.join(tempfile.gettempdir(), f"spj_{uuid.uuid4().hex}")
        os.makedirs(work_dir, exist_ok=True)
        
        # 将输入和输出写入临时文件
        with open(os.path.join(work_dir, "input.txt"), "w", encoding="utf-8") as f:
            f.write(input_str)
            
        with open(os.path.join(work_dir, "expected.txt"), "w", encoding="utf-8") as f:
            f.write(expected_output)
            
        with open(os.path.join(work_dir, "user_output.txt"), "w", encoding="utf-8") as f:
            f.write(user_output)
        
        # 创建SPJ脚本文件
        spj_file = os.path.join(work_dir, "spj.py")
        with open(spj_file, "w", encoding="utf-8") as f:
            f.write(spj_code)
        
        # 创建本地环境
        local_env = {
            
            # 文件读取函数
            'open_input': lambda: open(os.path.join(work_dir, "input.txt"), "r", encoding="utf-8"),
            'open_expected': lambda: open(os.path.join(work_dir, "expected.txt"), "r", encoding="utf-8"),
            'open_user_output': lambda: open(os.path.join(work_dir, "user_output.txt"), "r", encoding="utf-8"),
            
            # 预读取输入和输出内容
            'input_str': input_str,
            'expected_output': expected_output, 
            'user_output': user_output,
            
            # 辅助函数和模块
            'math': math,
            'check_result': None,
            
            # 禁用危险模块
            'os': None,
            'sys': None,
            'subprocess': None,
            'shutil': None,
            'eval': None,
            'exec': None,
        }
        
        # 执行SPJ脚本
        with open(spj_file, "r", encoding="utf-8") as f:
            code = compile(f.read(), spj_file, 'exec')
            exec(code, local_env)
        
        # 获取结果
        result = local_env.get('check_result', None)
        if isinstance(result, bool):
            return result
        else:
            return bool(result) if result is not None else False
        
    except Exception as e:
        print(f"SPJ执行错误: {str(e)}")
        return False
    
    finally:
        # 清理临时目录
        if work_dir and os.path.exists(work_dir):
            try:
                for filename in os.listdir(work_dir):
                    os.remove(os.path.join(work_dir, filename))
                os.rmdir(work_dir)
            except:
                pass

#内置的几种特判方法，当SPJ脚本不可用时使用

def check_set_equal(expected_output: str, user_output: str) -> bool:
    """集合相等判断"""
    try:
        expected_set = set(expected_output.strip().split())
        user_set = set(user_output.strip().split())
        return expected_set == user_set
    except:
        return False

def check_float_equal(expected_output: str, user_output: str, epsilon: float = 1e-6) -> bool:
    """浮点数比较"""
    try:
        expected = float(expected_output.strip())
        user = float(user_output.strip())
        
        # 接近0时使用绝对误差
        if abs(expected) < epsilon:
            return abs(user - expected) < epsilon
        else:
            # 使用相对误差
            return abs((user - expected) / expected) < epsilon
    except:
        return False

def check_multi_line_float(expected_output: str, user_output: str, epsilon: float = 1e-6) -> bool:
    """多行浮点数比较"""
    expected_lines = expected_output.strip().split('\n')
    user_lines = user_output.strip().split('\n')
    
    # 行数必须相同
    if len(expected_lines) != len(user_lines):
        return False
    
    # 逐行比较浮点数
    for i in range(len(expected_lines)):
        if not check_float_equal(expected_lines[i], user_lines[i], epsilon):
            return False
    
    return True

def check_sorted_lines_equal(expected_output: str, user_output: str) -> bool:
    """排序后行相等 - 行的顺序可以不同，但内容必须一致"""
    expected_lines = sorted(line for line in expected_output.strip().split('\n') if line)
    user_lines = sorted(line for line in user_output.strip().split('\n') if line)
    
    return expected_lines == user_lines


# SPJ脚本模板示例

# # 集合比较SPJ - 忽略输出顺序
# expected_set = set(expected_output.strip().split())
# user_set = set(user_output.strip().split())
# check_result = expected_set == user_set



# # 浮点数比较SPJ - 允许误差
# try:
#     expected = float(expected_output.strip())
#     user = float(user_output.strip())
    
#     epsilon = 1e-6

#     if abs(expected) < epsilon:
#         check_result = abs(user - expected) < epsilon
#     else:
#         check_result = abs((user - expected) / expected) < epsilon
# except:
#     check_result = False