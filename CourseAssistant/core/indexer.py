import logging
import pickle
from pathlib import Path

import faiss
import numpy as np

logger = logging.getLogger(__name__)

# In-memory index cache: user_id -> (faiss_index, chunks)
# Eliminates repeated disk reads on every search request.
_index_cache: dict[int, tuple] = {}


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
    # Update in-memory cache so next search is instant
    _index_cache[user_id] = (index, chunks)
    logger.info("Index built for user=%s chunks=%s", user_id, len(chunks))


def load_index(user_id: int):
    # Serve from RAM cache if available — avoids disk I/O on every query
    if user_id in _index_cache:
        return _index_cache[user_id]
    user_dir = get_user_dir(user_id)
    index_path = user_dir / "index.faiss"
    chunks_path = user_dir / "chunks.pkl"
    if not index_path.exists() or not chunks_path.exists():
        return None, None
    try:
        index = faiss.read_index(str(index_path))
        with chunks_path.open("rb") as f:
            chunks = pickle.load(f)
        _index_cache[user_id] = (index, chunks)
        return index, chunks
    except Exception:
        logger.exception("Failed loading index for user=%s", user_id)
        return None, None


def delete_user_data(user_id: int) -> None:
    _index_cache.pop(user_id, None)  # evict from RAM cache
    user_dir = get_user_dir(user_id)
    for name in ("index.faiss", "chunks.pkl"):
        p = user_dir / name
        if p.exists():
            p.unlink()
