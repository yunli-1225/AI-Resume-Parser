# HR Resume Filter

基于 AI 的简历筛选工具，帮助 HR 从批量简历中快速筛选出与岗位匹配的候选人。

## 快速开始

1. 安装依赖
   ```bash
   cd hr_resume_filter
   pip install -r requirements.txt
   ```

2. 配置环境变量
   ```bash
   cp .env.example .env
   # 编辑 .env，填入你的 API Key
   ```

3. 启动应用
   ```bash
   streamlit run app.py
   ```

## 使用说明

1. **Step 1** — 粘贴或上传岗位描述（JD）
2. **Step 2** — 批量上传候选人简历（PDF，最多 20 份）
3. **Step 3** — 点击"开始筛选"，等待 AI 评分
4. 查看排名表格，导出 CSV/Excel

## 部署

支持部署到 Streamlit Community Cloud、Railway、Render 或自建 VPS。
