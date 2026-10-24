from PIL import Image

from django.conf import settings


def avatar_transform(img):
    diff = abs(img.width - img.height) // 2
    if img.width > img.height:
        left, upper, right, lower = diff, 0, img.width - diff, img.height
    else:
        left, upper, right, lower = 0, diff, img.width, img.height - diff
    img = img.crop((left, upper, right, lower))
    return img.resize(settings.MAX_AVATAR_SIZE, resample=Image.Resampling.LANCZOS)


def post_image_transform(img):
    img.thumbnail(settings.MAX_SIZE, resample=Image.Resampling.LANCZOS)
    return img
