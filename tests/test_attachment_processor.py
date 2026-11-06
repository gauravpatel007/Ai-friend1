import io
import os
import tempfile
import pytest
from unittest.mock import MagicMock, patch
from PIL import Image

from app.ai.attachment_processor import (
    AttachmentProcessor,
    FileCategory,
    SUPPORTED_EXTENSIONS,
    verify_magic_bytes,
    get_temp_upload_dir,
    cleanup_stale_temp_uploads,
)


def test_supported_extensions_mapping():
    assert SUPPORTED_EXTENSIONS[".png"] == FileCategory.IMAGE
    assert SUPPORTED_EXTENSIONS[".jpg"] == FileCategory.IMAGE
    assert SUPPORTED_EXTENSIONS[".jpeg"] == FileCategory.IMAGE
    assert SUPPORTED_EXTENSIONS[".webp"] == FileCategory.IMAGE

    assert SUPPORTED_EXTENSIONS[".pdf"] == FileCategory.DOCUMENT
    assert SUPPORTED_EXTENSIONS[".docx"] == FileCategory.DOCUMENT
    assert SUPPORTED_EXTENSIONS[".txt"] == FileCategory.DOCUMENT
    assert SUPPORTED_EXTENSIONS[".md"] == FileCategory.DOCUMENT

    assert SUPPORTED_EXTENSIONS[".csv"] == FileCategory.SPREADSHEET
    assert SUPPORTED_EXTENSIONS[".xlsx"] == FileCategory.SPREADSHEET

    assert SUPPORTED_EXTENSIONS[".wav"] == FileCategory.AUDIO
    assert SUPPORTED_EXTENSIONS[".mp3"] == FileCategory.AUDIO
    assert SUPPORTED_EXTENSIONS[".m4a"] == FileCategory.AUDIO

    assert SUPPORTED_EXTENSIONS[".mp4"] == FileCategory.VIDEO
    assert SUPPORTED_EXTENSIONS[".mov"] == FileCategory.VIDEO


def test_validate_file_valid():
    sample_bytes = b"%PDF-1.4\n1 0 obj\n<<>>\nendobj"
    is_valid, err, cat = AttachmentProcessor.validate_file("document.pdf", sample_bytes)
    assert is_valid is True
    assert err is None
    assert cat == FileCategory.DOCUMENT

    png_bytes = b"\x89PNG\r\n\x1a\n" + b"\x00" * 30
    is_valid, err, cat = AttachmentProcessor.validate_file("photo.PNG", png_bytes)
    assert is_valid is True
    assert err is None
    assert cat == FileCategory.IMAGE


def test_validate_file_unsupported_extension():
    is_valid, err, cat = AttachmentProcessor.validate_file("script.exe", b"MZ\x90\x00\x03")
    assert is_valid is False
    assert "Unsupported file type" in err

    is_valid, err, cat = AttachmentProcessor.validate_file("malicious.bat", b"@echo off")
    assert is_valid is False
    assert "Unsupported file type" in err

    is_valid, err, cat = AttachmentProcessor.validate_file("script.sh", b"#!/bin/sh")
    assert is_valid is False
    assert "Unsupported file type" in err


def test_validate_file_size_exceeded():
    large_header = b"\x00" * 10
    is_valid, err, cat = AttachmentProcessor.validate_file(
        "huge.mp4",
        large_header,
        existing_total_size=0,
    )
    # Testing size exceeding by passing large existing total or dummy large bytes
    oversized = b"\x00" * (26 * 1024 * 1024)
    is_valid, err, cat = AttachmentProcessor.validate_file("huge.mp4", oversized)
    assert is_valid is False
    assert "exceeds maximum size limit" in err


def test_magic_bytes_detection():
    # Valid PNG
    png_header = b"\x89PNG\r\n\x1a\n" + b"\x00" * 20
    assert verify_magic_bytes(".png", png_header) is True

    # Fake PNG containing plain text or executable
    fake_png = b"MZ\x90\x00\x03\x00\x00\x00" + b"\x00" * 20
    assert verify_magic_bytes(".png", fake_png) is False

    # Valid PDF
    pdf_header = b"%PDF-1.4\n%..."
    assert verify_magic_bytes(".pdf", pdf_header) is True
    assert verify_magic_bytes(".pdf", b"Not a PDF header") is False

    # Valid JPEG
    jpeg_header = b"\xff\xd8\xff\xe0\x00\x10JFIF"
    assert verify_magic_bytes(".jpg", jpeg_header) is True
    assert verify_magic_bytes(".jpg", b"\x00\x00\x00\x00") is False

    # Valid Zip-based DOCX / XLSX
    zip_header = b"PK\x03\x04" + b"\x00" * 20
    assert verify_magic_bytes(".docx", zip_header) is True
    assert verify_magic_bytes(".xlsx", zip_header) is True

    # Valid WAV
    wav_header = b"RIFF" + b"\x00" * 4 + b"WAVE"
    assert verify_magic_bytes(".wav", wav_header) is True


