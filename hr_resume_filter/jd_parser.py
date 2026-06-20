"""JD 解析模块：处理文本粘贴或 PDF 上传"""

from pypdf import PdfReader
import io


def parse_jd_text(text: str) -> str:
    """校验并返回 JD 文本

    Args:
        text: 用户粘贴的 JD 文本

    Returns:
        去除首尾空白的文本

    Raises:
        ValueError: 文本为空
    """
    stripped = text.strip()
    if not stripped:
        raise ValueError("JD 文本不能为空")
    return stripped


def parse_jd_pdf(file_bytes: bytes) -> str:
    """从 PDF 文件中提取 JD 文本

    Args:
        file_bytes: PDF 文件的二进制内容

    Returns:
        提取的纯文本

    Raises:
        ValueError: PDF 无内容或解析失败
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
