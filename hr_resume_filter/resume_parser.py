"""简历 PDF 批量解析模块"""

from pypdf import PdfReader
import io
from dataclasses import dataclass
from typing import Optional


@dataclass
class ResumeFile:
    """单份简历文件的完整信息"""
    filename: str           # 原始文件名
    size_bytes: int         # 文件大小（字节）
    text: Optional[str] = None   # 提取的纯文本（解析后赋值）
    status: str = "待处理"  # 待处理 / 解析中 / 已完成 / 失败
    error: Optional[str] = None  # 错误信息


def parse_resume_pdf(file_bytes: bytes) -> str:
    """从 PDF 中提取简历文本

    Args:
        file_bytes: PDF 文件的二进制内容

    Returns:
        提取的纯文本

    Raises:
        ValueError: 解析失败
    """
    try:
        pdf = PdfReader(io.BytesIO(file_bytes))
        pages = []
        for page in pdf.pages:
            text = page.extract_text()
            if text:
                pages.append(text.strip())
        result = "\n".join(pages).strip()
        if not result:
            raise ValueError("PDF 中未提取到文本内容")
        return result
    except Exception as e:
        raise ValueError(f"PDF 解析失败: {str(e)}")


def format_file_size(size_bytes: int) -> str:
    """格式化文件大小显示

    Args:
        size_bytes: 文件字节数

    Returns:
        人类可读的大小字符串，如 "245 KB"
    """
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.0f} KB"
    else:
        return f"{size_bytes / (1024 * 1024):.1f} MB"
