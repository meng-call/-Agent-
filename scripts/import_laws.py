#!/usr/bin/env python
"""
法律文本批量导入脚本.

读取 JSON/TXT 格式的法律条文文件，分块 → Embedding → 批量写入 Milvus。
用法:
    python scripts/import_laws.py --input data/civil_code.json
    python scripts/import_laws.py --input data/laws/ --category 民法
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Iterator, Tuple

# 添加项目根目录到 Python path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.config import load_settings
from app.rag.chunker import chunk_document
from app.rag.embedding import EmbeddingModel
from app.rag.milvus_client import MilvusManager


def load_json_source(file_path: Path) -> Iterator[Tuple[str, str, str]]:
    """
    加载 JSON 格式的法律文件.

    期望格式:
    [
        {
            "title": "合同法",
            "category": "民事",
            "articles": [
                {"number": "第1条", "content": "..."},
                ...
            ]
        }
    ]

    Yields: (text, source, category)
    """
    with open(file_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    source_name = file_path.stem

    if isinstance(data, list):
        for item in data:
            category = item.get("category", "")
            title = item.get("title", source_name)
            articles = item.get("articles", [])
            for article in articles:
                number = article.get("number", "")
                content = article.get("content", "")
                full_text = f"{number} {content}"
                yield full_text, str(file_path), category or title
    elif isinstance(data, dict):
        # 单文件单法律
        title = data.get("title", source_name)
        category = data.get("category", "")
        articles = data.get("articles", [])
        for article in articles:
            number = article.get("number", "")
            content = article.get("content", "")
            full_text = f"{number} {content}"
            yield full_text, str(file_path), category or title


def load_txt_source(file_path: Path) -> Iterator[Tuple[str, str, str]]:
    """
    加载 TXT 格式的法律文件.

    每行为一条法条，格式: "第X条 内容..."
    """
    with open(file_path, "r", encoding="utf-8") as f:
        content = f.read()

    source_name = file_path.stem
    yield content, str(file_path), source_name


def import_documents(
    input_path: Path,
    category: str = "",
    batch_size: int = 32,
    dry_run: bool = False,
) -> None:
    """
    导入法律文本到 Milvus.

    Args:
        input_path: 输入文件或目录路径.
        category: 法律类别标签.
        batch_size: 每批插入的向量数.
        dry_run: 仅打印将要导入的内容，不实际写入.
    """
    # 加载配置
    settings = load_settings()

    # 初始化组件
    milvus = MilvusManager(
        uri=f"http://{settings.milvus.host}:{settings.milvus.port}",
        db_name=settings.milvus.db_name,
        collection_name=settings.milvus.collection_name,
    )
    embedding = EmbeddingModel(
        model_name=settings.embedding.model,
        device=settings.embedding.device,
    )

    # 确保 Collection 存在
    if not milvus.collection_exists():
        print("Collection 不存在，请先运行 init_milvus.py")
        return

    # 收集所有文件
    if input_path.is_file():
        files = [input_path]
    elif input_path.is_dir():
        files = list(input_path.glob("*.json")) + list(input_path.glob("*.txt"))
    else:
        print(f"路径不存在: {input_path}")
        return

    print(f"找到 {len(files)} 个文件")
    print(f"Embedding 模型: {embedding.model_name}")
    print(f"设备: {embedding.device}")
    print(f"向量维度: {embedding.dim}")

    total_chunks = 0
    total_inserted = 0

    for file_path in files:
        print(f"\n处理: {file_path.name}")

        # 加载原始文本
        if file_path.suffix == ".json":
            segments = list(load_json_source(file_path))
        elif file_path.suffix == ".txt":
            segments = list(load_txt_source(file_path))
        else:
            print(f"  跳过不支持的文件格式: {file_path.suffix}")
            continue

        # 对每个法条/段落进行分块
        all_chunks = []
        for text, source, cat in segments:
            chunks = chunk_document(
                text=text,
                source=source,
                category=cat or category,
            )
            all_chunks.extend(chunks)

        print(f"  生成 {len(all_chunks)} 个分块")

        if dry_run:
            for chunk in all_chunks:
                print(f"    [{chunk.index}] {chunk.text[:80]}...")
            total_chunks += len(all_chunks)
            continue

        # 分批 Embedding + 插入
        for i in range(0, len(all_chunks), batch_size):
            batch = all_chunks[i:i + batch_size]

            # 向量化
            texts = [c.text for c in batch]
            vectors = embedding.encode_documents(texts)

            # 组装插入数据
            data = []
            for chunk, vec in zip(batch, vectors):
                data.append({
                    "text": chunk.text,
                    "embedding": vec,
                    "source": chunk.source,
                    "law_category": chunk.law_category,
                    "article_number": chunk.article_number,
                })

            # 插入
            result = milvus.insert(data)
            print(f"  已插入: {i + len(batch)}/{len(all_chunks)}")

        total_chunks += len(all_chunks)
        total_inserted += len(all_chunks)

    # 刷新确保写入
    if not dry_run:
        # 重新加载 Collection
        milvus.load_collection()
        stats = milvus.get_stats()
        print(f"\n导入完成！共 {total_inserted} 个向量, 统计: {stats}")
    else:
        print(f"\n[Dry Run] 共 {total_chunks} 个分块（未实际写入）")

    milvus.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="导入法律文本到 Milvus 知识库")
    parser.add_argument(
        "--input", "-i",
        type=str,
        required=True,
        help="输入文件(.json/.txt)或目录路径",
    )
    parser.add_argument(
        "--category", "-c",
        type=str,
        default="",
        help="法律类别标签",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=32,
        help="每批写入的向量数",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="仅预览分块结果，不实际写入 Milvus",
    )
    args = parser.parse_args()

    input_path = Path(args.input)
    import_documents(
        input_path=input_path,
        category=args.category,
        batch_size=args.batch_size,
        dry_run=args.dry_run,
    )


if __name__ == "__main__":
    main()
