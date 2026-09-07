#!/usr/bin/env python
"""
法律知识批量导入 — 统一入口.

从 LawRefBook + ChatLaw 数据源提取法律知识，分块、向量化、写入 Milvus。

数据源:
  LawRefBook-master/laws.zip  — 1613 个 .md 法条文件（按类别分目录）
  ChatLaw-main/data/*.jsonl   — 法律咨询/概念问答对

用法:
  python scripts/import_all.py                      # 导入全部
  python scripts/import_all.py --source lawrefbook  # 仅 LawRefBook
  python scripts/import_all.py --source chatlaw     # 仅 ChatLaw
  python scripts/import_all.py --dry-run            # 预览不写入
"""

import argparse
import json
import re
import sys
import zipfile
from pathlib import Path
from typing import Iterator, Optional, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.config import load_settings
from app.rag.chunker import SemanticChunker, ChunkerConfig


def _chunk_text(text: str, source: str, category: str) -> list:
    """便捷分块."""
    config = ChunkerConfig(chunk_size=512, chunk_overlap=64)
    chunker = SemanticChunker(config)
    return chunker.chunk(text, source=source, category=category)


# ── LawRefBook 类别 → 系统类别映射 ──────────────────────
CATEGORY_MAP = {
    "民法商法": "民事-合同编",
    "民法典": "民事-合同编",
    "刑法": "刑事",
    "行政法": "行政法",
    "行政法规": "行政法",
    "经济法": "经济法",
    "社会法": "社会法-劳动法",
    "宪法": "宪法",
    "宪法相关法": "宪法",
    "诉讼与非诉讼程序法": "程序法",
    "司法解释": "司法解释",
    "部门规章": "部门规章",
    "案例": "案例",
    "其他": "其他",
}


def _clean_markdown(text: str) -> str:
    """清洗 Markdown 标记，保留纯文本."""
    # 去掉标题标记但保留文本
    text = re.sub(r"^#{1,6}\s+", "", text, flags=re.MULTILINE)
    # 去掉加粗/斜体
    text = re.sub(r"\*\*(.+?)\*\*", r"\1", text)
    text = re.sub(r"\*(.+?)\*", r"\1", text)
    # 去掉链接
    text = re.sub(r"\[(.+?)\]\(.+?\)", r"\1", text)
    # 合并多余空行
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _split_by_articles(text: str) -> list[Tuple[str, str]]:
    """将 Markdown 法律文本按法条分割.

    Returns: [(article_number, article_text), ...]
    """
    # 匹配 "第X条" 或 "第XX条"
    parts = re.split(r"(第[一二三四五六七八九十百千\d]+条[\s\S]*?)(?=第[一二三四五六七八九十百千\d]+条|\Z)", text)
    results = []
    for i, part in enumerate(parts):
        part = part.strip()
        if not part:
            continue
        m = re.match(r"(第[一二三四五六七八九十百千\d]+条)", part)
        if m:
            number = m.group(1)
            results.append((number, part))
        elif results:
            # 续接上一条
            prev_num, prev_text = results[-1]
            results[-1] = (prev_num, prev_text + "\n" + part)
        else:
            # 前言部分（法律名称、立法目的等）
            results.append(("", part))
    return results


# ── LawRefBook 加载器 ────────────────────────────────────

def _fix_zip_name(name: str) -> str:
    """修复 zip 中非 UTF-8 文件名编码（GBK → 正确中文）."""
    try:
        return name.encode("cp437").decode("gbk")
    except (UnicodeDecodeError, UnicodeEncodeError):
        return name


