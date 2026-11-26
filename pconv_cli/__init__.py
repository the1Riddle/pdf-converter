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


PROVIDERS = {
    "deepseek": ("DEEPSEEK_API_KEY", None),
    "openai": ("OPENAI_API_KEY", "https://api.openai.com/v1"),
    "google": ("GEMINI_API_KEY", "https://generativelanguage.googleapis.com/v1beta/openai"),
    "anthropic": ("ANTHROPIC_API_KEY", "https://api.anthropic.com/v1"),
}


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


def initialize(local, provider, model):
    setup_poppler()
    path = config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    if local:
        from pdf_craft import DeepSeekOCRLocalConfig, PDFCraft
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
        env_key, _ = PROVIDERS[provider]
        print(f"Remote OCR sends PDF pages to {provider}.")
        config = {"backend": provider}
        if model:
            config["model"] = model
        if not os.environ.get(env_key):
            key = getpass(f"{provider} API key (saved to your user config): ").strip()
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
    from pdf_craft import ConcurrentExecutor, DeepSeekOfficialOCRConfig, DeepSeekOCRLocalConfig
    from pdf_craft import FixedCapacity, PDFCraft, PDFOptions
    from pdf_craft.ocr_config import VisionChatOCRConfig

    provider = config.get("backend")
    executor = None
    if provider == "local":
        ocr = DeepSeekOCRLocalConfig(models_cache_path=path.parent / "models", local_only=True)
    elif provider in PROVIDERS:
        env_key, endpoint = PROVIDERS[provider]
        key = os.environ.get(env_key) or config.get("api_key")
        if not key:
            raise ValueError(f"Set {env_key} or rerun pconv init.")
        executor = ConcurrentExecutor(FixedCapacity(1))
        if provider == "deepseek":
            ocr = DeepSeekOfficialOCRConfig(key)
        else:
            if not config.get("model") or endpoint is None:
                raise ValueError("Missing vision model. Rerun pconv init with --provider and --model.")
            ocr = VisionChatOCRConfig(base_url=endpoint, api_key=key, model=config["model"], provider=provider)
    else:
        raise ValueError("Unknown OCR backend. Rerun pconv init.")
    output.parent.mkdir(parents=True, exist_ok=True)
    PDFCraft(pdf=PDFOptions(ocr=ocr, ocr_executor=executor)).convert_pdf_to_epub(source, output)
    print(output.resolve())


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    try:
        if argv[:1] == ["init"]:
            parser = argparse.ArgumentParser(prog="pconv init", description="Set up Poppler and OCR.")
            backend = parser.add_mutually_exclusive_group()
            backend.add_argument("--provider", choices=PROVIDERS, default="deepseek")
            backend.add_argument("--local", action="store_true", help="download models for local NVIDIA GPU OCR")
            parser.add_argument("--model", help="vision-capable chat model ID from your provider")
            args = parser.parse_args(argv[1:])
            if bool(args.model and args.model.strip()) != (args.provider != "deepseek"):
                parser.error("--model is required for OpenAI, Google and Anthropic only")
            initialize(args.local, args.provider, args.model)
        else:
            parser = argparse.ArgumentParser(prog="pconv", description="Convert a PDF to EPUB. First run pconv init.")
            parser.add_argument("source", type=Path, help="PDF file")
            parser.add_argument("output", type=Path, nargs="?", help="output filename or existing directory (default: ~/Documents)")
            if not argv:
                parser.print_help()
                return 0
            args = parser.parse_args(argv)
            convert(args.source, args.output)
    except (OSError, ValueError, EOFError, RuntimeError, subprocess.CalledProcessError) as error:
        print(f"pconv: {error}", file=sys.stderr)
        return 1
    return 0
