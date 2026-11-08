"""Public and administrative branding API schemas."""

from pydantic import BaseModel, Field, field_validator


class HeaderIconUpdate(BaseModel):
    image_data_url: str | None = Field(default=None, max_length=700_000)

    @field_validator("image_data_url")
    @classmethod
    def validate_image_data_url(cls, value: str | None) -> str | None:
        if value is None:
            return value
        import base64
        import binascii

        import re

        match = re.fullmatch(r"data:(image/(?:png|jpeg|webp));base64,([A-Za-z0-9+/]*={0,2})", value)
        if match is None:
            raise ValueError("Use a PNG, JPEG, or WebP image.")
        try:
            image = base64.b64decode(match.group(2), validate=True)
        except (ValueError, binascii.Error):
            raise ValueError("Invalid image data.") from None
        if not image or len(image) > 512 * 1024:
            raise ValueError("The image must be non-empty and no larger than 512 KB.")
        mime_type = match.group(1)
        valid = (
            (mime_type == "image/png" and image.startswith(b"\x89PNG\r\n\x1a\n"))
            or (mime_type == "image/jpeg" and image.startswith(b"\xff\xd8\xff"))
            or (
                mime_type == "image/webp"
                and len(image) >= 12
                and image[:4] == b"RIFF"
                and image[8:12] == b"WEBP"
            )
        )
        if not valid:
            raise ValueError("Image contents do not match the declared format.")
        return value


class HeaderIconPublic(BaseModel):
    image_data_url: str | None
