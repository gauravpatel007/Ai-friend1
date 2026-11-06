"""Comprehensive Unit and Integration Tests for Phase 7:
Local Multimodal File Processing (Images, PDFs, Word, Spreadsheets, Audio, Video, Multi-Attachments).
"""

import io
import os
import struct
import tempfile
import time
import wave
import cv2
import numpy as np
import openpyxl
from PIL import Image
import pypdf
import pytest
from unittest.mock import MagicMock, patch

from app.ai.attachment_processor import (
    AttachmentProcessor,
    FileCategory,
    MultimodalAttachment,
    SpreadsheetProfiler,
    build_multimodal_prompt_context,
    extract_docx_structured,
    extract_pdf_structured,
    extract_text_structured,
    process_audio_attachment,
    process_video_attachment,
)
from app.ai.model_capability_registry import ModelCapability, ModelProfile
from app.ai.model_router import TaskCategory, TaskDetector


# ─── 1. Unified Attachment Architecture (Requirement A) ────────────────────

def test_multimodal_attachment_model_and_serialization():
    att = MultimodalAttachment(
        id="att_12345",
        name="quarterly_report.pdf",
        file_type=".pdf",
        mime_type="application/pdf",
        size=45000,
        size_formatted="43.9 KB",
        category=FileCategory.DOCUMENT,
        storage_path="/path/to/upload.pdf",
        status="ready",
        content="--- [Page 1] ---\nFinancial summary.",
        metadata={"page_count": 5},
        conversation_id="conv-1",
        message_id=42,
    )

    data = att.to_dict()
    assert data["id"] == "att_12345"
    assert data["name"] == "quarterly_report.pdf"
    assert data["extension"] == "pdf"
    assert data["category"] == "document"
    assert data["size"] == 45000
    assert data["metadata"]["page_count"] == 5
    assert data["conversation_id"] == "conv-1"
    assert data["message_id"] == 42


# ─── 2. Image Understanding & Vision Safeguards (Requirement B) ────────────

def test_image_processing_and_thumbnails():
    img = Image.new("RGB", (320, 240), color=(100, 150, 200))
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    jpeg_bytes = buf.getvalue()

    result = AttachmentProcessor.process_attachment("sample_photo.jpg", jpeg_bytes)
    assert result["category"] == "image"
    assert result["metadata"]["dimensions"]["width"] == 320
    assert result["metadata"]["dimensions"]["height"] == 240
    assert result["base64"] is not None
    assert result["thumbnail_base64"] is not None
    assert result["dataUrl"].startswith("data:image/jpeg;base64,")


def test_vision_safeguard_when_no_vision_model_installed():
    """Text-only models must NEVER be falsely treated as vision models.
    Bond must explain the limitation and offer ollama pull command."""
    from app.ai.ai_service import AIService

    mock_client = MagicMock()
    mock_client.is_model_installed.return_value = True

    # Setup text-only model registry (e.g. only llama3.2:3b is installed)
    mock_registry = MagicMock()
    mock_registry.supports_capability.return_value = False
    mock_registry.get_models_with_capability.return_value = []

    with patch("app.ai.ai_service.QThreadPool"), \
         patch("app.ai.ai_service.QTimer"), \
         patch("app.ai.ai_service.ModelManager") as mock_mm_cls, \
         patch("app.ai.model_capability_registry.get_model_capability_registry", return_value=mock_registry):

        mock_mm = MagicMock()
        mock_mm.is_available.return_value = True
        mock_mm.active_model = "llama3.2:3b"
        mock_mm.installed_models = ["llama3.2:3b", "qwen2.5:3b"]
        mock_mm_cls.return_value = mock_mm

        ai = AIService(client=mock_client)
        ai.model_capability_registry = mock_registry

        # User uploads an image
        attachments = [{
            "id": "att_img",
            "name": "diagram.png",
            "category": "image",
            "extension": "png",
            "size": 500,
            "base64": "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==",
            "metadata": {"dimensions": {"width": 800, "height": 600}},
        }]

        with patch.object(ai.thread_pool, "start") as mock_start:
            gen_id = ai.ask(
                user_prompt="What is happening in this diagram?",
                attachments=attachments,
            )
            assert gen_id > 0
            # Check worker dispatched with helpful explanation
            assert mock_start.called
            worker = mock_start.call_args[0][0]
            assert "no local vision-capable model is currently installed" in worker.response_text
            assert "ollama pull gemma3:4b" in worker.response_text


