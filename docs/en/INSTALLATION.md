# Installation Guide

This guide is for users of the Python library. Start with the standard package unless you deliberately want OCR models to run on your own NVIDIA GPU.

## pconv command line (this fork)

Install this fork with Python 3.11–3.13. In a virtual environment, run:

```bash
python -m pip install .
pconv init
pconv ~/Downloads/book.pdf
pconv ~/Downloads/book.pdf ~/Books/my-edition.epub
```

With no destination, pconv creates `~/Documents/book.epub`. You can also pass an existing directory. Missing output parent directories are created.

Setup checks Poppler and installs missing system dependencies using apt-get on Debian/Ubuntu or Homebrew on macOS. Other platforms need Poppler installed first (see below). The default backend sends page images to the official DeepSeek OCR service. Set `DEEPSEEK_API_KEY` or enter a key during setup. Prompted keys are saved in the user's pconv configuration. Environment keys are read at conversion time.

For offline conversion on a supported NVIDIA GPU, install this fork with `python -m pip install '.[local]'` and CUDA-enabled PyTorch, then run `pconv init --local` to download the model once. Subsequent conversions use the cached model.

## Choose an installation

For vendor OCR, install:

```bash
python -m pip install pdf-craft
```

Vendor OCR uses a remote service, so CUDA is not required locally. You will still need the provider URL, model name, and credentials in your Python configuration.

For local OCR on a CUDA-capable NVIDIA GPU, install the local extra instead:

```bash
python -m pip install "pdf-craft[local]"
```

The extra supplies the Python runtime for local models. It does not choose a PyTorch wheel for your platform. Install a CUDA-compatible PyTorch build that matches your Python version, driver, and operating system. If you are unsure, use vendor OCR.

## Requirements

- Python `>=3.11,<3.14`
- Poppler for PDF conversion, OCR extraction, and PDF patching. Patching renders
  source pages only to sample local erasure colors; it does not rasterize them into
  the output.
- Ghostscript for PDF patching. It compiles the source page into a visual-only
  layer, so the original text cannot be selected beneath translated text.
- Network and valid credentials for vendor OCR
- A CUDA-capable NVIDIA GPU, matching PyTorch, model storage, and adequate VRAM for local OCR

PySide6/Qt is installed as a Python dependency. PDF patching also needs suitable
local fonts. Vector inline-formula rendering is optional: when enabled it needs
Matplotlib plus a TeX installation whose `latex` command is available. Without either
runtime, or when one formula cannot render, patching continues with readable plain
text for that formula.

Using a virtual environment is recommended:

```bash
python3.11 -m venv .venv
source .venv/bin/activate  # macOS / Linux
# Windows PowerShell: .venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install pdf-craft
```

## Install Poppler

The default PDF reader uses `pdfinfo` and `pdftoppm` with local and vendor OCR.
Publication page labels use Poppler's GLib API; install `libpoppler-glib8` (or the
distribution's ABI-equivalent package) on Linux. macOS Homebrew Poppler supplies
it; Windows deployments must make the corresponding DLLs discoverable to Python.
Custom handlers provide their own business reads/renders; no automatic full-input
validation runs. See [optional input assertions](ERROR_HANDLING.md#optional-input-assertions).


```bash
# macOS
brew install poppler

# Debian / Ubuntu
sudo apt-get update && sudo apt-get install poppler-utils libpoppler-glib8
```

On Windows, install a Poppler binary distribution and add its `bin` directory to `PATH`. The built-in Poppler adapter is selected automatically; `PDFOptions.pdf_handler` is reserved for async custom handlers.

Check the installation with `pdfinfo -v`.

For direct native reads with a non-PATH installation, use
`pdf_pages_count(path, pdf_handler=DefaultPDFHandler(poppler_path=directory))`
(`DefaultPDFHandler` is imported from `pdf_craft.pdf`). The same directory is
used for reading; invalid directories still fail.

Keep the PDF backends current when upgrading an existing deployment. PDF Craft
requires pypdf 6.21.2 or later within the 6.x series. Poppler is installed
separately: updating the Python package does not update the system tools.

```bash
python -m pip install --upgrade pdf-craft
# macOS
brew update
brew upgrade poppler
# Debian / Ubuntu: update to the versions available in your distribution
sudo apt-get update
sudo apt-get install --only-upgrade poppler-utils libpoppler-glib8
```

Backend upgrades do not guarantee that a previously unsupported document becomes compatible.

## Install Ghostscript for PDF patching

PDF patching requires the Ghostscript command-line executable:

```bash
# macOS
brew install ghostscript

# Debian / Ubuntu
sudo apt-get update && sudo apt-get install ghostscript
```

On Windows, install Ghostscript and add `gswin64c.exe` to `PATH`. Confirm that
`gs --version` (or `gswin64c --version`) works in the same environment that
runs Python.

## Optional: vector inline formulas in patched PDFs

`PatchTextOptions(render_inline_formulas=True)` is the default. When Matplotlib and
TeX are available, inline LaTeX is written back as a vector PDF fragment; otherwise
pdf-craft falls back to readable plain text rather than failing the PDF.

Install Matplotlib in the environment running pdf-craft and install a TeX
distribution that exposes `latex` on `PATH`. This is independent of OCR and is not
required when plain-text formula fallback is acceptable.

## Local OCR setup

Run `nvidia-smi` to confirm that the NVIDIA driver and GPU are visible. Then use the [PyTorch installation selector](https://pytorch.org/get-started/locally/) to install an appropriate CUDA build. Confirm it with:

```bash
python -c "import torch; print(torch.__version__); print(torch.cuda.is_available())"
```

Local OCR requires `True`. Models download on first use by default. To pre-download a model and later run without downloads:

```python
from pdf_craft import DeepSeekOCRLocalConfig, PDFCraft, PDFOptions

PDFCraft().predownload_models(ocr=DeepSeekOCRLocalConfig(models_cache_path="models"))
craft = PDFCraft(pdf=PDFOptions(ocr=DeepSeekOCRLocalConfig(
    models_cache_path="models", local_only=True,
)))
```

## Verify the package

```bash
python -c "import pdf_craft; print(pdf_craft.__file__)"
```

This verifies installation only; it does not download a model or call an OCR service. See the [OCR Backend Guide](OCR_BACKENDS.md) for runtime configuration and [Troubleshooting](TROUBLESHOOTING.md) for common setup failures.
