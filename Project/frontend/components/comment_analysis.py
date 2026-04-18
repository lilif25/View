import streamlit as st
import pandas as pd
import numpy as np
import jieba
import re
from collections import Counter
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import sys
import os
import json
from streamlit.components.v1 import html
import datetime

# 添加 utils 路径
current_dir = os.path.dirname(os.path.abspath(__file__))
utils_dir = os.path.join(os.path.dirname(current_dir), 'utils')
if utils_dir not in sys.path:
    sys.path.append(utils_dir)

# Add models path
models_dir = os.path.join(os.path.dirname(current_dir), 'models')
if models_dir not in sys.path:
    sys.path.append(models_dir)

try:
    from text.qwen_model import QwenModel
except ImportError:
    QwenModel = None

try:
    from utils.data_processor import process_uploaded_data, generate_response
    from utils.storage_router import (
        archive_current_run_on_reset_data,
        clear_reset_history_runs_data,
        get_default_user_id,
        get_effective_storage_mode,
        get_storage_mode,
        list_reset_history_runs,
        load_current_data,
        load_run_data,
        save_processed_data,
    )
    from utils.layout import render_header
except ImportError:
    st.error("无法导入数据处理模块，请检查路径。")
    def process_uploaded_data(df): return df
    def generate_response(label, text, category): return "无法生成"
    def archive_current_run_on_reset_data(user_id): return None
    def clear_reset_history_runs_data(user_id, limit=1000): return 0
    def get_default_user_id(): return "00000000-0000-0000-0000-000000000001"
    def get_effective_storage_mode(): return "online"
    def get_storage_mode(): return "online"
    def list_reset_history_runs(user_id, limit=100): return []
    def load_current_data(user_id): return None
    def load_run_data(run_id): return None
    def save_processed_data(processed_df, source_filename, user_id): return None
    def render_header(title, subtitle=None): st.title(title)