def test_vision_routing_when_vision_model_installed():
    """When a vision model is installed, Bond routes images to it."""
    from app.ai.ai_service import AIService

    mock_client = MagicMock()
    mock_client.is_model_installed.return_value = True

    mock_registry = MagicMock()
    mock_registry.supports_capability.side_effect = lambda m, cap: m == "gemma3:4b" and cap == ModelCapability.VISION
    vision_profile = ModelProfile(
        model_id="gemma3:4b",
        display_name="Gemma 3 (4B Vision)",
        installed=True,
        size_bytes=3000000000,
        size_formatted="3.0 GB",
        quantization="Q4_K_M",
        family="gemma3",
        families=["gemma3"],
        parameter_size="4B",
        context_capacity=8192,
        estimated_vram_mb=3200,
        capabilities=[ModelCapability.VISION, ModelCapability.GENERAL_CONVERSATION],
    )
    mock_registry.get_models_with_capability.return_value = [vision_profile]

    with patch("app.ai.ai_service.QThreadPool"), \
         patch("app.ai.ai_service.QTimer"), \
         patch("app.ai.ai_service.ModelManager") as mock_mm_cls, \
         patch("app.ai.model_capability_registry.get_model_capability_registry", return_value=mock_registry):

        mock_mm = MagicMock()
        mock_mm.is_available.return_value = True
        mock_mm.active_model = "gemma3:4b"
        mock_mm.installed_models = ["gemma3:4b", "llama3.2:3b"]
        mock_mm_cls.return_value = mock_mm

        ai = AIService(client=mock_client)
        ai.model_capability_registry = mock_registry

        attachments = [{
            "id": "att_img",
            "name": "photo.jpg",
            "category": "image",
            "extension": "jpg",
            "size": 1000,
            "base64": "fake_base64_data",
        }]

        with patch.object(ai.thread_pool, "start"):
            gen_id = ai.ask(
                user_prompt="Describe this picture.",
                attachments=attachments,
            )
            assert gen_id > 0
            assert ai.config.model == "gemma3:4b"


# ─── 3. PDF Processing (Requirement C) ─────────────────────────────────────

def test_pdf_page_aware_extraction_and_citations():
    """Create a 3-page PDF and verify page markers [Page 1], [Page 2], [Page 3] are preserved."""
    writer = pypdf.PdfWriter()
    p1 = writer.add_blank_page(width=300, height=300)
    p2 = writer.add_blank_page(width=300, height=300)
    p3 = writer.add_blank_page(width=300, height=300)

    buf = io.BytesIO()
    writer.write(buf)
    pdf_bytes = buf.getvalue()

    text, meta = extract_pdf_structured(pdf_bytes)
    assert meta["page_count"] == 3
    assert len(meta["pages"]) == 3
    assert meta["pages"][0]["page_number"] == 1
    assert meta["pages"][1]["page_number"] == 2
    assert meta["pages"][2]["page_number"] == 3


def test_large_pdf_relevance_retrieval_and_page_citations():
    """Large PDFs exceeding context budget must prioritize Page 1 and query-relevant pages."""
    pages_data = [
        {"page_number": 1, "text": "Executive Summary: Annual report overview of Company XYZ.", "char_count": 55},
        {"page_number": 2, "text": "Legal notices and standard boilerplate disclosures.", "char_count": 50},
        {"page_number": 3, "text": "Historical timeline of product launches from 2010 to 2020.", "char_count": 58},
        {"page_number": 4, "text": "Financial projections: Net revenue in Q4 exceeded expectations by 45%.", "char_count": 70},
        {"page_number": 5, "text": "Appendix A: Glossary of internal corporate acronyms.", "char_count": 52},
    ]

    meta = {"page_count": 5, "pages": pages_data}
    text, result_meta = _retrieve_relevant_pdf_pages_helper(
        pages_data=pages_data,
        query="What were the financial projections and net revenue?",
        max_chars=250,
        meta=meta,
    )

    # Page 1 (overview) and Page 4 (financial match) must be included
    assert "Page 1" in text
    assert "Page 4" in text
    assert "Financial projections" in text
    assert 4 in result_meta["relevant_page_numbers"]


def _retrieve_relevant_pdf_pages_helper(pages_data, query, max_chars, meta):
    from app.ai.attachment_processor import _retrieve_relevant_pdf_pages
    return _retrieve_relevant_pdf_pages(pages_data, query, max_chars, meta)


# ─── 4. Word and Text Documents (Requirement D) ────────────────────────────

