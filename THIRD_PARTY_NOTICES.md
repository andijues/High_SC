# Third-party notices

High_SC source code: Copyright (c) 2026 High_SC contributors. Licensed under GNU AGPL v3; see `LICENSE`.

## PyMuPDF / MuPDF

Used for PDF extraction, rendering, and the generated teaching PDF. Copyright belongs to Artifex Software and the respective contributors. PyMuPDF is offered under AGPL and commercial licenses. This project uses the open-source distribution. See [upstream licensing](https://pymupdf.readthedocs.io/en/latest/about.html#license-and-copyright) and the license supplied with the installed package.

## Bundled fonts

- Lora: Copyright 2011 The Lora Project Authors; SIL Open Font License 1.1. See `static/fonts/LICENSES.txt`.
- IBM Plex Sans: Copyright IBM Corp.; SIL Open Font License 1.1. See `static/fonts/IBMPlexSans-OFL.txt` and `static/fonts/LICENSES.txt`.

These font licenses are also embedded in generated reader HTML files. Font names and trademarks belong to their respective owners.

## Runtime dependencies

FastAPI, Starlette, Uvicorn, HTTPX, Pydantic, python-multipart and their dependencies retain their upstream licenses. They are installed by pip and are not vendored in this repository. Exact versions are recorded in `requirements.lock.txt`; installed package metadata contains the corresponding notices.

## Example content

`examples/demo_content.json` and its generated PDF / HTML are original teaching materials created for High_SC and distributed under this project's license. They do not reproduce a third-party research paper or report actual experimental data. User-imported materials are not part of this repository.
