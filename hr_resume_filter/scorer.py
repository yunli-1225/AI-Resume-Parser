"""LLM 评分模块：调用 OpenAI 兼容 API 进行简历评分"""

import json
import re
from dataclasses import dataclass, asdict
from typing import Optional
from openai import OpenAI


# System Prompt（复用原项目评分逻辑思路）
SYSTEM_PROMPT = """你是一位资深校招HR，擅长从简历中快速识别候选人与岗位的匹配度。

你的评分逻辑：
1. 硬性门槛（30分）：学历、专业、毕业时间是否满足JD要求
2. 技能匹配（30分）：JD中列出的硬技能关键词在简历中出现了多少
3. 经验相关性（30分）：实习/项目经历与岗位方向的吻合度
4. 加分项（10分）：竞赛获奖、优质作品集、论文等

强制约束：
- 分数须覆盖40-95分区间，平均分控制在65左右
- 输出格式必须为严格JSON"""


@dataclass
class ScoreResult:
    """评分结果"""
    score: int = 0
    top_reasons: list = None
    red_flags: list = None
    raw_response: Optional[str] = None
    error: Optional[str] = None

    def __post_init__(self):
        if self.top_reasons is None:
            self.top_reasons = []
        if self.red_flags is None:
            self.red_flags = []

    def to_dict(self):
        return asdict(self)


def _build_user_prompt(jd_text: str, resume_text: str) -> str:
    """组装 User Prompt"""
    return f"""【岗位JD】
{jd_text}
【候选人简历】
{resume_text}
请按上述规则打分，只返回JSON，不要额外文字。"""


def _parse_score_response(response_text: str) -> dict:
    """解析 LLM 返回的 JSON，有容错处理

    Args:
        response_text: LLM 的原始返回文本

    Returns:
        解析后的字典，含 score, top_reasons, red_flags
    """
    # 尝试直接解析
    text = response_text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # 尝试提取 ```json ... ``` 包裹的内容
    json_match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', text, re.DOTALL)
    if json_match:
        try:
            return json.loads(json_match.group(1))
        except json.JSONDecodeError:
            pass

    # 尝试提取第一个 { 到最后一个 }
    brace_match = re.search(r'\{.*\}', text, re.DOTALL)
    if brace_match:
        try:
            return json.loads(brace_match.group(0))
        except json.JSONDecodeError:
            pass

    # 全部失败，返回默认值
    return {
        "score": 0,
        "top_reasons": ["解析失败：LLM 返回格式异常"],
        "red_flags": ["需人工复核"]
    }


def score_resume(
    jd_text: str,
    resume_text: str,
    api_key: str,
    base_url: str,
    model_name: str,
    temperature: float = 0.1
) -> ScoreResult:
    """调用 LLM 对单份简历进行评分

    Args:
        jd_text: JD 文本
        resume_text: 简历文本
        api_key: API 密钥
        base_url: API 地址
        model_name: 模型名称
        temperature: 温度参数，默认 0.1

    Returns:
        ScoreResult 对象
    """
    try:
        client = OpenAI(api_key=api_key, base_url=base_url)

        response = client.chat.completions.create(
            model=model_name,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": _build_user_prompt(jd_text, resume_text)},
            ],
            temperature=temperature,
        )

        raw = response.choices[0].message.content or ""
        parsed = _parse_score_response(raw)

        return ScoreResult(
            score=parsed.get("score", 0),
            top_reasons=parsed.get("top_reasons", []),
            red_flags=parsed.get("red_flags", []),
            raw_response=raw,
        )

    except Exception as e:
        return ScoreResult(
            score=0,
            top_reasons=["LLM 调用失败"],
            red_flags=[f"错误: {str(e)}"],
            error=str(e),
        )
