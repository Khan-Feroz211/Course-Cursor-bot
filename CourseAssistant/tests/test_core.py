from api.auth import check_password, hash_password
from core.file_processor import chunk_pages


def test_file_processor_import():
    from core import file_processor  # noqa: F401

    assert callable(file_processor.extract_text)
    assert callable(file_processor.chunk_pages)


def test_chunk_pages():
    text = " ".join([f"word{i}" for i in range(1000)])
    pages = [{"text": text, "page": 1, "source": "sample.txt"}]
    chunks = chunk_pages(pages, chunk_size=200, overlap=50)
    assert len(chunks) > 1
    assert chunks[0]["source_filename"] == "sample.txt"
    first_words = chunks[0]["text"].split()
    second_words = chunks[1]["text"].split()
    assert first_words[-50:] == second_words[:50]


def test_auth_hash():
    pw = "StrongPass123!"
    hashed = hash_password(pw)
    assert hashed != pw
    assert check_password(pw, hashed) is True
    assert check_password("WrongPass", hashed) is False
