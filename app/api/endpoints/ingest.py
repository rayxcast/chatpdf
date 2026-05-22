import shutil
import tempfile
from pathlib import Path
from typing import Annotated, Any

import structlog
from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile

from app.rag.ingestion import ingest_documents

router = APIRouter(prefix="/ingest", tags=["ingest"])
logger = structlog.get_logger()


def _safe_upload_name(filename: str | None, index: int) -> str:
    name = Path(filename or f"upload-{index}").name
    return name or f"upload-{index}"


@router.post("/")
async def ingest(  # noqa: PLR0913
    request: Request,
    path: Annotated[str | None, Form(description="Local dir path inside container")] = None,
    file: Annotated[
        UploadFile | None,
        File(
            description=(
                "Single file upload. Leave unselected and untick 'Send empty value' "
                "if using 'path' instead."
            )
        ),
    ] = None,
    files: Annotated[
        list[UploadFile] | None,
        File(description="Multiple uploaded files."),
    ] = None,
    recreate: Annotated[bool, Form()] = False,
    collection_id: Annotated[str | None, Form()] = None,
) -> dict[str, Any]:
    request_id = getattr(request.state, "request_id", "no-id")
    upload_files = [upload for upload in ([file] if file else []) + (files or []) if upload]
    logger.info(
        "ingest_request_received",
        request_id=request_id,
        path=path,
        filename=file.filename if file else None,
        filenames=[upload.filename for upload in upload_files],
        recreate=recreate,
    )

    try:
        if upload_files:
            with tempfile.TemporaryDirectory() as tmp_dir:
                for index, upload in enumerate(upload_files, start=1):
                    file_path = Path(tmp_dir) / _safe_upload_name(upload.filename, index)
                    with file_path.open("wb") as f:
                        shutil.copyfileobj(upload.file, f)
                result = await ingest_documents(
                    str(Path(tmp_dir)),
                    recreate,
                    request_id=request_id,
                    source_name=(
                        upload_files[0].filename
                        if len(upload_files) == 1
                        else f"{len(upload_files)} uploaded files"
                    ),
                    source_type="upload",
                    collection_id=collection_id,
                )
        elif path:
            result = await ingest_documents(
                path,
                recreate,
                request_id=request_id,
                source_name=path,
                source_type="path",
                collection_id=collection_id,
            )
        else:
            raise HTTPException(400, "Provide 'path' or 'file'")
    except KeyError as error:
        raise HTTPException(404, str(error)) from error

    return result
