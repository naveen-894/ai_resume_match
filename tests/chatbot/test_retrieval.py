from app.chatbot import embeddings, retrieval, vector_store


async def test_retrieve_filters_low_score_matches(monkeypatch):
    async def fake_embed_text(text):
        return [0.1, 0.2, 0.3]

    async def fake_query(vector, top_k=None):
        return [
            {"id": "a", "score": 0.95, "metadata": {"text": "high relevance", "url": "u1", "title": "t1", "section": "s1"}},
            {"id": "b", "score": 0.10, "metadata": {"text": "low relevance", "url": "u2", "title": "t2", "section": "s2"}},
        ]

    monkeypatch.setattr(embeddings, "embed_text", fake_embed_text)
    monkeypatch.setattr(vector_store, "query", fake_query)

    chunks = await retrieval.retrieve("what services do you offer?")
    assert len(chunks) == 1
    assert chunks[0].text == "high relevance"


async def test_retrieve_returns_empty_on_vector_store_error(monkeypatch):
    async def fake_embed_text(text):
        return [0.1, 0.2, 0.3]

    async def failing_query(vector, top_k=None):
        raise vector_store.VectorStoreError("pinecone unreachable")

    monkeypatch.setattr(embeddings, "embed_text", fake_embed_text)
    monkeypatch.setattr(vector_store, "query", failing_query)

    chunks = await retrieval.retrieve("what services do you offer?")
    assert chunks == []


async def test_retrieve_returns_empty_on_unexpected_error(monkeypatch):
    async def failing_embed_text(text):
        raise RuntimeError("boom")

    monkeypatch.setattr(embeddings, "embed_text", failing_embed_text)

    chunks = await retrieval.retrieve("what services do you offer?")
    assert chunks == []
