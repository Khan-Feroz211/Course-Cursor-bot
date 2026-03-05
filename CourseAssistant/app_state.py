import logging
import time

from sentence_transformers import SentenceTransformer

logger = logging.getLogger(__name__)

embedding_model = None


def load_model() -> SentenceTransformer:
    global embedding_model
    if embedding_model is not None:
        return embedding_model
    for attempt in range(1, 4):  # retry up to 3 times
        try:
            logger.info("Loading embedding model all-MiniLM-L6-v2 (attempt %d/3)", attempt)
            embedding_model = SentenceTransformer("all-MiniLM-L6-v2")
            logger.info("Embedding model loaded successfully")
            return embedding_model
        except Exception:
            logger.exception("Failed to load embedding model (attempt %d/3)", attempt)
            if attempt < 3:
                time.sleep(3)
    logger.error("Embedding model could not be loaded after 3 attempts")
    return None


def is_model_ready() -> bool:
    return embedding_model is not None


def ensure_model() -> bool:
    """Called at request time — tries to load model if not already loaded."""
    global embedding_model
    if embedding_model is not None:
        return True
    embedding_model = load_model()
    return embedding_model is not None
