"""工具函数：导出、文件名校验等"""

import io
import pandas as pd
from typing import List, Dict


def extract_candidate_name(filename: str) -> str:
    """从文件名提取候选人姓名

    去掉 .pdf 后缀，去掉常见分隔符（_  -  ），取第一部分作为姓名

    Args:
        filename: 原始文件名，如 "张三_简历.pdf" 或 "李四-2024.pdf"

    Returns:
        提取的姓名，如 "张三"
    """
    name = filename.rsplit(".", 1)[0]  # 去后缀
    # 按常见分隔符分割，取第一部分
    for sep in ["_", "-", "—", " ", "：", ":"]:
        parts = name.split(sep)
        if len(parts) > 1:
            return parts[0].strip()
    return name.strip()


def build_results_dataframe(results: List[Dict]) -> pd.DataFrame:
    """将评分结果组装为排名表格

    Args:
        results: ScoreResult.to_dict() 列表，含 filename 字段

    Returns:
        排好序的 DataFrame，列：序号、候选人姓名、匹配分数、Top3匹配理由、风险提示
    """
    rows = []
    for r in results:
        rows.append({
            "候选人姓名": extract_candidate_name(r.get("filename", "")),
            "匹配分数": r.get("score", 0) if r.get("score", 0) > 0 else "-",
            "Top3匹配理由": "\n".join(r.get("top_reasons", [])),
            "风险提示": "\n".join(r.get("red_flags", [])),
        })

    if not rows:
        return pd.DataFrame(columns=["序号", "候选人姓名", "匹配分数", "Top3匹配理由", "风险提示"])

    df = pd.DataFrame(rows)

    # 按分数降序排列（分数为 "-" 的排在最后）
    def sort_key(val):
        if val == "-":
            return -1
        return int(val)

    df["_sort"] = df["匹配分数"].apply(sort_key)
    df = df.sort_values("_sort", ascending=False).drop(columns="_sort")
    df.insert(0, "序号", range(1, len(df) + 1))

    return df


def export_to_csv(df: pd.DataFrame) -> bytes:
    """导出为 CSV

    Args:
        df: 排名表格 DataFrame

    Returns:
        CSV 字节数据
    """
    return df.to_csv(index=False, encoding="utf-8-sig").encode("utf-8-sig")


def export_to_excel(df: pd.DataFrame) -> bytes:
    """导出为 Excel

    Args:
        df: 排名表格 DataFrame

    Returns:
        Excel 文件的字节数据（xlsx 格式）
    """
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="筛选结果")
    return output.getvalue()
