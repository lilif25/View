import streamlit as st
import sys
import os

# Add models path
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(os.path.dirname(os.path.dirname(current_dir)))
models_dir = os.path.join(project_root, 'View', 'models')

if models_dir not in sys.path:
    sys.path.append(models_dir)

try:
    from text.qwen_model import QwenModel
except ImportError:
    pass

def show_ai_assistant(backend_url=None):
    # 检查是否有已上传的数据
    uploaded_data = st.session_state.get('custom_comment_data', None)
    
    if uploaded_data is not None:
        st.info(f"📊 已检测到上传的数据：{len(uploaded_data)} 行，{len(uploaded_data.columns)} 列")
        st.session_state['data_context'] = {
            "has_data": True,
            "rows": len(uploaded_data),
            "columns": list(uploaded_data.columns),
            "preview": uploaded_data.head(10).to_string()
        }
    else:
        st.session_state['data_context'] = {"has_data": False}
    
    st.title("🤖 AI 智能助手 (Qwen)")
    st.markdown("基于通义千问大模型的智能对话助手")
    
    # Sidebar configuration
    with st.sidebar:
        st.divider()
        st.header("🤖 模型配置")
        api_key = st.text_input("DashScope API Key", type="password", help="请输入阿里云 DashScope API Key")
        model_select = st.selectbox("选择模型", ["qwen-turbo", "qwen-plus", "qwen-max"], index=0)
        
        if api_key:
            os.environ["DASHSCOPE_API_KEY"] = api_key
        
        if st.button("清除对话历史"):
            st.session_state.messages = []
            st.rerun()
    
    # Initialize chat history
    if "messages" not in st.session_state:
        st.session_state.messages = []

    # Display chat messages from history
    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])

    # React to user input
    if prompt := st.chat_input("有什么可以帮您的吗？"):
        # 获取数据上下文
        data_context = st.session_state.get('data_context', {"has_data": False})
        
        # 如果有数据，构建包含数据的 prompt
        if data_context.get("has_data"):
            full_prompt = f"""
【当前已上传的数据】
数据行数：{data_context['rows']}
数据列名：{', '.join(data_context['columns'])}
数据预览（前10行）：
{data_context['preview']}

【用户问题】
{prompt}

请基于以上数据回答用户的问题。如果用户要求分析数据，请使用这些数据进行分析。
"""
        else:
            full_prompt = prompt
        
        # Display user message
        st.chat_message("user").markdown(prompt)
        st.session_state.messages.append({"role": "user", "content": prompt})

        # Call Qwen Model
        with st.chat_message("assistant"):
            message_placeholder = st.empty()
            message_placeholder.markdown("Thinking...")
            
            try:
                from text.qwen_model import QwenModel
                
                model = QwenModel(api_key=api_key, model_name=model_select, use_local_fallback=True)
                history = st.session_state.messages[:-1]
                
                # 使用包含数据的 full_prompt
                response = model.predict(full_prompt, history=history)
                
                if response.get("status") == "success":
                    full_response = response.get("text", "")
                    message_placeholder.markdown(full_response)
                    st.session_state.messages.append({"role": "assistant", "content": full_response})
                else:
                    error_msg = response.get("text", "未知错误")
                    message_placeholder.error(error_msg)
                    if "API Key missing" in error_msg:
                        st.info("请在左侧侧边栏输入您的 DashScope API Key。")
            except Exception as e:
                message_placeholder.error(f"发生错误: {str(e)}")