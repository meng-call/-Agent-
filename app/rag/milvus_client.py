"""
合约风控审查 Agent 系统 — Milvus 向量数据库客户端.

管理 Milvus 连接生命周期、Collection 创建和索引配置。
基于 pymilvus MilvusClient (v2.4+) API.
"""

from typing import Any, Dict, List, Optional

import milvus_lite  # noqa: F401 — 必须在 pymilvus 之前导入，注册本地文件 URI 支持
from pymilvus import MilvusClient, DataType


class MilvusManager:
    """Milvus 连接管理器.

    封装 Collection 创建、索引管理、数据插入和搜索操作。
    """

    # BGE-Law 默认维度
    DEFAULT_DIM = 1024

    def __init__(
        self,
        uri: str = "http://localhost:19530",
        db_name: str = "contract_review",
        collection_name: str = "legal_knowledge",
    ) -> None:
        """
        初始化 Milvus 连接.

        Args:
            uri: Milvus 服务地址.
            db_name: 数据库名称.
            collection_name: 默认 Collection 名称.
        """
        self.uri = uri
        self.db_name = db_name
        self.collection_name = collection_name
        self._client: Optional[MilvusClient] = None

    @property
    def client(self) -> MilvusClient:
        """惰性创建 MilvusClient 连接."""
        if self._client is None:
            self._client = MilvusClient(uri=self.uri, db_name=self.db_name)
        return self._client

    def connect(self) -> None:
        """显式建立连接并切换数据库."""
        self._client = MilvusClient(uri=self.uri, db_name=self.db_name)

    def close(self) -> None:
        """关闭连接."""
        if self._client is not None:
            self._client.close()
            self._client = None

    def collection_exists(self, name: Optional[str] = None) -> bool:
        """检查 Collection 是否存在."""
        return self.client.has_collection(
            collection_name=name or self.collection_name
        )

    def list_collections(self) -> List[str]:
        """列出所有 Collection."""
        return self.client.list_collections()

    def create_collection(
        self,
        name: Optional[str] = None,
        dim: int = DEFAULT_DIM,
        drop_if_exists: bool = False,
    ) -> None:
        """
        创建法律知识库 Collection.

        Schema:
        - id: INT64 主键 (auto_id)
        - text: VARCHAR(4096) 法律文本片段
        - embedding: FLOAT_VECTOR(dim) 向量
        - source: VARCHAR(512) 来源文件
        - law_category: VARCHAR(128) 法律类别
        - article_number: VARCHAR(64) 法条编号

        Args:
            name: Collection 名称，默认使用 self.collection_name.
            dim: 向量维度.
            drop_if_exists: 如果已存在是否先删除.
        """
        col_name = name or self.collection_name

        if self.collection_exists(col_name):
            if drop_if_exists:
                self.client.drop_collection(collection_name=col_name)
            else:
                return  # 已存在，不重复创建

        # 创建 Schema
        schema = self.client.create_schema(
            auto_id=True,
            enable_dynamic_field=True,
        )
        schema.add_field(
            field_name="id",
            datatype=DataType.INT64,
            is_primary=True,
        )
        schema.add_field(
            field_name="text",
            datatype=DataType.VARCHAR,
            max_length=4096,
        )
        schema.add_field(
            field_name="embedding",
            datatype=DataType.FLOAT_VECTOR,
            dim=dim,
        )
        schema.add_field(
            field_name="source",
            datatype=DataType.VARCHAR,
            max_length=512,
        )
        schema.add_field(
            field_name="law_category",
            datatype=DataType.VARCHAR,
            max_length=128,
        )
        schema.add_field(
            field_name="article_number",
            datatype=DataType.VARCHAR,
            max_length=64,
        )

        # 创建索引
        index_params = self.client.prepare_index_params()
        index_params.add_index(
            field_name="id",
            index_type="INVERTED",
        )
        index_params.add_index(
            field_name="embedding",
            index_type="AUTOINDEX",
            metric_type="COSINE",
        )

        # 创建 Collection（同时创建索引）
        self.client.create_collection(
            collection_name=col_name,
            schema=schema,
            index_params=index_params,
        )

    def drop_collection(self, name: Optional[str] = None) -> None:
        """删除 Collection."""
        col_name = name or self.collection_name
        self.client.drop_collection(collection_name=col_name)

    def load_collection(self, name: Optional[str] = None) -> None:
        """将 Collection 加载到内存（搜索前必须执行）."""
        col_name = name or self.collection_name
        self.client.load_collection(collection_name=col_name)

    def release_collection(self, name: Optional[str] = None) -> None:
        """从内存释放 Collection."""
        col_name = name or self.collection_name
        self.client.release_collection(collection_name=col_name)

    def insert(
        self,
        chunks: List[Dict[str, Any]],
        name: Optional[str] = None,
    ) -> Dict[str, int]:
        """
        批量插入数据.

        Args:
            chunks: 数据列表，每个元素需包含 text, embedding, source 等字段.
            name: Collection 名称.

        Returns:
            {'insert_count': N}
        """
        col_name = name or self.collection_name
        return self.client.insert(
            collection_name=col_name,
            data=chunks,
        )

    def search(
        self,
        query_vectors: List[List[float]],
        limit: int = 5,
        output_fields: Optional[List[str]] = None,
        metric_type: str = "COSINE",
        name: Optional[str] = None,
    ) -> List[List[Dict[str, Any]]]:
        """
        向量相似度搜索.

        Args:
            query_vectors: 查询向量列表.
            limit: 返回 Top-K 结果.
            output_fields: 需要返回的标量字段.
            metric_type: 度量类型.
            name: Collection 名称.

        Returns:
            搜索结果列表，每项为 [{'id': ..., 'distance': ..., 'entity': {...}}, ...].
        """
        if output_fields is None:
            output_fields = ["text", "source", "law_category", "article_number"]

        col_name = name or self.collection_name
        return self.client.search(
            collection_name=col_name,
            data=query_vectors,
            limit=limit,
            output_fields=output_fields,
            search_params={"metric_type": metric_type},
        )

    def get_stats(self, name: Optional[str] = None) -> Dict[str, Any]:
        """获取 Collection 统计信息."""
        col_name = name or self.collection_name
        return self.client.get_collection_stats(collection_name=col_name)
