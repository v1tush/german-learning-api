from PIL import Image
import io

from django.conf import settings
from django.core.files.base import ContentFile

from core.exceptions import (
    WrongImageTypeError,
    WrongFileSizeError,
    TooManyPixelsError,
    WrongFileTypeError,
)
from core.utils import avatar_transform, post_image_transform


def _process_and_compress_image(file, max_resolution, resize_func):
    img = Image.open(file)

    if img.width * img.height > max_resolution:
        raise TooManyPixelsError("Image resolution is too high")

    original_format = img.format
    img = resize_func(img)

    bytes_io = io.BytesIO()
    save_format = original_format if original_format else "JPEG"
    img.save(bytes_io, format=save_format)

    return ContentFile(bytes_io.getvalue(), name=file.name)


def validate_avatar(file):
    if file.content_type not in settings.IMAGE_ALLOWED_TYPES:
        raise WrongImageTypeError("Avatar should be jpeg, png or webp")
    if file.size > settings.AVATAR_SIZE:
        raise WrongFileSizeError(
            f"Avatar should not be more than {settings.AVATAR_SIZE / 1024 / 1024:.0f} MB"
        )
    return _process_and_compress_image(
        file, settings.MAX_AVATAR_RESOLUTION, avatar_transform
    )

#
# def validate_attachment(file):
#     if file.content_type in settings.IMAGE_ALLOWED_TYPES:
#         max_size = settings.IMAGE_SIZE
#         file_type = PostAttachment.Type.IMAGE
#     elif file.content_type in settings.VIDEO_ALLOWED_TYPES:
#         max_size = settings.VIDEO_SIZE
#         file_type = PostAttachment.Type.VIDEO
#     else:
#         raise WrongFileTypeError(
#             f"File should be one of these type: "
#             f"{', '.join(settings.ALLOWED_EXTENSIONS_HUMAN)}"
#         )
#
#     if file.size > max_size:
#         raise WrongFileSizeError(
#             f"{file_type} should not be more than {max_size / 1024 / 1024:.0f} MB"
#         )
#
#     if file_type == PostAttachment.Type.VIDEO:
#         return file, file_type.value
#
#     return (
#         _process_and_compress_image(
#             file, settings.MAX_IMAGE_RESOLUTION, post_image_transform
#         ),
#         file_type.value,
#     )
