"""Tests for base channel abstraction and media content builder."""

import base64

from unittest.mock import AsyncMock

from astromesh.channels.base import ChannelAdapter, ChannelMessage, MediaAttachment
from astromesh.channels.media import build_multimodal_query


# ---------------------------------------------------------------------------
# MediaAttachment tests
# ---------------------------------------------------------------------------

class TestMediaAttachment:

    def test_create_image_attachment(self):
        att = MediaAttachment(
            media_type="image",
            mime_type="image/jpeg",
            content=b"\xff\xd8\xff",
            source_id="media_123",
        )
        assert att.media_type == "image"
        assert att.mime_type == "image/jpeg"
        assert att.content == b"\xff\xd8\xff"
        assert att.source_id == "media_123"
        assert att.filename is None

    def test_create_document_attachment_with_filename(self):
        att = MediaAttachment(
            media_type="document",
            mime_type="application/pdf",
            content=None,
            source_id="media_456",
            filename="report.pdf",
        )
        assert att.filename == "report.pdf"
        assert att.content is None


# ---------------------------------------------------------------------------
# ChannelMessage tests
# ---------------------------------------------------------------------------

class TestChannelMessage:

    def test_text_only_message(self):
        msg = ChannelMessage(
            sender_id="user123",
            text="Hello",
            media=[],
            message_id="msg_1",
            timestamp="1700000000",
            channel="test",
        )
        assert msg.text == "Hello"
        assert msg.media == []
        assert msg.raw_payload == {}

    def test_media_only_message(self):
        att = MediaAttachment(
            media_type="image",
            mime_type="image/png",
            content=None,
            source_id="m1",
        )
        msg = ChannelMessage(
            sender_id="user123",
            text=None,
            media=[att],
            message_id="msg_2",
            timestamp="1700000000",
            channel="test",
        )
        assert msg.text is None
        assert len(msg.media) == 1

    def test_mixed_message(self):
        att = MediaAttachment(
            media_type="image",
            mime_type="image/jpeg",
            content=None,
            source_id="m1",
        )
        msg = ChannelMessage(
            sender_id="user123",
            text="Check this out",
            media=[att],
            message_id="msg_3",
            timestamp="1700000000",
            channel="test",
        )
        assert msg.text == "Check this out"
        assert len(msg.media) == 1


# ---------------------------------------------------------------------------
# build_multimodal_query tests
# ---------------------------------------------------------------------------

def _make_adapter() -> ChannelAdapter:
    """Create a mock ChannelAdapter."""
    adapter = AsyncMock(spec=ChannelAdapter)
    return adapter


def _make_message(
    text=None,
    media=None,
) -> ChannelMessage:
    return ChannelMessage(
        sender_id="user1",
        text=text,
        media=media or [],
        message_id="msg_1",
        timestamp="1700000000",
        channel="test",
    )


class TestBuildMultimodalQuery:

    async def test_text_only_returns_string(self):
        msg = _make_message(text="Hello world")
        result = await build_multimodal_query(msg, _make_adapter())
        assert result == "Hello world"
        assert isinstance(result, str)

    async def test_empty_text_returns_empty_string(self):
        msg = _make_message(text=None)
        result = await build_multimodal_query(msg, _make_adapter())
        assert result == ""
        assert isinstance(result, str)

    async def test_image_returns_multimodal_list(self):
        image_bytes = b"\x89PNG\r\n\x1a\n"
        att = MediaAttachment(
            media_type="image",
            mime_type="image/png",
            content=image_bytes,
            source_id="m1",
        )
        msg = _make_message(text="What is this?", media=[att])
        adapter = _make_adapter()

        result = await build_multimodal_query(msg, adapter)

        assert isinstance(result, list)
        assert len(result) == 2
        assert result[0] == {"type": "text", "text": "What is this?"}
        assert result[1]["type"] == "image_url"
        expected_b64 = base64.b64encode(image_bytes).decode()
        assert result[1]["image_url"]["url"] == f"data:image/png;base64,{expected_b64}"

    async def test_image_without_text(self):
        image_bytes = b"\xff\xd8\xff"
        att = MediaAttachment(
            media_type="image",
            mime_type="image/jpeg",
            content=image_bytes,
            source_id="m1",
        )
        msg = _make_message(text=None, media=[att])

        result = await build_multimodal_query(msg, _make_adapter())

        assert isinstance(result, list)
        assert len(result) == 1
        assert result[0]["type"] == "image_url"

    async def test_audio_returns_text_description(self):
        audio_bytes = b"\x00" * 100
        att = MediaAttachment(
            media_type="audio",
            mime_type="audio/ogg",
            content=audio_bytes,
            source_id="m1",
        )
        msg = _make_message(text="Voice message", media=[att])

        result = await build_multimodal_query(msg, _make_adapter())

        # Audio can't be sent to vision models, so result should be plain text.
        assert isinstance(result, str)
        assert "audio/ogg" in result
        assert "100 bytes" in result

    async def test_document_includes_filename(self):
        doc_bytes = b"%PDF-1.4"
        att = MediaAttachment(
            media_type="document",
            mime_type="application/pdf",
            content=doc_bytes,
            source_id="m1",
            filename="report.pdf",
        )
        msg = _make_message(text=None, media=[att])

        result = await build_multimodal_query(msg, _make_adapter())

        assert isinstance(result, str)
        assert "report.pdf" in result

    async def test_downloads_media_when_content_is_none(self):
        att = MediaAttachment(
            media_type="image",
            mime_type="image/png",
            content=None,
            source_id="m1",
        )
        msg = _make_message(text="Look", media=[att])
        adapter = _make_adapter()
        adapter.download_media = AsyncMock(return_value=b"\x89PNG")

        result = await build_multimodal_query(msg, adapter)

        adapter.download_media.assert_called_once_with(att)
        assert isinstance(result, list)
        assert any(p["type"] == "image_url" for p in result)

    async def test_download_failure_adds_error_text(self):
        att = MediaAttachment(
            media_type="image",
            mime_type="image/png",
            content=None,
            source_id="m1",
        )
        msg = _make_message(text="Look", media=[att])
        adapter = _make_adapter()
        adapter.download_media = AsyncMock(side_effect=RuntimeError("network error"))

        result = await build_multimodal_query(msg, adapter)

        # Should fall back to text since the only image failed.
        assert isinstance(result, str)
        assert "download failed" in result

    async def test_mixed_image_and_audio(self):
        img = MediaAttachment(
            media_type="image", mime_type="image/jpeg",
            content=b"\xff\xd8", source_id="m1",
        )
        aud = MediaAttachment(
            media_type="audio", mime_type="audio/ogg",
            content=b"\x00" * 50, source_id="m2",
        )
        msg = _make_message(text="Check these", media=[img, aud])

        result = await build_multimodal_query(msg, _make_adapter())

        # Has an image, so should be multimodal list.
        assert isinstance(result, list)
        types = [p["type"] for p in result]
        assert "text" in types
        assert "image_url" in types
