# 多模态反馈分析平台 (Multimodal Analysis Platform)

基于 FastAPI 和 Streamlit 构建的智能化用户反馈分析系统，集成了先进的自然语言处理（NLP）和计算机视觉（CV）技术，提供文本评论情感分析和图像内容智能识别功能。

## 一、核心功能

### 1. 文本评论分析 (Comment Analysis)
- **多维度筛选**：支持按情感倾向（正面/负面/中性）、评分范围、产品品类进行数据筛选。
- **情感与关键词分析**：自动进行情感分类，提取高频关键词。
- **AI 智能应对**：针对负面评价，调用 AI 自动生成专业的客服应对/整改建议。
- **历史记录管理**：
    - 自动归档每次分析记录。
    - 支持“查看历史”与“清空历史”。
    - 数据持久化，页面刷新数据不丢失。
- **UI 优化**：使用折叠面板（Expanders）管理上传和筛选区域，保持界面整洁。

### 2. 图像智能分析 (Image Analysis)
- **视觉智能分析**：
    - **对象识别**：准确识别图中物体及其置信度。
    - **场景理解**：生成详细的场景描述 (Image Captioning)。
    - **图像分类**：自动打标（如：户外、室内、办公等）。
- **OCR 文字提取**：高精度提取图像中的文本内容，并支持一键下载提取结果。
- **模型支持**：后端接入 **DashScope Qwen-VL** 大模型，提供业界领先的 90%+ 识别准确率（需配置 API Key）。

### 3. AI 智能助手 (AI Assistant)

- **智能数据识别**：自动识别已上传的数据格式和内容结构，无需手动配置。
- **一键智能分析**：上传数据后，AI 助手自动进行多维度分析，包括情感分析、关键词提取、趋势分析等。
- **个性化分析报告**：根据数据类型自动生成定制化的分析报告和可视化图表。
- **智能建议生成**：基于分析结果，自动生成业务改进建议和应对策略。
- **交互式问答**：支持自然语言交互，用户可通过对话方式获取深度分析洞察。

## 二、技术栈

- **前端**：Streamlit, Plotly, Pandas
- **后端**：FastAPI, Uvicorn
- **AI 模型**：
    - 图像：Alibaba Qwen-VL-Plus (通过 DashScope API) / Local Transformers (Fallback)
    - 文本：Jieba (分词), VaderSentiment (情感), Local LLM / Rule-based
- **数据存储**：本地 CSV 文件系统 (用于演示和轻量级持久化)

## 三、快速开始

### 1. 环境准备
确保 Python 版本 >= 3.10。

建议在新环境运行，将本地环境隔离开，防止版本冲突
```bash
# 创建conda环境
conda create -n project python=3.10.19
# 激活环境
conda activate project

# 安装依赖
pip install -r backend/requirements.txt
pip install -r frontend/requirements.txt
```

### 2. 配置 API Key
本项目图像分析依赖阿里云 DashScope API（通义千问-VL）。
请确保在环境变量中设置 `DASHSCOPE_API_KEY`。

```bash
export DASHSCOPE_API_KEY="your_api_key_here"
```

### 3. 启动后端服务 (Backend)
后端负责处理 AI 分析请求。确保先启动后端，否则前端无法进行分析。

```bash
# 打开终端窗口 1
cd backend
# 启动服务 (自动重载模式)
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```
*服务默认运行在 `http://localhost:8000`*

### 4. 启动前端应用 (Frontend)
前端提供可视化交互界面。

```bash
# 打开终端窗口 2
cd frontend
python -m streamlit run app.py
```
*应用将自动在浏览器打开，地址通常为 `http://localhost:8501`*

## 四、项目结构

```
project/
├── backend/                # FastAPI 后端服务
│   ├── api/routes/         # API 路由 (如 multimodal_analysis.py)
│   ├── models/             # 后端模型定义
│   ├── services/           # 业务逻辑服务
│   ├── main.py             # 后端应用入口
│   ├── Dockerfile          # 后端 Docker 构建文件
│   └── requirements.txt    # 后端 Python 依赖
├── frontend/               # Streamlit 前端应用
│   ├── components/         # UI 组件 (侧边栏、分析页等)
│   ├── models/             # 前端模型定义 (独立于后端)
│   ├── utils/              # 前端工具函数
│   ├── app.py              # 前端应用入口
│   ├── Dockerfile          # 前端 Docker 构建文件
│   └── requirements.txt    # 前端 Python 依赖
└── README.md               # 项目说明文档
```

## ⚠️ 注意事项
- **网络连接**：调用云端大模型需要稳定的网络连接。
- **历史数据**：生成的分析历史保存在 `frontend/data/history/` 目录下。

---
© 2026 多模态分析平台 | 版本 1.0.0