def test_process_plain_text():
    content = "Hello, Bond! This is a test text attachment with UTF-8 characters: \u0915\u094d\u0937\u092e\u093e."
    data = content.encode("utf-8")

    result = AttachmentProcessor.process_attachment(
        filename="test_notes.txt",
        content_bytes=data,
    )

    assert result["category"] == "document"
    assert "txt" in result["extension"]
    assert "Hello, Bond!" in result["content"]
    assert result["size"] == len(data)


def test_process_csv():
    csv_data = "Item,Price,Quantity\nApple,1.5,10\nBanana,0.8,20\n".encode("utf-8")
    result = AttachmentProcessor.process_attachment(
        filename="groceries.csv",
        content_bytes=csv_data,
    )
    assert result["category"] == "spreadsheet"
    assert "Item,Price,Quantity" in result["content"]
    assert "Apple" in result["content"]


def test_process_docx():
    import docx
    doc = docx.Document()
    doc.add_heading("Meeting Minutes", level=1)
    doc.add_paragraph("Action item: Upgrade local models for Bond.")
    
    buf = io.BytesIO()
    doc.save(buf)
    docx_bytes = buf.getvalue()

    result = AttachmentProcessor.process_attachment(
        filename="meeting.docx",
        content_bytes=docx_bytes,
    )
    assert result["category"] == "document"
    assert "Meeting Minutes" in result["content"]
    assert "Action item: Upgrade local models for Bond." in result["content"]


def test_process_xlsx():
    import openpyxl
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Sales"
    ws.append(["Region", "Revenue"])
    ws.append(["North", 50000])
    ws.append(["South", 75000])

    buf = io.BytesIO()
    wb.save(buf)
    xlsx_bytes = buf.getvalue()

    result = AttachmentProcessor.process_attachment(
        filename="sales.xlsx",
        content_bytes=xlsx_bytes,
    )
    assert result["category"] == "spreadsheet"
    assert "Sheet: Sales" in result["content"]
    assert "North" in result["content"]
    assert "75000" in result["content"]


def test_process_image():
    # Create test image (120x80 RGB)
    img = Image.new("RGB", (120, 80), color=(255, 100, 50))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    png_bytes = buf.getvalue()

    result = AttachmentProcessor.process_attachment(
        filename="photo.png",
        content_bytes=png_bytes,
    )

    assert result["category"] == "image"
    assert result["base64"] is not None
    assert len(result["base64"]) > 0
    assert result["thumbnail_base64"] is not None
    assert result["metadata"]["dimensions"]["width"] == 120
    assert result["metadata"]["dimensions"]["height"] == 80


def test_api_upload_and_delete():
    from fastapi.testclient import TestClient
    from app.api.server import create_app

    app = create_app()
    client = TestClient(app)

    # 1. Single file upload
    test_content = b"Content of uploaded file for testing."
    files = {"file": ("test_upload.txt", test_content, "text/plain")}
    response = client.post("/api/upload", files=files)
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    attachment = data["attachment"]
    assert attachment["name"] == "test_upload.txt"
    assert attachment["category"] == "document"
    assert "Content of uploaded file" in attachment["content"]
    attachment_id = attachment["id"]

    # 2. Delete uploaded file
    del_res = client.delete(f"/api/upload/{attachment_id}")
    assert del_res.status_code == 200
    assert del_res.json()["status"] == "ok"

    # 3. Multiple files upload
    files_multi = [
        ("files", ("file1.txt", b"First text file", "text/plain")),
        ("files", ("file2.csv", b"col1,col2\nval1,val2", "text/csv")),
    ]
    multi_res = client.post("/api/upload/multiple", files=files_multi)
    assert multi_res.status_code == 200
    multi_data = multi_res.json()
    assert multi_data["status"] == "ok"
    assert len(multi_data["attachments"]) == 2
    assert multi_data["attachments"][0]["name"] == "file1.txt"
    assert multi_data["attachments"][1]["name"] == "file2.csv"


def test_ai_service_attachment_injection():
    from app.ai.ai_service import AIService

    mock_client = MagicMock()
    mock_client.is_model_installed.return_value = True

    with patch("app.ai.ai_service.QThreadPool"), patch("app.ai.ai_service.QTimer"), patch("app.ai.ai_service.ModelManager") as mock_mm_cls:
        mock_mm = MagicMock()
        mock_mm.is_available.return_value = True
        mock_mm.active_model = "gemma3:4b"
        mock_mm_cls.return_value = mock_mm

        ai = AIService(client=mock_client)

        attachments = [
            {
                "id": "att_1",
                "name": "annual_report.txt",
                "category": "document",
                "extension": "txt",
                "size": 100,
                "content": "Profit increased by 40% in Q4.",
            },
            {
                "id": "att_2",
                "name": "diagram.png",
                "category": "image",
                "extension": "png",
                "size": 500,
                "base64": "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==",
            },
        ]

        gen_id = ai.ask(
            user_prompt="Please summarize this report and explain the diagram.",
            attachments=attachments,
        )

        assert gen_id > 0
        # Check that user turn has document content and image placeholder
        user_msgs = [m for m in ai.context._history if m.get("role") == "user"]
        assert len(user_msgs) > 0
        last_turn = user_msgs[-1]["content"]
        assert "Profit increased by 40% in Q4." in last_turn
        assert "[Attached Image: diagram.png" in last_turn
