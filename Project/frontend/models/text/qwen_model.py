from typing import Dict, Any, List
import sys
import os
import logging

sys.path.append(os.path.join(os.path.dirname(__file__), '..'))
from base_model import BaseModel

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class QwenModel(BaseModel):
    """
    完全离线模式 - 强制使用本地 Ollama 模型
    """
    
    def __init__(self, api_key: str = None, model_name: str = "qwen-turbo", use_local_fallback: bool = True):
        super().__init__(None)
        self.model_name = model_name
        self.local_model = None
        self._init_local_model()

    def _init_local_model(self):
        """初始化本地模型"""
        try:
            from .local_model import LocalModel
            self.local_model = LocalModel()
            logger.info("本地模型加载成功，完全离线模式已启用")
        except Exception as e:
            logger.error(f"本地模型加载失败: {e}")

    def load_model(self):
        pass
    
    def predict(self, input_data: str, history: List[Dict] = None) -> Dict[str, Any]:
        """
        强制使用本地模型进行预测（完全离线，不尝试在线 API）
        """
        if self.local_model is None:
            return {
                "status": "error",
                "text": "本地模型未加载，请检查 Ollama 是否安装并下载了模型"
            }
        
        return self.local_model.predict(input_data, history)

    def preprocess(self, input_data: str) -> str:
        return input_data.strip()
        
    def postprocess(self, output_data: Dict[str, Any]) -> Dict[str, Any]:
        return output_data