import logging

from sentence_transformers import SentenceTransformer

logger = logging.getLogger(__name__)

embedding_model = None


def load_model() -> SentenceTransformer:
    global embedding_model
    if embedding_model is None:
        logger.info("Loading embedding model all-MiniLM-L6-v2")
        embedding_model = SentenceTransformer("all-MiniLM-L6-v2")
    return embedding_model