def load_lawrefbook(
    zip_path: Path,
    categories: Optional[list] = None,
) -> Iterator[Tuple[str, str, str]]:
    """从 LawRefBook laws.zip 加载法律条文.

    Args:
        zip_path: laws.zip 路径.
        categories: 限定类别列表，None 表示全部.

    Yields: (text, source, category)
    """
    z = zipfile.ZipFile(zip_path)
    md_files = [n for n in z.namelist() if n.endswith(".md") and "/" in n]

    for name in md_files:
        parts = name.split("/")
        folder = _fix_zip_name(parts[0])
        filename = parts[-1].replace(".md", "")

        # 类别过滤
        if categories and folder not in categories:
            continue

        category = CATEGORY_MAP.get(folder, folder)
        content = z.read(name).decode("utf-8")
        content = _clean_markdown(content)

        # 按法条分割
        articles = _split_by_articles(content)

        for number, article_text in articles:
            if len(article_text) < 20:
                continue
            label = f"{filename} {number}".strip() if number else filename
            full_text = f"{label}\n{article_text}" if number else article_text
            yield full_text, f"{folder}/{filename}.md", category

    z.close()


# ── ChatLaw 加载器 ──────────────────────────────────────

def load_chatlaw_qa(jsonl_path: Path) -> Iterator[Tuple[str, str, str]]:
    """从 ChatLaw JSONL 加载法律问答对.

    格式: {"chat": [{"咨询者": "...", "ChatLAW": "..."}], "subject": "法律咨询"}

    Yields: (text, source, category)
    """
    with open(jsonl_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                continue

            subject = item.get("subject", "法律咨询")
            chats = item.get("chat", [])
            for chat in chats:
                question = chat.get("咨询者", "")
                answer = chat.get("ChatLAW", "")
                if question and answer:
                    text = f"问：{question}\n答：{answer}"
                    yield text, jsonl_path.name, f"ChatLaw-{subject}"


def load_chatlaw_stage2(json_path: Path) -> Iterator[Tuple[str, str, str]]:
    """从 ChatLaw stage2 加载案件-罪名数据.

    格式: [{"q": "指控...", "crime": ["罪名"]}, ...]

    Yields: (text, source, category)
    """
    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    for item in data:
        q = item.get("q", "")
        crimes = item.get("crime", [])
        crime_label = "、".join(crimes) if crimes else "未知罪名"
        if q:
            yield q, json_path.name, f"ChatLaw-案例-{crime_label}"


# ── 主导入流程 ──────────────────────────────────────────

def import_all(
    lawrefbook_zip: Optional[Path] = None,
    chatlaw_dir: Optional[Path] = None,
    categories: Optional[list] = None,
    batch_size: int = 32,
    dry_run: bool = False,
) -> None:
    """导入所有法律数据到 Milvus."""
    settings = load_settings()

    from app.rag.embedding import EmbeddingModel
    from app.rag.milvus_client import MilvusManager

    milvus = MilvusManager(
        uri=settings.milvus.db_uri,
        db_name=settings.milvus.db_name,
        collection_name=settings.milvus.collection_name,
    )
    embedding = EmbeddingModel(
        model_name=settings.embedding.model,
        device=settings.embedding.device,
    )

    if not milvus.collection_exists():
        print("Collection 不存在，请先运行: python scripts/init_milvus.py --drop-existing")
        return

    print(f"Milvus: {settings.milvus.db_uri}")
    print(f"Embedding: {embedding.model_name} ({embedding.dim}维)")
    print(f"设备: {embedding.device}")
    print()

    # 收集所有输入
    all_segments: list[Tuple[str, str, str]] = []

    if lawrefbook_zip and lawrefbook_zip.exists():
        cat_info = f" (类别: {', '.join(categories)})" if categories else " (全部)"
        print(f"[LawRefBook] 加载 {lawrefbook_zip}{cat_info} ...")
        segments = list(load_lawrefbook(lawrefbook_zip, categories=categories))
        print(f"  提取 {len(segments)} 个法条段落")
        all_segments.extend(segments)

    if chatlaw_dir and chatlaw_dir.exists():
        for jsonl_file in sorted(chatlaw_dir.glob("*.jsonl")):
            print(f"[ChatLaw JSONL] 加载 {jsonl_file.name} ...")
            segments = list(load_chatlaw_qa(jsonl_file))
            print(f"  提取 {len(segments)} 个问答对")
            all_segments.extend(segments)

        for json_file in sorted(chatlaw_dir.glob("*.json")):
            if json_file.name.endswith(".jsonl"):
                continue
            print(f"[ChatLaw JSON] 加载 {json_file.name} ...")
            try:
                segments = list(load_chatlaw_stage2(json_file))
                print(f"  提取 {len(segments)} 个案例")
                all_segments.extend(segments)
            except Exception as e:
                print(f"  跳过: {e}")

    if not all_segments:
        print("没有找到可导入的数据")
        return

    # 分块
    print(f"\n总计 {len(all_segments)} 个段落，开始分块...")
    all_chunks = []
    for text, source, category in all_segments:
        chunks = _chunk_text(text, source=source, category=category)
        all_chunks.extend(chunks)

    print(f"生成 {len(all_chunks)} 个分块")

    if dry_run:
        print("\n[Dry Run] 预览前 10 个分块:")
        for i, chunk in enumerate(all_chunks[:10]):
            print(f"  [{i}] [{chunk.law_category}] {chunk.text[:100]}...")
        print(f"\n共 {len(all_chunks)} 个分块（未写入）")
        return

    # 批量向量化 + 插入（带重试，Milvus Lite gRPC 连接偶尔断开）
    import time
    total_inserted = 0
    for i in range(0, len(all_chunks), batch_size):
        batch = all_chunks[i:i + batch_size]
        texts = [c.text for c in batch]
        vectors = embedding.encode_documents(texts)

        data = []
        for chunk, vec in zip(batch, vectors):
            article = chunk.article_number or ""
            data.append({
                "text": chunk.text,
                "embedding": vec,
                "source": chunk.source,
                "law_category": chunk.law_category,
                "article_number": article,
            })

        for attempt in range(3):
            try:
                milvus.insert(data)
                total_inserted += len(batch)
                print(f"  已插入: {total_inserted}/{len(all_chunks)}")
                break
            except Exception as e:
                if attempt < 2:
                    print(f"  重试 {attempt+1}/2: {e}")
                    time.sleep(2)
                    # 重连
                    try:
                        milvus.close()
                    except Exception:
                        pass
                    milvus.connect()
                    if milvus.collection_exists():
                        try:
                            milvus.load_collection()
                        except Exception:
                            pass
                else:
                    raise

        # 每 50 批暂停一下，释放 gRPC 压力
        if (i // batch_size + 1) % 50 == 0:
            time.sleep(1)

    # 加载并统计
    try:
        milvus.load_collection()
    except Exception:
        pass
    stats = milvus.get_stats()
    print(f"\n导入完成！总计 {total_inserted} 条向量，统计: {stats}")
    milvus.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="批量导入法律知识到 Milvus")
    parser.add_argument("--source", type=str, default="all",
                        choices=["all", "lawrefbook", "chatlaw"],
                        help="数据源 (默认: all)")
    parser.add_argument("--lawrefbook-zip", type=str,
                        default="LawRefBook-master/LawRefBook-master/laws.zip",
                        help="LawRefBook laws.zip 路径")
    parser.add_argument("--chatlaw-dir", type=str,
                        default="ChatLaw-main (1)/ChatLaw-main/data",
                        help="ChatLaw data 目录路径")
    parser.add_argument("--categories", type=str, default="民法商法,民法典,经济法,社会法,案例",
                        help="LawRefBook 限定类别，逗号分隔 (默认: 合同审查相关)")
    parser.add_argument("--batch-size", type=int, default=32)
    parser.add_argument("--dry-run", action="store_true",
                        help="仅预览，不写入 Milvus")
    args = parser.parse_args()

    base = Path(__file__).resolve().parent.parent

    lawrefbook = None
    chatlaw = None

    if args.source in ("all", "lawrefbook"):
        lawrefbook = base / args.lawrefbook_zip
    if args.source in ("all", "chatlaw"):
        chatlaw = base / args.chatlaw_dir

    import_all(
        lawrefbook_zip=lawrefbook,
        chatlaw_dir=chatlaw,
        categories=[c.strip() for c in args.categories.split(",")] if args.categories else None,
        batch_size=args.batch_size,
        dry_run=args.dry_run,
    )


if __name__ == "__main__":
    main()