def test_docx_structured_headings_and_tables():
    import docx
    doc = docx.Document()
    doc.add_heading("Project Alpha Architecture", level=1)
    doc.add_paragraph("This document outlines the system components.")
    doc.add_heading("Database Schema", level=2)
    
    table = doc.add_table(rows=2, cols=2)
    table.cell(0, 0).text = "Table"
    table.cell(0, 1).text = "Description"
    table.cell(1, 0).text = "users"
    table.cell(1, 1).text = "Authentication credentials"

    buf = io.BytesIO()
    doc.save(buf)
    docx_bytes = buf.getvalue()

    text, meta = extract_docx_structured(docx_bytes)
    assert meta["heading_count"] >= 2
    assert "Project Alpha Architecture" in meta["headings"]
    assert "# Project Alpha Architecture" in text
    assert "## Database Schema" in text
    assert "| Table | Description |" in text
    assert "| users | Authentication credentials |" in text


def test_markdown_and_plain_text_extraction():
    md_content = "# Guide to Bond\n\nBond is an offline personal AI.\n\n## Capabilities\n- Local inference\n- Vision support\n"
    text, meta = extract_text_structured(md_content.encode("utf-8"), "guide.md")
    assert meta["char_count"] == len(md_content)
    assert meta["word_count"] > 10
    assert "Guide to Bond" in meta["headings"]
    assert "Capabilities" in meta["headings"]


# ─── 5. Spreadsheet Processing & Statistics (Requirement E) ────────────────

def test_spreadsheet_csv_statistical_profiling():
    csv_data = (
        "Region,Sales,Quantity,Status\n"
        "North,1500,25,Active\n"
        "South,2500,40,Active\n"
        "East,1000,15,Pending\n"
        "West,3000,50,Active\n"
        "North,2000,30,Active\n"
    ).encode("utf-8")

    text, meta = SpreadsheetProfiler.analyze_csv(csv_data)
    assert meta["row_count"] == 5
    assert meta["col_count"] == 4

    # Verify column statistics
    cols = {c["name"]: c for c in meta["columns"]}
    assert cols["Sales"]["type"] == "Numeric"
    assert cols["Sales"]["min"] == 1000.0
    assert cols["Sales"]["max"] == 3000.0
    assert cols["Sales"]["sum"] == 10000.0
    assert cols["Sales"]["mean"] == 2000.0
    assert cols["Sales"]["median"] == 2000.0

    assert cols["Quantity"]["sum"] == 160.0
    assert cols["Status"]["type"] == "Text"

    # Verify markdown profile text
    assert "Dataset Dimensions: 5 rows × 4 columns" in text
    assert "Min=1000.0, Max=3000.0" in text
    assert "| North | 1500 | 25 | Active |" in text


def test_spreadsheet_xlsx_multi_sheet_profiling():
    wb = openpyxl.Workbook()
    ws1 = wb.active
    ws1.title = "Revenue"
    ws1.append(["Department", "Q1", "Q2"])
    ws1.append(["Engineering", 120000, 135000])
    ws1.append(["Marketing", 45000, 52000])

    ws2 = wb.create_sheet("Headcount")
    ws2.append(["Office", "Staff"])
    ws2.append(["NYC", 45])
    ws2.append(["London", 30])

    buf = io.BytesIO()
    wb.save(buf)
    xlsx_bytes = buf.getvalue()

    text, meta = SpreadsheetProfiler.analyze_xlsx(xlsx_bytes)
    assert "Revenue" in meta["sheet_names"]
    assert "Headcount" in meta["sheet_names"]
    assert "Spreadsheet Profile: Revenue" in text
    assert "Spreadsheet Profile: Headcount" in text
    assert "Engineering" in text


# ─── 6. Audio Processing with Faster-Whisper (Requirement F) ───────────────

def test_audio_wav_metadata_and_transcription():
    # Generate 1-second 16kHz mono WAV file
    sample_rate = 16000
    samples = [int(1000 * np.sin(2 * np.pi * 440 * t / sample_rate)) for t in range(sample_rate)]
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(struct.pack("<" + "h" * len(samples), *samples))
    wav_bytes = buf.getvalue()

    mock_engine = MagicMock()
    mock_engine.ensure_model_loaded.return_value = True
    mock_res = MagicMock()
    mock_res.text = "Hello, this is a test voice note."
    mock_res.language = "en"
    mock_engine.transcribe.return_value = mock_res

    content, meta = process_audio_attachment(
        file_bytes=wav_bytes,
        filename="voicenote.wav",
        storage_path="",
        whisper_engine=mock_engine,
    )

    assert meta["duration_sec"] == 1.0
    assert meta["sample_rate"] == 16000
    assert meta["transcribed"] is True
    assert "Hello, this is a test voice note." in content
    assert "Duration: 1.0s" in content


# ─── 7. Video Processing with OpenCV (Requirement G) ───────────────────────

