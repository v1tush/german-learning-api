class WrongImageTypeError(Exception):
    code = 422


class WrongFileTypeError(Exception):
    code = 422


class WrongFileSizeError(Exception):
    code = 413


class TooManyPixelsError(Exception):
    code = 400
