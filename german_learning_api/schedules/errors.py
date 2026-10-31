class ScheduleError(Exception):
    status_code = 422

    def __init__(self, code: str = "schedule_error"):
        self.code = code
        super().__init__(code)


class ScheduleNotFoundError(ScheduleError):
    status_code = 404
    code = "schedule_not_found"


class InvalidTagIdsError(ScheduleError):
    status_code = 400
    code = "invalid_tag_ids"


class ScheduleHasRunsError(ScheduleError):
    status_code = 409
    code = "schedule_has_runs"


class InsufficientLearningWordsError(ScheduleError):
    code = "insufficient_learning_words"


class UnsupportedDeliveryFormatError(ScheduleError):
    code = "word_delivery_format_required"


class InvalidScheduleConfigurationError(ScheduleError):
    code = "invalid_schedule_configuration"
