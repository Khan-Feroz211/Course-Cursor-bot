import logging
import pickle
from pathlib import Path

import faiss
import numpy as np

logger = logging.getLogger(__name__)


def get_user_dir(user_id: int) -> Path:
    user_dir = Path(f"data/users/{user_id}")
    user_dir.mkdir(parents=True, exist_ok=True)
    (user_dir / "uploads").mkdir(parents=True, exist_ok=True)
    return user_dir


def build_index(user_id: int, chunks: list[dict], model) -> None:
    user_dir = get_user_dir(user_id)
    index_path = user_dir / "index.faiss"
    chunks_path = user_dir / "chunks.pkl"
    if not chunks:
        delete_user_data(user_id)
        return
    texts = [c["text"] for c in chunks]
    vectors = model.encode(texts)
    vectors_np = np.array(vectors, dtype=np.float32)
    faiss.normalize_L2(vectors_np)
    index = faiss.IndexFlatIP(vectors_np.shape[1])
    index.add(vectors_np)
    faiss.write_index(index, str(index_path))
    with chunks_path.open("wb") as f:
        pickle.dump(chunks, f)
    logger.info("Index built for user=%s chunks=%s", user_id, len(chunks))


def load_index(user_id: int):
    user_dir = get_user_dir(user_id)
    index_path = user_dir / "index.faiss"
    chunks_path = user_dir / "chunks.pkl"
    if not index_path.exists() or not chunks_path.exists():
        return None, None
    try:
        index = faiss.read_index(str(index_path))
        with chunks_path.open("rb") as f:
            chunks = pickle.load(f)
        return index, chunks
    except Exception:
        logger.exception("Failed loading index for user=%s", user_id)
        return None, None


def delete_user_data(user_id: int) -> None:
    user_dir = get_user_dir(user_id)
    for name in ("index.faiss", "chunks.pkl"):
        p = user_dir / name
        if p.exists():
            p.unlink()
