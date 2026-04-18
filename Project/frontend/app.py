# View/frontend/app.py
import streamlit as st
import os
import requests

# 设置 API Key 环境变量 (用户配置)
os.environ["DASHSCOPE_API_KEY"] = "sk-6285b3701d014538b142e05637c14b5b"

# 设置页面配置
st.set_page_config(
    page_title="多模态分析平台",
    page_icon="📝",
    layout="wide",
    initial_sidebar_state="expanded"
)

BACKEND_URL = st.secrets.get("BACKEND_URL", "http://114.132.163.125:8000")

from components.comment_analysis import show_comment_analysis
from components.image_analysis import show_image_analysis
from components.home import show_home
from components.sidebar_navigation import create_custom_sidebar
from utils.styles import load_css

# 加载全局样式
load_css()

# 定义页面映射
PAGES = {
    "首页": show_home,
    "文本分析": show_comment_analysis,
    "图像分析": show_image_analysis
}

def main():
    # 使用自定义侧边导航栏
    current_page = create_custom_sidebar()
    
    # 显示选定的页面
    if current_page in PAGES:
        page_function = PAGES[current_page]
        page_function(BACKEND_URL)
    else:
        st.error(f"页面 '{current_page}' 不存在")

    # 在所有侧边栏内容之后添加页脚
    st.sidebar.markdown("""
    <div style='margin-top: 20px; text-align: center; color: #6c757d; font-size: 0.8rem;'>
        © 2026 多模态分析平台<br>
        版本 1.0.0
    </div>
    """, unsafe_allow_html=True)

if __name__ == "__main__":
    main()
