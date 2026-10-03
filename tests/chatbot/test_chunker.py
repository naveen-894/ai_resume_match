from app.chatbot.knowledge.chunker import chunk_content_items
from app.chatbot.knowledge.loader import ContentItem


def _item(text: str, id_: str = "test-item") -> ContentItem:
    return ContentItem(
        id=id_, url="https://modax.in/", title="Title", section="Section",
        content_type="company_overview", text=text,
    )


def test_short_text_is_a_single_chunk():
    item = _item("Modax builds custom AI tools for HR teams.")
    chunks = chunk_content_items([item])
    assert len(chunks) == 1
    assert chunks[0].id == "test-item"
    assert chunks[0].metadata["url"] == "https://modax.in/"
    assert chunks[0].metadata["text"] == chunks[0].text


def test_long_text_is_split_into_multiple_chunks():
    sentence = "Modax builds custom AI tools that save teams hours of manual work. "
    long_text = sentence * 40  # well over the default 900-char chunk size
    item = _item(long_text)
    chunks = chunk_content_items([item])
    assert len(chunks) > 1
    # ids are deterministic and derived from the source item id
    assert all(c.id.startswith("test-item") for c in chunks)
    assert len({c.id for c in chunks}) == len(chunks)  # no collisions


def test_metadata_preserved_across_chunks():
    item = _item("Short enough text.", id_="svc-1")
    item = ContentItem(
        id="svc-1", url="https://modax.in/services", title="Services",
        section="AI Assistants", content_type="service", text="Short enough text.",
    )
    [chunk] = chunk_content_items([item])
    assert chunk.metadata["source_id"] == "svc-1"
    assert chunk.metadata["section"] == "AI Assistants"
    assert chunk.metadata["content_type"] == "service"
