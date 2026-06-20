"""HR Resume Filter — Streamlit 主程序"""

import os
import streamlit as st
from dotenv import load_dotenv

from jd_parser import parse_jd_text, parse_jd_pdf
from resume_parser import ResumeFile, parse_resume_pdf, format_file_size
from scorer import score_resume
from utils import build_results_dataframe, export_to_csv, export_to_excel

# 加载环境变量
load_dotenv()

# 页面配置
st.set_page_config(
    page_title="HR 简历筛选工具",
    page_icon="📋",
    layout="wide",
)

# ─── Session State 初始化 ───────────────────────────────
if "jd_text" not in st.session_state:
    st.session_state.jd_text = ""
if "resume_files" not in st.session_state:
    st.session_state.resume_files = []  # List[ResumeFile]
if "results" not in st.session_state:
    st.session_state.results = []       # List[dict]


# ─── 侧边栏 ─────────────────────────────────────────────
with st.sidebar:
    st.markdown("## 📋 HR 简历筛选工具")
    st.markdown("---")
    st.markdown("""
    ### 使用说明

    1. **上传 JD** — 粘贴岗位描述或上传 PDF
    2. **上传简历** — 批量上传候选人简历（PDF）
    3. **开始筛选** — AI 自动评分排名

    ### 注意事项

    - 单次最多处理 **20 份**简历
    - 支持 PDF 格式
    - 评分范围 40-95 分
    - 绿色 ≥80 | 黄色 60-79 | 红色 <60
    """)

    st.markdown("---")
    st.markdown("### ⚙️ 设置")

    # 模型选择：从环境变量读取默认值
    default_model = os.getenv("MODEL_NAME", "deepseek-chat")
    model_name = st.text_input("模型名称", value=default_model)

    api_key = st.text_input(
        "API Key",
        value=os.getenv("API_KEY", ""),
        type="password",
    )

    base_url = st.text_input("API 地址", value=os.getenv("BASE_URL", "https://api.deepseek.com"))

    st.markdown("---")
    st.caption("Made with ❤️ | 非商用部署")


# ─── 主区域：三步流程 ──────────────────────────────────

st.title("📄 HR 简历筛选工具")
st.markdown("---")

# ─── Step 1: 上传 JD ────────────────────────────────────
st.header("Step 1: 上传岗位描述（JD）")

col1, col2 = st.columns([3, 1])

with col1:
    st.text_area(
        "粘贴 JD 文本",
        value=st.session_state.jd_text,
        height=200,
        placeholder="在此粘贴岗位描述...",
        key="jd_text",
        label_visibility="collapsed",
    )

with col2:
    st.markdown("**或上传 PDF 文件**")
    uploaded_jd = st.file_uploader(
        "上传 JD PDF",
        type=["pdf"],
        label_visibility="collapsed",
        key="jd_uploader",
    )

    if uploaded_jd is not None:
        try:
            extracted = parse_jd_pdf(uploaded_jd.read())
            st.session_state.jd_text = extracted
            st.rerun()
        except ValueError as e:
            st.error(f"JD 解析失败: {e}")

# 显示已输入的 JD 文本统计
if st.session_state.jd_text.strip():
    st.info(f"✅ JD 已录入，共 {len(st.session_state.jd_text)} 字")
else:
    st.warning("请粘贴 JD 文本或上传 PDF 文件")

st.markdown("---")

# ─── Step 2: 上传简历 ───────────────────────────────────
st.header("Step 2: 上传候选人简历（PDF）")

uploaded_files = st.file_uploader(
    "批量上传简历 PDF",
    type=["pdf"],
    accept_multiple_files=True,
    label_visibility="collapsed",
    key="resume_uploader",
)

