from unittest.mock import patch

import pytest

from pdf_craft import DeepSeekOfficialOCRConfig
from pdf_craft.ocr_config import VisionChatOCRConfig
from pdf_craft.pdf.vendor_ocr import _deepseek_payload
from pdf_craft.pdf.vision_layout import grounded_page
from pconv_cli import main


@pytest.mark.parametrize("provider", ["deepseek", "openai", "google", "anthropic"])
def test_remote_setup_and_conversion(tmp_path, monkeypatch, provider):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    source = tmp_path / "sample.pdf"
    source.touch()
    flags = [] if provider == "deepseek" else ["--provider", provider, "--model", "vision-model"]
    with patch("pconv_cli.setup_poppler"), patch("pconv_cli.getpass", return_value="test-key"):
        assert main(["init", *flags]) == 0
    with patch("pdf_craft.PDFCraft") as craft:
        output = tmp_path / "book.epub"
        assert main([str(source), str(output)]) == 0
        options = craft.call_args.kwargs["pdf"]
        assert options.ocr_executor is not None
        craft.return_value.convert_pdf_to_epub.assert_called_once_with(source, output)
        if provider == "deepseek":
            assert isinstance(options.ocr, DeepSeekOfficialOCRConfig)
        else:
            assert isinstance(options.ocr, VisionChatOCRConfig)
            payload = _deepseek_payload("data:image/png;base64,TEST", options.ocr)
            assert payload["model"] == "vision-model"
            assert "bounding box" in payload["messages"][0]["content"][1]["text"]


def test_page_layout():
    assert grounded_page('[{"kind":"title","box":[2,3,550,80],"text":"Heading"}]') == (
        "<|ref|>title<|/ref|><|det|>[[2, 3, 550, 80]]<|/det|>\nHeading"
    )
    with pytest.raises(ValueError):
        grounded_page('[{"kind":"text","box":[90,12,6,30],"text":"Invalid"}]')
