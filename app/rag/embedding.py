"""
合约风控审查 Agent 系统 — BGE-Law Embedding 封装.

加载 BGE 法律中文模型，提供统一的文档编码和查询编码接口。
"""

from typing import List, Optional

from sentence_transformers import SentenceTransformer


class EmbeddingModel:
    """BGE-Law Embedding 模型封装.

    使用 sentence-transformers 加载 BAAI/bge-large-zh-v1.5 模型，
    输出 1024 维向量。
    """

    def __init__(
        self,
        model_name: str = "BAAI/bge-large-zh-v1.5",
        device: str = "cpu",
    ) -> None:
        """
        初始化 Embedding 模型.

        Args:
            model_name: HuggingFace 模型名称.
            device: 运行设备（"cpu" 或 "cuda"）.
        """
        self.model_name = model_name
        self.device = device
        self._model: Optional[SentenceTransformer] = None

    @property
    def model(self) -> SentenceTransformer:
        """惰性加载模型."""
        if self._model is None:
            import os
            os.environ.setdefault("HF_HUB_OFFLINE", "1")
            self._model = SentenceTransformer(
                self.model_name,
                device=self.device,
                local_files_only=True,
            )
        return self._model

    @property
    def dim(self) -> int:
        """Embedding 维度."""
        return self.model.get_sentence_embedding_dimension()

    def encode_documents(self, texts: List[str]) -> List[List[float]]:
        """
        对文档文本进行编码（批量）.

        BGE 模型建议在文档编码时添加 "passage: " 前缀以获得更好的检索效果.

        Args:
            texts: 文档文本列表.

        Returns:
            向量列表，每个向量维度为 dim.
        """
        # BGE 模型最佳实践：文档侧加 "passage: " 前缀
        prefixed = [f"passage: {t}" for t in texts]
        embeddings = self.model.encode(
            prefixed,
            normalize_embeddings=True,
            show_progress_bar=False,
        )
        return embeddings.tolist()

    def encode_queries(self, queries: List[str]) -> List[List[float]]:
        """
        对查询文本进行编码（批量）.

        BGE 模型建议在查询编码时添加 "query: " 前缀以获得更好的检索效果.

        Args:
            queries: 查询文本列表.

        Returns:
            向量列表，每个向量维度为 dim.
        """
        # BGE 模型最佳实践：查询侧加 "query: " 前缀
        prefixed = [f"query: {q}" for q in queries]
        embeddings = self.model.encode(
            prefixed,
            normalize_embeddings=True,
            show_progress_bar=False,
        )
        return embeddings.tolist()
