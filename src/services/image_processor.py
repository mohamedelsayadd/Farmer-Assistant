from pathlib import Path

from fastapi import HTTPException, Request
from starlette.datastructures import UploadFile

from models.schemas.chat import UploadedImage

ALLOWED_IMAGE_EXTENSIONS = {".jpeg", ".jpg", ".png", ".webp"}


def is_supported_image_file(file: UploadFile) -> bool:
    return Path(file.filename or "").suffix.lower() in ALLOWED_IMAGE_EXTENSIONS


async def read_image_file(request: Request, image_file: UploadFile) -> UploadedImage:
    if not is_supported_image_file(image_file):
        allowed = sorted(ALLOWED_IMAGE_EXTENSIONS)
        raise HTTPException(status_code=422, detail=f"image_file must be one of: {allowed}.")

    image_bytes = await image_file.read()
    max_image_bytes = request.app.state.plant_disease_max_image_bytes
    if len(image_bytes) > max_image_bytes:
        raise HTTPException(status_code=413, detail="image_file is too large.")
    if not image_bytes:
        raise HTTPException(status_code=422, detail="image_file must not be empty.")

    return UploadedImage(
        filename=image_file.filename or "plant-image",
        content_type=image_file.content_type,
        content=image_bytes,
    )