def render_interactive_layout(section_id, component_map, initial_order):
    """
    使用 HTML+CSS+JS 实现的客户端真·悬浮交互布局 (支持 N 个图表轮播)
    特性：点击左侧/右侧触发轮换，带平滑动画，无需后端重绘。
    """
    # 1. 准备数据: 执行回调并将 Plotly Figure 转换为 JSON
    chart_data = {}
    valid_keys = []
    
    # Use initial_order as the source of truth for the sequence
    for key in initial_order:
        if key in component_map:
            try:
                fig = component_map[key]()
                if fig:
                    fig_dict = json.loads(fig.to_json())
                    # Clean up layout for CSS card
                    if 'layout' in fig_dict:
                        fig_dict['layout'].pop('width', None)
                        fig_dict['layout'].pop('height', None)
                        fig_dict['layout']['autosize'] = True
                        # 保留图表原有边距设置，确保标签不被遮挡
                        if 'margin' not in fig_dict['layout']:
                            fig_dict['layout']['margin'] = dict(l=120, r=40, t=60, b=130)
                        else:
                            # 如果已有边距设置，确保最小值
                            margin = fig_dict['layout']['margin']
                            margin['l'] = max(margin.get('l', 0), 120)
                            margin['r'] = max(margin.get('r', 0), 40)
                            margin['t'] = max(margin.get('t', 0), 60)
                            margin['b'] = max(margin.get('b', 0), 130)
                        fig_dict['layout']['paper_bgcolor'] = 'rgba(0,0,0,0)'
                    
                    chart_data[key] = fig_dict
                    if key not in valid_keys:
                        valid_keys.append(key)
            except Exception as e:
                print(f"Error rendering {key}: {e}")

    chart_data_js = json.dumps(chart_data)
    order_list_js = json.dumps(valid_keys)

    html_code = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <script src="https://cdn.plot.ly/plotly-2.24.1.min.js"></script>
        <style>
            body {{
                margin: 0;
                padding: 10px;
                font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
                background: transparent;
                overflow: hidden;
            }}
            .container {{
                position: relative;
                width: 100%;
                height: 800px; /* 大幅增加高度以确保下方数据完全显示 */
                perspective: 1200px;
                display: flex;
                justify-content: center;
                align-items: flex-start; /* 改为顶部对齐，避免垂直居中导致的截断 */
                padding-top: 20px; /* 减少顶部填充以提供更多下方空间 */
            }}
            
            /* 卡片基础样式 */
            .chart-card {{
                position: absolute;
                background: white;
                border: 1px solid #e5e7eb;
                border-radius: 12px;
                box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1);
                transition: all 0.6s cubic-bezier(0.25, 0.8, 0.25, 1);
                overflow: hidden;
                box-sizing: border-box;
                display: block;
                /* Default to hidden state to prevent flash */
                opacity: 0;
                transform: scale(0.8) translateY(50px);
                z-index: 0;
                pointer-events: none;
            }}
            
            /* 状态类 - 通过JS切换 */
            
            /* Center / Top Card */
            .chart-card.pos-top {{
                opacity: 1;
                width: 55%; 
                height: 650px; /* 大幅增加高度以确保下方数据完全显示 */
                transform: translateX(-50%) scale(1); /* 添加水平居中变换 */
                z-index: 20;
                left: 50%; /* 改为50%以实现精确水平居中 */
                top: 0; /* 改为顶部对齐 */
                box-shadow: 0 25px 50px -12px rgba(0, 0, 0, 0.25);
                border: 2px solid #3b82f6;
                pointer-events: auto;
            }}

            /* Left Background Card */
            .chart-card.pos-left {{
                opacity: 0.7;
                width: 45%;
                height: 650px; /* 大幅增加高度以确保下方数据完全显示 */
                transform: translateX(-110%) scale(0.9) perspective(1000px) rotateY(15deg); /* 调整水平变换以匹配新的居中方式 */
                z-index: 10;
                left: 50%; /* 改为50%以实现精确水平居中 */
                top: 20px; /* 改为顶部对齐 */
                filter: brightness(0.95);
                pointer-events: none; /* Let clicks pass through to layer */
            }}

            /* Right Background Card */
            .chart-card.pos-right {{
                opacity: 0.7;
                width: 45%;
                height: 650px; /* 大幅增加高度以确保下方数据完全显示 */
                transform: translateX(10%) scale(0.9) perspective(1000px) rotateY(-15deg); /* 调整水平变换以匹配新的居中方式 */
                z-index: 10;
                left: 50%; /* 改为50%以实现精确水平居中 */
                top: 20px; /* 改为顶部对齐 */
                filter: brightness(0.95);
                pointer-events: none;
            }}
            
            /* Hidden Card */
            .chart-card.hidden {{
                opacity: 0;
                transform: translateY(50px) scale(0.8);
                z-index: 0;
                pointer-events: none;
                display: none; /* remove from layout flow entirely if needed */
            }}

            .plot-container {{
                width: 100%;
                height: 100%;
                padding: 20px;     /* 增加内边距以确保图表标签有足够空间 */
                box-sizing: border-box;
                overflow-wrap: break-word;
                word-break: break-all;
                max-height: 100%;
                white-space: normal;
            }}

            /* 交互层 - 用于捕捉点击 */
            .nav-area {{
                position: absolute;
                top: 0;
                height: 100%;
                width: 30%;
                z-index: 30;
                cursor: pointer;
                display: flex;
                align-items: center;
                justify-content: center;
                transition: background 0.3s;
            }}
            
            .nav-left {{
                left: 0;
            }}
            
            .nav-right {{
                right: 0;
            }}
            
            .nav-area:hover {{
                background: rgba(0,0,0,0.02);
            }}
            
            /* Chevron Arrows */
            .arrow {{
                font-size: 40px;
                color: rgba(0,0,0,0.2);
                font-weight: bold;
                transition: color 0.3s;
            }}
            .nav-area:hover .arrow {{
                color: rgba(59, 130, 246, 0.6);
            }}

        </style>
    </head>
    <body>
        <div class="container" id="container">
            <!-- Navigation Areas -->
            <div class="nav-area nav-left" id="btnLeft">
                <div class="arrow">‹</div>
            </div>
            <div class="nav-area nav-right" id="btnRight">
                <div class="arrow">›</div>
            </div>
        </div>

        <script>
            const chartData = {chart_data_js};
            const orderList = {order_list_js}; // All available keys
            let activeIndex = 0; 
            
            const container = document.getElementById('container');
            const cardElements = {{}};
            const plots = {{}};

            // Initialize all cards
            orderList.forEach(key => {{
                if (!chartData[key]) return;
                
                const card = document.createElement('div');
                card.id = 'card-' + key;
                card.className = 'chart-card hidden'; 
                
                const plotDiv = document.createElement('div');
                plotDiv.className = 'plot-container';
                card.appendChild(plotDiv);
                
                // Add title overlay if needed, or rely on plotly title
                
                container.appendChild(card);
                cardElements[key] = card;
                
                // Render Plotly
                const spec = chartData[key];
                const config = {{displayModeBar: false, responsive: true, staticPlot: true}}; 
                
                Plotly.newPlot(plotDiv, spec.data, spec.layout, config).then(gd => {{
                    plots[key] = gd;
                }});
            }});

            function updateLayout() {{
                const total = orderList.length;
                if (total === 0) return;
                
                // Calculate indices
                const centerIdx = activeIndex;
                const leftIdx = (activeIndex - 1 + total) % total;
                const rightIdx = (activeIndex + 1) % total;
                
                const centerKey = orderList[centerIdx];
                const leftKey = orderList[leftIdx];
                const rightKey = orderList[rightIdx];
                
                // Reset/Assign classes
                // We iterate all to ensure ones that should be hidden get 'hidden' class
                orderList.forEach(key => {{
                    const el = cardElements[key];
                    if (!el) return;
                    
                    // Remove all pos classes first
                    el.classList.remove('pos-top', 'pos-left', 'pos-right', 'hidden');
                    
                    if (key === centerKey) {{
                        el.classList.add('pos-top');
                        el.style.display = 'block';
                    }} else if (key === leftKey) {{
                        el.classList.add('pos-left');
                        el.style.display = 'block';
                    }} else if (key === rightKey) {{
                        el.classList.add('pos-right');
                        el.style.display = 'block';
                    }} else {{
                        el.classList.add('hidden');
                        // Optional: delay display:none to allow transition out? 
                        // For simplicity, we keep display:block but opacity:0 from css
                        // Actually, 'hidden' class sets display:none or opacity:0
                    }}
                }});
                
                // Trigger resize for the visible ones to ensure they fit their new container size
                // (Center is larger than sides)
                setTimeout(() => {{
                    [centerKey, leftKey, rightKey].forEach(k => {{
                        if (plots[k]) Plotly.Plots.resize(plots[k]);
                    }});
                }}, 605); // slightly after transition
            }}

            function moveNext() {{
                activeIndex = (activeIndex + 1) % orderList.length;
                updateLayout();
            }}
            
            function movePrev() {{
                activeIndex = (activeIndex - 1 + orderList.length) % orderList.length;
                updateLayout();
            }}

            // Event Listeners
            document.getElementById('btnRight').addEventListener('click', moveNext);
            document.getElementById('btnLeft').addEventListener('click', movePrev);
            
            // Keyboard nav
            document.addEventListener('keydown', (e) => {{
                if (e.key === 'ArrowRight') moveNext();
                if (e.key === 'ArrowLeft') movePrev();
            }});

            // Initial render
            // Small delay to ensure container is ready
            setTimeout(updateLayout, 100);

        </script>
    </body>
    </html>
    """
    
    html(html_code, height=820, scrolling=False)  # 增加高度以匹配容器高度800px + 额外空间


def render_sidebar():
    """
    渲染侧边栏控制组件 (数据管理、筛选等)
    返回: filtered_df (筛选后的数据), 或 None
    """
    # -------------------------------------------------------------------------
    # 侧边栏：文本分析 (控制项)
    # -------------------------------------------------------------------------
    
    # 1. 数据管理
    with st.sidebar.expander("数据管理", expanded=False):
        default_user_id = get_default_user_id()
        
        # 自动加载历史
        if 'custom_comment_data' not in st.session_state and not st.session_state.get('data_cleared', False):
            try:
                loaded_df = load_current_data(default_user_id)
                if loaded_df is not None and not loaded_df.empty:
                    st.session_state['custom_comment_data'] = loaded_df
            except Exception as e:
                print(f"Failed to load current data from storage: {e}")

        if 'uploader_key' not in st.session_state:
            st.session_state['uploader_key'] = 0
            
        def reset_data():
            try:
                archive_current_run_on_reset_data(default_user_id)
            except Exception as e:
                st.warning(f"归档当前记录失败: {e}")

            if 'custom_comment_data' in st.session_state:
                del st.session_state['custom_comment_data']
            
            if 'viewing_history' in st.session_state:
                st.session_state['viewing_history'] = False

            st.session_state['uploader_key'] += 1
            st.session_state['data_cleared'] = True
            
        st.markdown("#### 上传新数据")
        uploaded_file = st.file_uploader(
            "选择文件 (CSV/XLSX)", 
            type=['csv', 'xlsx'], 
            key=f"uploader_{st.session_state['uploader_key']}",
            label_visibility="collapsed"
        )
        
        if uploaded_file:
            if st.button("处理并分析", use_container_width=True):
                with st.spinner("正在处理数据..."):
                    try:
                        if uploaded_file.name.endswith('.csv'):
                            raw_df = pd.read_csv(uploaded_file)
                        else:
                            raw_df = pd.read_excel(uploaded_file)
                        
                        processed_df = process_uploaded_data(raw_df)
                        try:
                            save_processed_data(
                                processed_df=processed_df,
                                source_filename=uploaded_file.name,
                                user_id=default_user_id,
                            )
                        except Exception as e:
                            st.error(f"写入存储失败: {e}")
                            raise

                        st.session_state['custom_comment_data'] = processed_df
                        st.session_state['viewing_history'] = False
                        st.session_state['data_cleared'] = False
                        st.success("数据处理完成！")
                        st.rerun()
                    except Exception as e:
                        st.error(f"处理失败: {e}")
        
        if st.button("🗑️ 重置所有数据", on_click=reset_data, use_container_width=True):
            pass

        history_header_col, history_action_col = st.columns([3, 2])
        with history_header_col:
            st.markdown("#### 历史记录")
        with history_action_col:
            clear_history_clicked = st.button("-- 清空历史记录", key="clear_history_runs", use_container_width=True)

        if clear_history_clicked:
            try:
                deleted_count = clear_reset_history_runs_data(default_user_id, limit=5000)

                if st.session_state.get('viewing_history', False):
                    st.session_state['viewing_history'] = False
                    if 'history_run_id' in st.session_state:
                        del st.session_state['history_run_id']

                    restored_df = load_current_data(default_user_id)
                    if restored_df is not None and not restored_df.empty:
                        st.session_state['custom_comment_data'] = restored_df
                    elif 'custom_comment_data' in st.session_state:
                        del st.session_state['custom_comment_data']

                st.success(f"已删除 {deleted_count} 条历史记录")
                st.rerun()
            except Exception as e:
                st.error(f"清空历史记录失败: {e}")

        history_runs = []
        try:
            history_runs = list_reset_history_runs(default_user_id, limit=100)
        except Exception as e:
            st.caption(f"历史记录加载失败: {e}")

        if not history_runs:
            st.caption("暂无重置归档历史")
        else:
            for run in history_runs:
                run_id = run.get("id")
                source_filename = run.get("source_filename") or "uploaded_data"
                created_at = run.get("created_at") or ""
                status = run.get("status") or "unknown"
                row_count = run.get("row_count") or 0
                is_current = bool(run.get("is_current"))

                display_time = created_at
                if created_at:
                    try:
                        dt = pd.to_datetime(created_at)
                        display_time = dt.strftime("%Y-%m-%d %H:%M:%S")
                    except Exception:
                        pass

                current_mark = "当前" if is_current else "历史"
                meta_line = f"{display_time} | {row_count} rows | {status}"

                title_col, action_col = st.columns([4, 1])
                with title_col:
                    st.markdown(f"**{source_filename}**")
                    st.caption(f"[{current_mark}] {meta_line}")

                with action_col:
                    view_clicked = st.button("查看", key=f"history_view_{run_id}", use_container_width=True)

                if view_clicked:
                    if not run_id:
                        st.warning("该记录缺少 run_id，无法查看。")
                    else:
                        try:
                            run_df = load_run_data(run_id)
                            if run_df is None or run_df.empty:
                                st.warning("该历史记录没有明细数据。")
                            else:
                                st.session_state['custom_comment_data'] = run_df
                                st.session_state['viewing_history'] = True
                                st.session_state['history_run_id'] = run_id
                                st.session_state['data_cleared'] = False
                                st.rerun()
                        except Exception as e:
                            st.error(f"加载历史详情失败: {e}")
                st.divider()

    # 3. 数据准备 (Dataframe Construction)
    df = None
    if 'custom_comment_data' in st.session_state:
        processed_df = st.session_state['custom_comment_data']
        sentiment_map = {"正面": "positive", "负面": "negative", "中性": "neutral"}
        
        # 构造 UI 用的 DF
        data = {
            'id': range(1, len(processed_df) + 1),
            'comment': processed_df['review_content'],
            'sentiment': processed_df['sentiment_label'].map(sentiment_map).fillna('neutral'),
            'rating': processed_df['rating'],
            'category': processed_df['product_category'],
            'solution': processed_df.get('solution', [None]*len(processed_df))
        }
        
        # Date 处理
        if 'date' in processed_df.columns:
             data['date'] = pd.to_datetime(processed_df['date'])
        else:
             # Mock dates
             mock_dates = pd.date_range(start='2023-01-01', periods=len(processed_df), freq='H')
             if len(mock_dates) < len(processed_df):
                 mock_dates = np.random.choice(mock_dates, len(processed_df))
             mock_dates_list = list(mock_dates)
             np.random.shuffle(mock_dates_list)
             data['date'] = mock_dates_list
             
        df = pd.DataFrame(data)
    
    # 4. 筛选器
    filtered_df = None
    if df is not None:
        with st.sidebar.expander("数据筛选", expanded=True):
            sentiment_options = list(df['sentiment'].unique())
            category_options = list(df['category'].unique())
            rating_min = float(df['rating'].min())
            rating_max = float(df['rating'].max())

            if st.button("清空筛选条件", key="ca_clear_filters", use_container_width=True):
                st.session_state['ca_sentiment_filter'] = sentiment_options
                st.session_state['ca_category_filter'] = category_options
                st.session_state['ca_rating_filter'] = (rating_min, rating_max)
                st.rerun()

            st.caption("情感类型")
            sentiment_filter = st.multiselect(
                "Select Sentiment",
                options=sentiment_options,
                default=sentiment_options,
                key="ca_sentiment_filter",
                label_visibility="collapsed"
            )
            
            st.caption("评分范围")
            if np.isclose(rating_min, rating_max):
                rating_filter = (rating_min, rating_max)
                st.session_state['ca_rating_filter'] = rating_filter
                st.caption(f"当前数据评分固定为 {rating_min:.2f}")
            else:
                rating_filter = st.slider(
                    "Select Rating",
                    min_value=rating_min,
                    max_value=rating_max,
                    value=(rating_min, rating_max),
                    step=0.1,
                    key="ca_rating_filter",
                    label_visibility="collapsed"
                )
            
            st.caption("产品分类")
            category_filter = st.multiselect(
                "Select Category",
                options=category_options,
                default=category_options,
                key="ca_category_filter",
                label_visibility="collapsed"
            )

            sentiment_all_selected = set(sentiment_filter) == set(sentiment_options)
            category_all_selected = set(category_filter) == set(category_options)
            rating_all_selected = np.isclose(rating_filter[0], rating_min) and np.isclose(rating_filter[1], rating_max)
            if not (sentiment_all_selected and category_all_selected and rating_all_selected):
                st.info("当前处于筛选视图，数据概览为筛选后结果。")
            
            # Apply
            filtered_df = df[
                (df['sentiment'].isin(sentiment_filter)) &
                (df['rating'].between(rating_filter[0], rating_filter[1])) &
                (df['category'].isin(category_filter))
            ].copy()
            
    # Save to session (vital for show_comment_analysis)
    st.session_state['ca_filtered_df'] = filtered_df
    return filtered_df


def show_comment_analysis(backend_url=None):
    """
    显示评论分析页面 (内容区域)
    """
    render_header("评论分析", "深度挖掘用户评论中的情感与观点")
    configured_mode = (get_storage_mode() or "hybrid").upper()
    effective_mode = (get_effective_storage_mode() or configured_mode).upper()
    st.caption(f"当前存储模式： {effective_mode}")
    
    # 检查是否处于"查看历史"模式
    is_viewing_history = st.session_state.get('viewing_history', False)
    
    if is_viewing_history:
        if st.button("🔙 退出历史查看", type="primary"):
            default_user_id = get_default_user_id()
            restored_df = None
            try:
                restored_df = load_current_data(default_user_id)
            except Exception as e:
                st.warning(f"恢复当前数据失败: {e}")

            if restored_df is not None and not restored_df.empty:
                st.session_state['custom_comment_data'] = restored_df
            elif 'custom_comment_data' in st.session_state:
                del st.session_state['custom_comment_data']
            st.session_state['viewing_history'] = False
            if 'history_run_id' in st.session_state:
                del st.session_state['history_run_id']
            st.session_state['data_cleared'] = False
            st.rerun()

    # 从 Session State 获取筛选后的数据
    filtered_df = st.session_state.get('ca_filtered_df', None)
    
    if filtered_df is None:
        st.info("👋 欢迎使用评论分析！\n\n请在左侧侧边栏上传您的 CSV/XLSX 评论数据文件以开始分析。")
        return
    
    # 显示数据概览
    st.markdown("### 数据概览")
    
    # 添加简洁居中样式
    st.markdown("""
    <style>
    .dashboard-container {
        display: grid;
        grid-template-columns: repeat(4, 1fr);
        gap: 1rem;
        margin-bottom: 2rem;
    }
    
    .dashboard-card {
        background: white;
        border: 1px solid #e5e7eb;
        border-radius: 8px;
        padding: 2rem 1rem;
        text-align: center;
        color: #1f2937;
        box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1);
        transition: all 0.3s ease;
        min-height: 140px;
        display: flex;
        flex-direction: column;
        justify-content: center;
        align-items: center;
    }
    
    .dashboard-card:hover {
        box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
        border-color: #3b82f6;
    }
    
    .card-number {
        font-size: 2rem;
        font-weight: 600;
        margin-bottom: 0.5rem;
        color: #1f2937;
    }
    
    .card-label {
        font-size: 0.9rem;
        font-weight: 500;
        color: #6b7280;
    }
    
    /* 动画效果 */
    @keyframes fadeInUp {
        from {
            opacity: 0;
            transform: translateY(20px);
        }
        to {
            opacity: 1;
            transform: translateY(0);
        }
    }
    
    .dashboard-card {
        animation: fadeInUp 0.4s ease-out;
    }
    
    .dashboard-card:nth-child(1) { animation-delay: 0.1s; }
    .dashboard-card:nth-child(2) { animation-delay: 0.2s; }
    .dashboard-card:nth-child(3) { animation-delay: 0.3s; }
    .dashboard-card:nth-child(4) { animation-delay: 0.4s; }
    </style>
    """, unsafe_allow_html=True)
    
    # 计算数据
    total_comments = len(filtered_df)
    full_comments = len(st.session_state.get('custom_comment_data', filtered_df))
    if total_comments == 0:
        avg_rating = 0.0
        positive_pct = 0.0
        negative_pct = 0.0
    else:
        avg_rating = filtered_df['rating'].mean()
        positive_pct = (filtered_df['sentiment'] == 'positive').sum() / total_comments * 100
        negative_pct = (filtered_df['sentiment'] == 'negative').sum() / total_comments * 100

    if full_comments != total_comments:
        st.caption(f"当前筛选: {total_comments:,} / 全量数据: {full_comments:,}")
    else:
        st.caption(f"当前展示全量数据: {full_comments:,}")
    
    # 创建简洁的仪表盘卡片
    st.markdown(f"""
    <div class="dashboard-container">
        <div class="dashboard-card">
            <div class="card-number">{total_comments:,}</div>
            <div class="card-label">当前筛选评论数</div>
        </div>
        <div class="dashboard-card">
            <div class="card-number">{avg_rating:.2f}</div>
            <div class="card-label">平均评分</div>
        </div>
        <div class="dashboard-card">
            <div class="card-number">{positive_pct:.1f}%</div>
            <div class="card-label">正面评论比例</div>
        </div>
        <div class="dashboard-card">
            <div class="card-number">{negative_pct:.1f}%</div>
            <div class="card-label">负面评论比例</div>
        </div>
    </div>
    """, unsafe_allow_html=True)
    st.markdown('</div>', unsafe_allow_html=True)
    
    
    # 新增：定义各个图表的渲染函数
    def render_sentiment_pie():
        sentiment_counts = filtered_df['sentiment'].value_counts().reset_index()
        sentiment_counts.columns = ['sentiment', 'count']
        
        fig_pie = px.pie(
            sentiment_counts,
            values='count',
            names='sentiment',
            color='sentiment',
            title="情感分布",
            color_discrete_map={
                'positive': '#00CC96', 
                'negative': '#EF553B', 
                'neutral': '#636EFA'
            }
        )
         # 显式设置 autosize 和居中布局
        fig_pie.update_layout(
            autosize=True,
            margin=dict(l=80, r=80, t=80, b=80),  # 均衡的边距实现居中
            paper_bgcolor='rgba(0,0,0,0)',
            plot_bgcolor='rgba(0,0,0,0)',
            legend=dict(
                x=0.5,    # 水平居中
                y=-0.1,   # 移到图表下方
                xanchor='center',
                yanchor='top',
                orientation='h',  # 水平排列
                bgcolor='rgba(255,255,255,0.8)',
                bordercolor='rgba(0,0,0,0.2)',
                borderwidth=1
            ),
            # 饼图居中设置
            uniformtext_minsize=12,
            uniformtext_mode='hide',
            showlegend=True
        )
        
        # 设置饼图在图表区域内的位置为居中
        fig_pie.update_traces(
            textposition='inside',
            textinfo='percent+label',
            insidetextorientation='radial',
            pull=0.02,  # 轻微分离效果
            marker=dict(line=dict(color='#ffffff', width=2))
        )
        
        return fig_pie

    def render_rating_bar():
        # 评分分布：使用更鲜艳的颜色，避免 Viridis 默认的深紫色/黑色
        rating_counts = filtered_df['rating'].value_counts().sort_index()
        fig_bar = px.bar(
            x=rating_counts.index,
            y=rating_counts.values,
            title="评分分布",
            labels={'x': '评分', 'y': '数量'},
            # 使用 Orange 或其他明亮色系，或者根据评分渐变
            color=rating_counts.index,
            color_continuous_scale='RdYlGn' # 红黄绿渐变，低分红高分绿
        )
        fig_bar.update_layout(coloraxis_showscale=False, margin=dict(l=120, r=40, t=60, b=80))
        fig_bar.update_yaxes(title_standoff=18)
        return fig_bar
    
    def render_sentiment_summary_bubble():
        sentiment_summary = filtered_df.groupby('sentiment').agg({
            'rating': 'mean',
            'id': 'count'
        }).rename(columns={'rating': '平均评分', 'id': '评论数'}).reset_index()
        
        fig = px.scatter(
            sentiment_summary,
            x='sentiment',
            y='平均评分',
            size='评论数',
            color='sentiment',
            title="情感摘要 (大小=数量)",
            color_discrete_map={'positive': 'green', 'negative': 'red', 'neutral': 'blue'}
        )
        fig.update_layout(
            margin=dict(l=120, r=40, t=60, b=80),
            legend=dict(
                x=0.02,  # 靠近左侧
                y=0.98,  # 靠近顶部
                xanchor='left',
                yanchor='top',
                bgcolor='rgba(255,255,255,0.8)',
                bordercolor='rgba(0,0,0,0.2)',
                borderwidth=1
            )
        )
        fig.update_yaxes(title_standoff=18)
        return fig

    
    # 类别分析定义
    def render_category_count_bar():
        category_counts = filtered_df['category'].value_counts()
        fig_cat_count = px.bar(
            x=category_counts.index,
            y=category_counts.values,
            title="各产品分类评论数量",
            labels={'x': '产品分类', 'y': '评论数量'}
        )
        fig_cat_count.update_traces(marker_color='#3b82f6')
        fig_cat_count.update_layout(margin=dict(l=120, r=40, t=60, b=80))
        fig_cat_count.update_yaxes(title_standoff=18)
        return fig_cat_count

    def render_category_sentiment_bar():
        category_sentiment = filtered_df.groupby(['category', 'sentiment']).size().unstack().fillna(0)
        cat_sentiment_long = category_sentiment.reset_index().melt(
            id_vars='category',
            var_name='sentiment',
            value_name='count'
        )
        color_map = {'positive': '#00CC96', 'negative': '#EF553B', 'neutral': '#636EFA'}
        fig_cat_sentiment = px.bar(
            cat_sentiment_long,
            x='category',
            y='count',
            color='sentiment',
            title="各产品分类情感分布",
            color_discrete_map=color_map,
            barmode='group',
            labels={'category': '产品分类', 'count': '数量', 'sentiment': '情感'}
        )
        fig_cat_sentiment.update_layout(
            margin=dict(l=120, r=40, t=60, b=80),
            legend=dict(
                x=0.02,  # 靠近左侧
                y=0.98,  # 靠近顶部
                xanchor='left',
                yanchor='top',
                bgcolor='rgba(255,255,255,0.8)',
                bordercolor='rgba(0,0,0,0.2)',
                borderwidth=1
            )
        )
        fig_cat_sentiment.update_yaxes(title_standoff=18)
        return fig_cat_sentiment

    def render_category_treemap():
        cat_summary = filtered_df.groupby('category').agg({
            'rating': 'mean',
            'id': 'count'
        }).rename(columns={'rating': '平均评分', 'id': '评论总数'}).reset_index()
        
        fig = px.treemap(
            cat_summary,
            path=['category'],
            values='评论总数',
            color='平均评分',
            title="分类统计详情 (面积=评论数)",
            color_continuous_scale='Viridis'
        )
        fig.update_layout(
            margin=dict(l=160, r=80, t=60, b=80),  # 增加左侧边距为颜色条留出空间
            coloraxis_colorbar=dict(
                x=-0.1,  # 移到图表左侧外边
                y=0.5,   # 垂直居中
                xanchor='right',
                yanchor='middle',
                title='平均评分',
                thickness=15,
                len=0.6
            )
        )
        return fig

    
    # 时间趋势分析定义
    # 按月份聚合数据 (预处理)
    filtered_df['month'] = filtered_df['date'].dt.to_period('M')
    monthly_data = filtered_df.groupby('month').agg({
        'rating': 'mean',
        'sentiment': lambda x: (x == 'positive').sum() / len(x) * 100,
        'id': 'count'
    }).reset_index().rename(columns={'id': 'count'})
    monthly_data['month'] = monthly_data['month'].dt.to_timestamp()

    def render_rating_trend_line():
        fig_rating_trend = px.line(
            monthly_data,
            x='month',
            y='rating',
            title="月度平均评分",
            markers=True,
            labels={'month': '月份', 'rating': '平均评分'}
        )
        fig_rating_trend.update_traces(line_color='#636EFA')
        fig_rating_trend.update_layout(margin=dict(l=120, r=40, t=60, b=80))
        fig_rating_trend.update_yaxes(title_standoff=18)
        return fig_rating_trend
        
    def render_sentiment_trend_line():
        fig_sentiment_trend = px.line(
            monthly_data,
            x='month',
            y='sentiment',
            title="月度正面评论比例(%)",
            markers=True,
            labels={'month': '月份', 'sentiment': '正面比例(%)'}
        )
        fig_sentiment_trend.update_traces(line_color='#00CC96')
        fig_sentiment_trend.update_layout(margin=dict(l=120, r=40, t=60, b=80))
        fig_sentiment_trend.update_yaxes(title_standoff=18)
        return fig_sentiment_trend


    def render_monthly_kpi_card():
        display_monthly = monthly_data.copy()
        display_monthly['month_str'] = display_monthly['month'].dt.strftime('%Y-%m')
        
        fig = make_subplots(rows=3, cols=1, shared_xaxes=True, vertical_spacing=0.1)
        fig.add_trace(go.Scatter(x=display_monthly['month_str'], y=display_monthly['rating'], mode='lines+markers', name='评分'), row=1, col=1)
        fig.add_trace(go.Bar(x=display_monthly['month_str'], y=display_monthly['count'], name='评论数', marker_color='#3b82f6'), row=2, col=1)
        fig.add_trace(go.Scatter(x=display_monthly['month_str'], y=display_monthly['sentiment'], mode='lines+markers', name='正面率'), row=3, col=1)
        
        fig.update_layout(title="月度综合指标", showlegend=False, margin=dict(l=120, r=40, t=60, b=80))
        fig.update_yaxes(title_standoff=18)
        return fig


    # 高频词分析定义
    
    # 文本处理逻辑 (保留原函数逻辑)
    def process_text(text):
        if not isinstance(text, str):
            return []
        stop_words = {
            '我', '你', '他', '仅', 'i', 'you', 'also', 'be', 'after',
            '的', '了', '在', '是', '有', '和', '就', '不', '人', '都', 
            '一', '一个', '上', '也', '很', '到', '说', '要', '去', '会', 
            '着', '没有', '看', '好', '自己', '这', '非常', '感觉', '觉得', 
            '比较', '这个', '那个', '我们', '你们', '他们', '它', '只是', '但是',
            'the', 'a', 'an', 'and', 'or', 'but', 'is', 'are', 'was', 'were', 
            'to', 'of', 'in', 'on', 'at', 'for', 'with', 'it', 'this', 'that', 
            'my', 'your', 'his', 'her', 'its', 'we', 'they', 'have', 'has', 'had', 
            'do', 'does', 'did', 'can', 'could', 'will', 'would', 'should', 'not', 
            'no', 'yes', 'so', 'as', 'if', 'when', 'where', 'why', 'how', 'all', 
            'any', 'some', 'very', 'good', 'bad', 'great', 'product', 'use', 'one', 
            'just', 'get', 'from', 'out', 'up', 'down', 'about', 'than', 'then', 
            'now', 'only', 'well', 'much', 'more', 'other', 'which', 'what', 
            'who', 'whom', 'whose', 'cable', 'charging', 'phone',
            'been', 'being', 'am', 'before', 'by', 'into', 'during', 'until', 
            'against', 'among', 'through', 'over', 'between', 'since', 'without', 
            'under', 'within', 'along', 'across', 'behind', 'beyond', 'around', 
            'above', 'near', 'off', 'go', 'going', 'gone', 'went', 'make', 'made', 
            'making', 'know', 'take', 'see', 'come', 'think', 'look', 'want', 
            'give', 'used', 'using', 'find', 'tell', 'ask', 'work', 'worked', 
            'working', 'seem', 'feel', 'try', 'leave', 'call', 'he', 'him', 'she', 
            'us', 'our', 'them', 'their', 'these', 'those', 'even', 'still', 'way', 
            'too', 'really', 'usb', 'type', 'fast', 'data', 'sync', 'compatible'
        }
        words = jieba.cut(text)
        result = []
        for word in words:
            word = word.strip().lower()
            if len(word) > 1 and word not in stop_words and not word.isdigit() and not re.match(r'^[^\w\s]+$', word):
                result.append(word)
        return result
    
    # 预先计算词频
    all_words = []
    for comment in filtered_df['comment']:
        all_words.extend(process_text(comment))
    word_counts = Counter(all_words)
    top_words = word_counts.most_common(20)
    top_words_df = pd.DataFrame(top_words, columns=['词汇', '频次'])
    
    # 预先计算情感关键词
    positive_comments = filtered_df[filtered_df['sentiment'] == 'positive']['comment']
    positive_words = []
    for comment in positive_comments:
        unique_words = set(process_text(comment))
        positive_words.extend(unique_words)
    positive_word_counts = Counter(positive_words).most_common(10)
    positive_words_df = pd.DataFrame(positive_word_counts, columns=['词汇', '频次'])

    negative_comments = filtered_df[filtered_df['sentiment'] == 'negative']['comment']
    negative_words = []
    for comment in negative_comments:
        unique_words = set(process_text(comment))
        negative_words.extend(unique_words)
    negative_word_counts = Counter(negative_words).most_common(10)
    negative_words_df = pd.DataFrame(negative_word_counts, columns=['词汇', '频次'])

    def render_word_freq_bar():
        if not top_words_df.empty:
            fig_words = px.bar(
                top_words_df,
                x='词汇',
                y='频次',
                title="高频词汇分布"
            )
            fig_words.update_traces(marker_color='#3b82f6')
            fig_words.update_xaxes(tickangle=45)
            fig_words.update_layout(margin=dict(l=120, r=80, t=60, b=80))  # 增加右侧边距以防止图例被遮挡
            fig_words.update_yaxes(title_standoff=18)
            return fig_words
        else:
            return None

    def render_sentiment_butterfly():
        # Top 10 Pos vs Top 10 Neg
        pos = positive_words_df.copy()
        pos['Type'] = '正面'
        neg = negative_words_df.copy()
        neg['Type'] = '负面'
        neg['频次'] = -neg['频次'] # Make negative for diverging bar
        
        combined = pd.concat([pos, neg])
        
        fig = px.bar(
            combined,
            y='词汇',
            x='频次',
            color='Type',
            orientation='h',
            title="情感关键词对比 (左负右正)",
            color_discrete_map={'正面': 'green', '负面': 'red'}
        )
        fig.update_layout(
            margin=dict(l=120, r=40, t=60, b=80),
            legend=dict(
                x=0.02,  # 靠近左侧
                y=0.98,  # 靠近顶部
                xanchor='left',
                yanchor='top',
                bgcolor='rgba(255,255,255,0.8)',
                bordercolor='rgba(0,0,0,0.2)',
                borderwidth=1
            )
        )
        fig.update_yaxes(title_standoff=18)
        return fig

    def render_top_words_treemap():
        if not top_words_df.empty:
            fig = px.treemap(
                top_words_df,
                path=['词汇'],
                values='频次',
                title="高频词汇 (面积表示频次)",
                color='频次',
                color_continuous_scale='Blues'
            )
            fig.update_layout(
                margin=dict(l=160, r=80, t=60, b=80),  # 增加左侧边距为颜色条留出空间
                coloraxis_colorbar=dict(
                    x=-0.1,  # 移到图表左侧外边
                    y=0.5,   # 垂直居中
                    xanchor='right',
                    yanchor='middle',
                    title='频次',
                    thickness=15,
                    len=0.6
                )
            )
            return fig
        else:
            return None

# ---------------- 评论搜索与智能应对 ----------------
    st.markdown('<div class="css-card">', unsafe_allow_html=True)
    st.markdown("### 评论搜索与智能应对")
    
    col_search, col_action = st.columns([4, 1])
    with col_search:
        search_keyword = st.text_input("输入关键词搜索评论...", placeholder="输入关键词搜索评论，例如：正面、负面、中性...", key="comment_search_input", label_visibility="collapsed")
    with col_action:
        do_search = st.button("搜索", use_container_width=True)
        
    if search_keyword:
        # Enhanced Filter Logic: Support Sentiment Keywords
        sentiment_map_search = {
             '正面': 'positive', 'positive': 'positive',
             '负面': 'negative', 'negative': 'negative',
             '中性': 'neutral', '中立': 'neutral', 'neutral': 'neutral'
        }
        
        lower_keyword = search_keyword.strip().lower()
        search_target_sentiment = sentiment_map_search.get(lower_keyword)
        
        if search_target_sentiment:
             search_results = filtered_df[filtered_df['sentiment'] == search_target_sentiment]
             match_msg = f"情感为 '{search_keyword}'"
        else:
             search_results = filtered_df[filtered_df['comment'].str.contains(search_keyword, case=False, na=False)]
             match_msg = f"包含 '{search_keyword}'"
        
        if not search_results.empty:
            st.success(f"找到 {len(search_results)} 条{match_msg}的评论")
            
            # 使用 container(height=...) 创建可滚动的列表视图
            # 设置合适的高度以展示约 10 条数据 (假设每条约 100px)
            search_container = st.container(height=600, border=True)
            
            with search_container:
                # Iterate all results (Container handles scrolling)
                for idx, row in search_results.iterrows():
                    # Emotion color
                    sentiment_color = "#00CC96" if row['sentiment'] == 'positive' else "#EF553B" if row['sentiment'] == 'negative' else "#636EFA"
                    sentiment_bg = "rgba(0, 204, 150, 0.1)" if row['sentiment'] == 'positive' else "rgba(239, 85, 59, 0.1)" if row['sentiment'] == 'negative' else "rgba(99, 110, 250, 0.1)"
                    sentiment_cn = "正面" if row['sentiment'] == 'positive' else "负面" if row['sentiment'] == 'negative' else "中性"
                    
                    with st.container():
                        st.markdown(f"""
                        <div style="background-color: {sentiment_bg}; padding: 12px; border-radius: 8px; margin-bottom: 12px; border-left: 5px solid {sentiment_color};">
                            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px;">
                                <span style="font-weight: bold; font-size: 0.9em; color: {sentiment_color}; background: white; padding: 2px 8px; border-radius: 4px;">{sentiment_cn}</span>
                                <span style="font-size: 0.85em; color: #666;">分类: {row['category']} | 评分: {row['rating']}</span>
                            </div>
                            <div style="font-size: 1em; color: #333; line-height: 1.5;">{row['comment']}</div>
                        </div>
                        """, unsafe_allow_html=True)
                        
                        # AI Suggestion (Only for Negative)
                        if row['sentiment'] == 'negative':
                            if st.button(f"🤖 生成智能应对建议", key=f"ai_sugg_{idx}"):
                                if QwenModel:
                                    with st.spinner("AI 正在分析并生成应对策略..."):
                                        try:
                                            api_key = os.getenv("DASHSCOPE_API_KEY")
                                            if api_key:
                                                model = QwenModel(api_key=api_key)
                                                prompt = f"针对以下电商评论生成具体的应对措施和回复建议。评论：'{row['comment']}'。分类：{row['category']}。情感：{sentiment_cn}。请给出：1.潜在问题分析 2.建议回复话术 3.改进措施。"
                                                response = model.predict(prompt)
                                                if response.get("status") == "success":
                                                    st.info(response.get("text"))
                                                else:
                                                    st.error(f"生成失败: {response.get('text')}")
                                            else:
                                                st.warning("未检测到 API Key，请检查环境配置。")
                                        except Exception as e:
                                            st.error(f"处理出错: {str(e)}")
                                else:
                                    st.warning("AI 模型组件未加载")
                        
                        st.markdown("---") # Separator
        else:
            st.warning(f"未找到包含 '{search_keyword}' 的评论")
            
    st.markdown('</div>', unsafe_allow_html=True)

    # ---------------- 文本分析交互式布局 ----------------
    st.markdown('<div class="css-card">', unsafe_allow_html=True)
    st.markdown("### 文本分析互动视图")

    render_interactive_layout(
        section_id="keyword_analysis",
        component_map={
            'pie_chart': render_sentiment_pie,
            'bar_chart': render_rating_bar,
            'summary_plot': render_sentiment_summary_bubble,
            'cat_count_bar': render_category_count_bar,
            'cat_sentiment_bar': render_category_sentiment_bar,
            'cat_treemap': render_category_treemap,
            'rating_line': render_rating_trend_line,
            'sentiment_line': render_sentiment_trend_line,
            'monthly_plot': render_monthly_kpi_card,
            'word_bar': render_word_freq_bar,
            'word_treemap': render_top_words_treemap,
            'sentiment_bar': render_sentiment_butterfly
        },
        initial_order=['pie_chart', 'bar_chart', 'summary_plot', 'cat_count_bar', 'cat_sentiment_bar', 'cat_treemap' ,'summary_plot', 'cat_count_bar', 'cat_sentiment_bar', 'cat_treemap', 'rating_line', 'sentiment_line', 'monthly_plot', 'word_bar', 'word_treemap', 'sentiment_bar']
    )
    st.markdown('</div>', unsafe_allow_html=True)