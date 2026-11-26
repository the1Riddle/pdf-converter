"""Command-line setup and PDF to EPUB conversion."""
import argparse
from ctypes.util import find_library
from getpass import getpass
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from tempfile import NamedTemporaryFile


def config_path():
    root = os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config"
    return Path(root) / "pconv" / "config.json"


def missing_poppler():
    missing = [name for name in ("pdfinfo", "pdftoppm") if not shutil.which(name)]
    if sys.platform.startswith("linux") and not find_library("poppler-glib"):
        missing.append("libpoppler-glib")
    return missing


def setup_poppler():
    missing = missing_poppler()
    if not missing:
        return
    if sys.platform == "darwin" and shutil.which("brew"):
        command = ["brew", "install", "poppler"]
    elif sys.platform.startswith("linux") and shutil.which("apt-get"):
        command = ["apt-get", "install", "poppler-utils", "libpoppler-glib8"]
        if os.geteuid() != 0:
            command.insert(0, "sudo")
    else:
        raise ValueError("Install Poppler and add its bin directory to PATH. Missing: " + ", ".join(missing))
    subprocess.run(command, check=True)
    if missing_poppler():
        raise ValueError("Poppler setup is incomplete: " + ", ".join(missing_poppler()))


def initialize(local):
    from pdf_craft import DeepSeekOCRLocalConfig, PDFCraft
    setup_poppler()
    path = config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    if local:
        try:
            import torch
        except ImportError as error:
            raise ValueError("Install the fork with the [local] extra and CUDA-enabled PyTorch.") from error
        if not torch.cuda.is_available():
            raise ValueError("Local OCR requires CUDA-enabled PyTorch and a compatible NVIDIA GPU.")
        cache = path.parent / "models"
        PDFCraft().predownload_models(ocr=DeepSeekOCRLocalConfig(models_cache_path=cache))
        config = {"backend": "local"}
    else:
        print("Remote OCR sends PDF pages to the official DeepSeek OCR service.")
        config = {"backend": "deepseek"}
        if not os.environ.get("DEEPSEEK_API_KEY"):
            key = getpass("DeepSeek API key (saved to your user config): ").strip()
            if not key:
                raise ValueError("An API key is required for remote OCR.")
            config["api_key"] = key
    with NamedTemporaryFile(mode="w", dir=path.parent, delete=False, encoding="utf-8") as handle:
        temp = Path(handle.name)
        try:
            json.dump(config, handle)
            handle.close()
            temp.replace(path)
        finally:
            temp.unlink(missing_ok=True)
    print("Setup complete. Run pconv path/to/book.pdf")


def convert(source, output):
    from pdf_craft import DeepSeekOfficialOCRConfig, DeepSeekOCRLocalConfig, PDFCraft, PDFOptions
    source = source.expanduser()
    if not source.is_file() or source.suffix.lower() != ".pdf":
        raise ValueError(f"Expected an existing PDF file: {source}")
    if output is None:
        output = Path.home() / "Documents" / source.with_suffix(".epub").name
    else:
        output = output.expanduser()
        if output.is_dir():
            output = output / source.with_suffix(".epub").name
        elif not output.suffix:
            output = output.with_suffix(".epub")
    if output.suffix.lower() != ".epub" or output.exists() or output.is_symlink():
        raise ValueError(f"Choose an unused .epub output path: {output}")
    path = config_path()
    if not path.is_file():
        raise ValueError("Run pconv init first.")
    config = json.loads(path.read_text(encoding="utf-8"))
    if config["backend"] == "local":
        ocr = DeepSeekOCRLocalConfig(models_cache_path=path.parent / "models", local_only=True)
    elif config["backend"] == "deepseek":
        key = os.environ.get("DEEPSEEK_API_KEY") or config.get("api_key")
        if not key:
            raise ValueError("Set DEEPSEEK_API_KEY or rerun pconv init.")
        ocr = DeepSeekOfficialOCRConfig(key)
    else:
        raise ValueError("Unknown OCR backend. Rerun pconv init.")
    output.parent.mkdir(parents=True, exist_ok=True)
    PDFCraft(pdf=PDFOptions(ocr=ocr)).convert_pdf_to_epub(source, output)
    print(output.resolve())


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    try:
        if argv[:1] == ["init"]:
            parser = argparse.ArgumentParser(prog="pconv init", description="Set up Poppler and OCR.")
            parser.add_argument("--local", action="store_true", help="download models for local NVIDIA GPU OCR")
            initialize(parser.parse_args(argv[1:]).local)
        else:
            parser = argparse.ArgumentParser(prog="pconv", description="Convert a PDF to EPUB. First run pconv init.")
            parser.add_argument("source", type=Path, help="PDF file")
            parser.add_argument("output", type=Path, nargs="?", help="output filename or existing directory (default: ~/Documents)")
            args = parser.parse_args(argv)
            convert(args.source, args.output)
    except (OSError, ValueError, EOFError, RuntimeError, subprocess.CalledProcessError) as error:
        print(f"pconv: {error}", file=sys.stderr)
        return 1
    return 0
