"""
本地模型类 - 实现完全离线的 AI 能力
使用 Ollama 运行本地模型，无需联网
"""

from typing import Dict, Any, List
import subprocess
import logging
import re

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class LocalModel:
    """
    本地模型类
    调用 Ollama 运行的 qwen2 模型实现完全离线推理
    """
    
    def __init__(self, model_name: str = "qwen2:0.5b"):
        self.model_name = model_name
        logger.info(f"本地模型初始化完成，使用模型: {model_name}")
    
    def _clean_response(self, text: str) -> str:
        """清理模型输出中的控制字符和乱码"""
        if not text:
            return text
        
        # 移除 ANSI 转义序列 (\x1b[...m 等)
        ansi_escape = re.compile(r'\x1B\[[0-?]*[ -/]*[@-~]')
        text = ansi_escape.sub('', text)
        
        # 移除常见的控制字符序列 (如 [K, [D, [C 等)
        control_chars = re.compile(r'\[\d+[A-Za-z]|\[\w')
        text = control_chars.sub('', text)
        
        # 移除光标移动序列
        cursor_moves = re.compile(r'\x1b\[\d+[A-Za-z]')
        text = cursor_moves.sub('', text)
        
        # 移除多余的空格和换行
        text = re.sub(r'\n{3,}', '\n\n', text)
        
        return text.strip()
    
    def predict(self, text: str, history: List[Dict] = None) -> Dict[str, Any]:
        """
        调用本地模型进行推理
        """
        try:
            # 构建 prompt
            prompt = self._build_prompt(text, history)
            
            # 调用 Ollama 命令行
            result = subprocess.run(
                ["ollama", "run", self.model_name, prompt],
                capture_output=True,
                text=True,
                encoding='utf-8',
                timeout=120
            )
            
            if result.returncode == 0:
                response = result.stdout.strip()
                # 清理控制字符
                response = self._clean_response(response)
                
                return {
                    "status": "success",
                    "text": response if response else "模型没有生成回复",
                    "source": "local"
                }
            else:
                return {
                    "status": "error",
                    "text": f"模型调用失败: {result.stderr}",
                    "source": "local"
                }
                
        except subprocess.TimeoutExpired:
            return {
                "status": "error",
                "text": "模型响应超时，请稍后重试",
                "source": "local"
            }
        except Exception as e:
            logger.error(f"本地模型调用异常: {e}")
            return {
                "status": "error",
                "text": f"本地模型异常: {str(e)}",
                "source": "local"
            }
    
    def _build_prompt(self, text: str, history: List[Dict] = None) -> str:
        """构建包含历史对话的 prompt"""
        prompt = "请用中文回答，输出清晰整洁，不要包含特殊控制字符。\n"
        if history:
            for msg in history[-5:]:
                role = "用户" if msg.get('role') == 'user' else "助手"
                prompt += f"{role}: {msg.get('content', '')}\n"
        prompt += f"用户: {text}\n助手: "
        return prompt
    
    def generate(self, prompt: str) -> str:
        """兼容原有接口的生成方法"""
        result = self.predict(prompt)
        return result.get("text", "")