if uploaded_files:
    # 校验数量
    if len(uploaded_files) > 20:
        st.error(f"单次最多上传 20 份简历，当前 {len(uploaded_files)} 份")
    else:
        # 只处理新文件（不在 session_state 中的）
        existing_names = {r.filename for r in st.session_state.resume_files}
        new_files = []
        for f in uploaded_files:
            if f.name not in existing_names:
                new_files.append(ResumeFile(
                    filename=f.name,
                    size_bytes=f.size or 0,
                ))

        if new_files:
            # 建立文件名到 UploadedFile 的映射
            uploaded_lookup = {f.name: f for f in uploaded_files}
            for rf in new_files:
                try:
                    uploaded_file = uploaded_lookup.get(rf.filename)
                    if uploaded_file is None:
                        raise ValueError("无法找到上传的文件数据")
                    rf.text = parse_resume_pdf(uploaded_file.read())
                    rf.status = "已完成"
                except ValueError as e:
                    rf.error = str(e)
                    rf.status = "失败"

            st.session_state.resume_files.extend(new_files)

        # 显示文件列表
        if st.session_state.resume_files:
            status_data = []
            for rf in st.session_state.resume_files:
                status_data.append({
                    "文件名": rf.filename,
                    "大小": format_file_size(rf.size_bytes),
                    "状态": rf.status,
                    "备注": rf.error or "",
                })
            st.dataframe(status_data, use_container_width=True, hide_index=True)

else:
    st.session_state.resume_files = []

st.markdown("---")

# ─── Step 3: 开始筛选 ───────────────────────────────────
st.header("Step 3: 开始筛选")

# 校验条件
jd_ready = bool(st.session_state.jd_text.strip())
resume_ready = len(st.session_state.resume_files) > 0
resumes_all_parsed = all(
    rf.status in ("已完成", "失败") for rf in st.session_state.resume_files
)

if not jd_ready:
    st.warning("⏳ 请先完成 Step 1: 上传 JD")
elif not resume_ready:
    st.warning("⏳ 请先完成 Step 2: 上传简历")
elif not resumes_all_parsed:
    st.warning("⏳ 简历解析中，请稍候...")
else:
    # 过滤掉解析失败的简历
    valid_resumes = [rf for rf in st.session_state.resume_files if rf.status == "已完成" and rf.text]

    if st.button("🚀 开始筛选", type="primary", use_container_width=True):
        if not api_key:
            st.error("请在侧边栏配置 API Key")
        else:
            # 进度条
            progress_bar = st.progress(0, text="准备开始...")
            status_text = st.empty()

            total = len(valid_resumes)
            results = []

            for i, rf in enumerate(valid_resumes):
                # 更新进度
                progress = (i + 1) / total
                progress_bar.progress(progress, text=f"正在筛选: {rf.filename} ({i + 1}/{total})")
                status_text.info(f"⏳ 第 {i + 1}/{total} 份: {rf.filename}")

                # 调用 LLM 评分
                result = score_resume(
                    jd_text=st.session_state.jd_text,
                    resume_text=rf.text,
                    api_key=api_key,
                    base_url=base_url,
                    model_name=model_name,
                )

                result_dict = result.to_dict()
                result_dict["filename"] = rf.filename
                results.append(result_dict)

            progress_bar.progress(1.0, text="筛选完成！")
            status_text.success("✅ 全部筛选完成！")

            st.session_state.results = results

# ─── 结果展示 ───────────────────────────────────────────
if st.session_state.results:
    st.markdown("---")
    st.header("📊 筛选排名结果")

    df = build_results_dataframe(st.session_state.results)

    # 条件着色
    def color_score(val):
        if val == "-":
            return "color: gray"
        score = int(val)
        if score >= 80:
            return "color: green; font-weight: bold"
        elif score >= 60:
            return "color: orange; font-weight: bold"
        else:
            return "color: red; font-weight: bold"

    styled_df = df.style.map(color_score, subset=["匹配分数"])
    st.dataframe(styled_df, use_container_width=True, hide_index=True)

    # 导出按钮
    col1, col2 = st.columns(2)
    with col1:
        csv_data = export_to_csv(df)
        st.download_button(
            label="📥 导出 CSV",
            data=csv_data,
            file_name="筛选结果.csv",
            mime="text/csv",
            use_container_width=True,
        )
    with col2:
        excel_data = export_to_excel(df)
        st.download_button(
            label="📥 导出 Excel",
            data=excel_data,
            file_name="筛选结果.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True,
        )