def test_video_keyframe_extraction_and_grounded_summary():
    # Create temporary 1-second 10-fps MP4 video
    temp_dir = tempfile.gettempdir()
    vid_path = os.path.join(temp_dir, f"test_vid_{int(time.time())}.mp4")
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    out = cv2.VideoWriter(vid_path, fourcc, 10.0, (64, 64))

    for i in range(10):
        frame = np.zeros((64, 64, 3), dtype=np.uint8)
        frame[:, :] = (i * 25, 120, 200)
        out.write(frame)
    out.release()

    with open(vid_path, "rb") as f:
        vid_bytes = f.read()

    content, meta, keyframes = process_video_attachment(
        file_bytes=vid_bytes,
        filename="clip.mp4",
        storage_path=vid_path,
        max_keyframes=4,
    )

    try:
        os.remove(vid_path)
    except Exception:
        pass

    assert meta["frame_count"] == 10
    assert meta["fps"] == 10.0
    assert len(keyframes) > 0
    assert "keyframe_timestamps" in meta
    # Verify keyframe structure
    kf = keyframes[0]
    assert "base64" in kf
    assert "thumbnail_base64" in kf
    assert "timestamp_sec" in kf
    # Verify limitation notice in content
    assert "Limitation Notice" in content
    assert "discrete sampled keyframes" in content


# ─── 8. Multi-Attachment Prompt Context & Security (Requirement H & I) ──────

def test_multi_attachment_prompt_synthesis_and_isolation():
    attachments = [
        {
            "id": "att_1",
            "name": "annual_report.pdf",
            "category": "document",
            "size_formatted": "120 KB",
            "content": "--- [Page 1] ---\nNet profit: $12M.",
        },
        {
            "id": "att_2",
            "name": "financials.xlsx",
            "category": "spreadsheet",
            "size_formatted": "45 KB",
            "content": "--- [Spreadsheet Profile: Q4] ---\nTotal Revenue: $45M.",
        },
        {
            "id": "att_3",
            "name": "store_front.png",
            "category": "image",
            "size_formatted": "80 KB",
            "base64": "fake_img_base64",
            "metadata": {"dimensions": {"width": 800, "height": 600}},
        },
    ]

    prompt_ctx, images, refs = build_multimodal_prompt_context(
        attachments=attachments,
        user_prompt="Compare the profit in the report with the revenue in the spreadsheet.",
    )

    # Check numbered attachment headers
    assert "=== [ATTACHMENT 1: annual_report.pdf" in prompt_ctx
    assert "=== [ATTACHMENT 2: financials.xlsx" in prompt_ctx
    assert "=== [ATTACHMENT 3: store_front.png" in prompt_ctx

    # Check source attribution markers
    assert "[Source: annual_report.pdf]" in prompt_ctx
    assert "[Source: financials.xlsx]" in prompt_ctx
    assert "[Source: store_front.png]" in prompt_ctx

    # Check security isolation boundaries
    assert "<<< UNTRUSTED_ATTACHMENT_DATA: annual_report.pdf >>>" in prompt_ctx
    assert "<<< END_UNTRUSTED_ATTACHMENT_DATA >>>" in prompt_ctx

    # Check that image base64 was extracted
    assert len(images) == 1
    assert images[0] == "fake_img_base64"
    assert len(refs) == 3


# ─── 9. Model Router Multimodal Classification (Requirement J) ──────────────

def test_router_multimodal_task_classification():
    # 1. Vision image -> Image Understanding
    task, _ = TaskDetector.detect_task(
        prompt="Explain this diagram.",
        attachments=[{"name": "diagram.png", "category": "image"}],
    )
    assert task == TaskCategory.IMAGE_UNDERSTANDING

    # 2. Video file -> Image Understanding (visual keyframes)
    task, _ = TaskDetector.detect_task(
        prompt="What happens in this video?",
        attachments=[{"name": "recording.mp4", "category": "video"}],
    )
    assert task == TaskCategory.IMAGE_UNDERSTANDING

    # 3. Document attachment -> Document Summarization
    task, _ = TaskDetector.detect_task(
        prompt="Summarize the key points of this PDF.",
        attachments=[{"name": "thesis.pdf", "category": "document"}],
    )
    assert task == TaskCategory.DOCUMENT_SUMMARIZATION

    # 4. Spreadsheet attachment -> Complex Reasoning
    task, _ = TaskDetector.detect_task(
        prompt="Analyze the sales trends and find the top performing region.",
        attachments=[{"name": "sales.xlsx", "category": "spreadsheet"}],
    )
    assert task == TaskCategory.COMPLEX_REASONING

    # 5. Multi-attachment comparison -> Complex Reasoning
    task, _ = TaskDetector.detect_task(
        prompt="Compare findings across these files.",
        attachments=[
            {"name": "report.pdf", "category": "document"},
            {"name": "data.csv", "category": "spreadsheet"},
        ],
    )
    assert task == TaskCategory.COMPLEX_REASONING
