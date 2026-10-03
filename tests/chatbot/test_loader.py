from app.chatbot.knowledge.loader import load_content_items


def test_real_content_files_load_without_error():
    """Guards against malformed/duplicate ids in the actual knowledge/content/*.json
    files that ship with the repo."""
    items = load_content_items()
    assert len(items) > 10
    ids = [i.id for i in items]
    assert len(ids) == len(set(ids))
    for item in items:
        assert item.url.startswith("https://modax.in")
        assert item.text.strip()
