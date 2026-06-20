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
- 使用严格的JSON格式，不包含markdown代码块、不包含任何额外文字
- 字段名必须为小写驼峰：score, top_reasons, red_flags
- top_reasons和red_flags必须是数组，即使没有内容也要返回空数组
- 不要使用中文引号，一律使用ASCII双引号"""


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
请严格按上述规则打分，只返回纯JSON，不要markdown代码块包裹，不要任何额外文字。"""


def _clean_response_text(text: str) -> str:
    """预处理 LLM 返回文本，清洗脏数据

    处理顺序：
    1. 替换 Unicode 花引号为 ASCII 标准双引号
    2. 移除零宽字符
    3. 移除 JSON 中的尾部逗号
    4. 如果没有 { 则返回空（不可能提取）
    5. 如果整体不是以 { 开头，用正则提取 {...} 部分

    Args:
        text: LLM 原始返回文本

    Returns:
        清洗后尽可能接近纯 JSON 的字符串，失败返回 ""
    """
    if not text or not text.strip():
        return ""

    t = text.strip()

    # 替换各种 Unicode 花/弯引号为 ASCII 标准双引号
    quote_pairs = {
        "“": '"',   # " (LEFT DOUBLE QUOTATION MARK)
        "”": '"',   # " (RIGHT DOUBLE QUOTATION MARK)
        "„": '"',   # „ (DOUBLE LOW-9 QUOTATION MARK)
        "‟": '"',   # ‟ (DOUBLE HIGH-REVERSED-9 QUOTATION MARK)
        "‘": "'",   # ' (LEFT SINGLE QUOTATION MARK)
        "’": "'",   # ' (RIGHT SINGLE QUOTATION MARK)
        "「": '"',   # 「 (LEFT CORNER BRACKET)
        "」": '"',   # 」 (RIGHT CORNER BRACKET)
        "『": '"',   # 『 (LEFT WHITE CORNER BRACKET)
        "』": '"',   # 』 (RIGHT WHITE CORNER BRACKET)
        "＂": '"',   # ＂ (FULLWIDTH QUOTATION MARK)
    }
    for old, new in quote_pairs.items():
        t = t.replace(old, new)

    # 替换中文冒号为标准冒号
    t = t.replace("：", ":")

    # 移除非法的控制字符（保留 \t \n \r）
    t = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', '', t)

    # 移除零宽字符
    zero_width = [
        "​",  # ZERO WIDTH SPACE
        "‌",  # ZERO WIDTH NON-JOINER
        "‍",  # ZERO WIDTH JOINER
        "﻿",  # BOM / ZERO WIDTH NO-BREAK SPACE
        "‎",  # LEFT-TO-RIGHT MARK
        "‏",  # RIGHT-TO-LEFT MARK
        "⁠",  # WORD JOINER
    ]
    for ch in zero_width:
        t = t.replace(ch, "")

    # 移除多余的尾部逗号（在 } 或 ] 之前）
    t = re.sub(r',\s*([}\]])', r'\1', t)

    # 如果文本中没有 {，无法提取 JSON
    if "{" not in t:
        return ""

    # 如果整体不是以 { 开头，尝试提取第一个 { 到最后一个 } 的内容
    if not t.startswith("{"):
        brace_match = re.search(r'\{.*\}', t, re.DOTALL)
        if brace_match:
            t = brace_match.group(0).strip()
        else:
            return ""

    return t


def _parse_score_response(response_text: str) -> dict:
    """解析 LLM 返回的 JSON，有多层容错处理

    解析链：清洗 → 直接解析 → 字符级修复 → ```json```提取 → {.}提取

    Args:
        response_text: LLM 的原始返回文本

    Returns:
        解析后的字典，含 score, top_reasons, red_flags
    """
    text = response_text.strip()
    if not text:
        return _default_fallback("LLM 返回内容为空")

    # ─── 第一层：清洗后直接解析 ───
    cleaned = _clean_response_text(text)
    if cleaned:
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            pass

    # ─── 第二层：字符级修复 ───
    # 常见问题：属性名和字符串值用了单引号、True/False/None 未转小写
    fixed = cleaned or text
    try:
        # 在 JSON 结构内部将所有单引号替换为双引号
        # （中文文本没有英文所有格如 don't 的问题，安全）
        obj_match = re.search(r'\{.*\}', fixed, re.DOTALL)
        if obj_match:
            json_part = obj_match.group(0)
            json_part = json_part.replace("'", '"')
            json_part = json_part.replace("True", "true").replace("False", "false").replace("None", "null")
            fixed = fixed[:obj_match.start()] + json_part + fixed[obj_match.end():]
        return json.loads(fixed)
    except json.JSONDecodeError:
        pass

    # ─── 第三层：尝试提取 ```json ... ``` 包裹的内容 ───
    json_match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', text, re.DOTALL)
    if json_match:
        try:
            inner = _clean_response_text(json_match.group(1))
            if inner:
                return json.loads(inner)
        except json.JSONDecodeError:
            pass

    # ─── 第四层：提取第一个 { 到最后一个 } ───
    brace_match = re.search(r'\{.*\}', text, re.DOTALL)
    if brace_match:
        try:
            inner = _clean_response_text(brace_match.group(0))
            if inner:
                return json.loads(inner)
        except json.JSONDecodeError:
            pass

    # ─── 全部失败 ───
    return _default_fallback("LLM 返回格式异常")


def _default_fallback(reason: str) -> dict:
    """生成默认兜底结果"""
    return {
        "score": 0,
        "top_reasons": [f"解析失败：{reason}"],
        "red_flags": ["需人工复核"],
    }


def _normalize_result(parsed: dict) -> dict:
    """规范化解析结果，确保字段类型和值的合法性

    Args:
        parsed: 解析后的原始字典

    Returns:
        规范化后的字典
    """
    result = {}

    # ─── score: 确保是 int 且在 0-100 范围内 ───
    score = parsed.get("score", 0)
    if score is None:
        score = 0
    if not isinstance(score, (int, float)):
        try:
            score = int(str(score).strip())
        except (ValueError, TypeError):
            score = 0
    score = int(score)
    score = max(0, min(100, score))  # 夹紧到 [0, 100]
    result["score"] = score

    # ─── top_reasons: 确保是 list ───
    reasons = parsed.get("top_reasons", [])
    if reasons is None:
        reasons = []
    if isinstance(reasons, str):
        # 尝试按换行或中文顿号/逗号分割
        reasons = re.split(r'[\n,，、;；]+', reasons)
        reasons = [r.strip() for r in reasons if r.strip()]
    if not isinstance(reasons, list):
        reasons = [str(reasons)]
    if len(reasons) == 0:
        reasons = ["暂无突出匹配项"]
    result["top_reasons"] = reasons[:3]  # 最多保留 3 条

    # ─── red_flags: 确保是 list ───
    flags = parsed.get("red_flags", [])
    if flags is None:
        flags = []
    if isinstance(flags, str):
        flags = re.split(r'[\n,，、;；]+', flags)
        flags = [f.strip() for f in flags if f.strip()]
    if not isinstance(flags, list):
        flags = [str(flags)]
    result["red_flags"] = flags

    return result


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
        normalized = _normalize_result(parsed)

        return ScoreResult(
            score=normalized["score"],
            top_reasons=normalized["top_reasons"],
            red_flags=normalized["red_flags"],
            raw_response=raw,
        )

    except Exception as e:
        return ScoreResult(
            score=0,
            top_reasons=["LLM 调用失败"],
            red_flags=[f"错误: {str(e)}"],
            error=str(e),
        )
