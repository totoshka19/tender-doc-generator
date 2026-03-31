import json
import tempfile
from pathlib import Path

import yaml
from fastapi import FastAPI, File, Form, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse

from engine import generate_document, load_data
from extractor import extract
from validator import validate

BASE_DIR = Path(__file__).parent
OUTPUT_DIR = BASE_DIR / "output"
OUTPUT_DIR.mkdir(exist_ok=True)

app = FastAPI(title="Tender Doc Generator")


@app.get("/", response_class=HTMLResponse)
async def index():
    return (BASE_DIR / "static" / "index.html").read_text(encoding="utf-8")


@app.post("/api/generate")
async def api_generate(
    profile: UploadFile | None = File(default=None),
    tender: UploadFile | None = File(default=None),
    calc: UploadFile | None = File(default=None),
    incoming_docx: UploadFile | None = File(default=None),
    skip_validation: bool = Form(default=False),
):
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)

        # Определяем пути к данным: загруженный файл или дефолтный
        profile_path = _resolve(profile, tmp / "profile.json", BASE_DIR / "data" / "company_profile.json")
        calc_path = _resolve(calc, tmp / "calc.json", BASE_DIR / "data" / "calc.json")

        if incoming_docx:
            docx_path = tmp / "incoming.docx"
            docx_path.write_bytes(await incoming_docx.read())
            extracted = extract(str(docx_path))
            tender_path = tmp / "tender_extracted.json"
            tender_path.write_text(json.dumps(extracted, ensure_ascii=False, indent=2), encoding="utf-8")
        else:
            tender_path = _resolve(tender, tmp / "tender.json", BASE_DIR / "data" / "tender.json")

        try:
            context = load_data(str(profile_path), str(tender_path), str(calc_path))
        except Exception as e:
            return JSONResponse({"status": "error", "errors": [str(e)], "warnings": []})

        errors, warnings = validate(context)
        if errors and not skip_validation:
            return JSONResponse({"status": "validation_error", "errors": errors, "warnings": warnings})

        generated = []
        for mapping_path in sorted((BASE_DIR / "mappings").glob("*.yaml")):
            with open(mapping_path, encoding="utf-8") as f:
                mapping = yaml.safe_load(f)

            filename = Path(mapping["output"]).name
            mapping["template"] = str(BASE_DIR / mapping["template"])
            mapping["output"] = str(OUTPUT_DIR / filename)

            tmp_mapping = tmp / mapping_path.name
            with open(tmp_mapping, "w", encoding="utf-8") as f:
                yaml.dump(mapping, f, allow_unicode=True)

            generate_document(str(tmp_mapping), context)
            generated.append(filename)

        return JSONResponse({"status": "ok", "warnings": warnings, "files": generated})


@app.get("/api/download/{filename}")
async def api_download(filename: str):
    path = OUTPUT_DIR / filename
    if not path.exists() or path.suffix != ".docx":
        return JSONResponse({"error": "File not found"}, status_code=404)
    return FileResponse(
        path,
        filename=filename,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )


def _resolve(upload: UploadFile | None, dest: Path, default: Path) -> Path:
    if upload:
        dest.write_bytes(upload.file.read())
        return dest
    return default
