#!/usr/bin/env python
"""
Milvus Collection 初始化脚本.

一键创建法律知识库 Collection 并配置索引。
用法: python scripts/init_milvus.py [--drop-existing]
"""

import argparse
import sys
from pathlib import Path

# 添加项目根目录到 Python path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.config import load_settings
from app.rag.milvus_client import MilvusManager


def main() -> None:
    parser = argparse.ArgumentParser(description="初始化 Milvus 法律知识库 Collection")
    parser.add_argument(
        "--drop-existing",
        action="store_true",
        help="如果 Collection 已存在，先删除再重建",
    )
    parser.add_argument(
        "--dim",
        type=int,
        default=1024,
        help="向量维度（BGE-Law 默认 1024）",
    )
    args = parser.parse_args()

    # 加载配置
    settings = load_settings()
    print(f"连接 Milvus: {settings.milvus.db_uri}")

    # 创建管理器
    manager = MilvusManager(
        uri=settings.milvus.db_uri,
        db_name=settings.milvus.db_name,
        collection_name=settings.milvus.collection_name,
    )

    try:
        # 检查是否已存在
        if manager.collection_exists():
            if args.drop_existing:
                print(f"删除已有 Collection: {settings.milvus.collection_name}")
                manager.drop_collection()
            else:
                print(f"Collection 已存在: {settings.milvus.collection_name}")
                print("使用 --drop-existing 强制重建")
                return

        # 创建 Collection
        print(f"创建 Collection: {settings.milvus.collection_name} (dim={args.dim})")
        manager.create_collection(
            name=settings.milvus.collection_name,
            dim=args.dim,
            drop_if_exists=False,
        )

        # 加载到内存
        manager.load_collection()
        print("Collection 已加载到内存")

        # 验证
        stats = manager.get_stats()
        print(f"统计: {stats}")

    finally:
        manager.close()

    print("\n初始化完成！现在可以运行 import_laws.py 导入法律文本。")


if __name__ == "__main__":
    main()
