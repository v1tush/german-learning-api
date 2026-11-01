class ScheduleError(Exception):
    status_code = 422
    code = "schedule_error"


class ScheduleNotFoundError(ScheduleError):
    status_code = 404
    code = "schedule_not_found"


class InvalidDatasetIdError(ScheduleError):
    status_code = 400
    code = "invalid_dataset_id"


class ScheduleHasRunsError(ScheduleError):
    status_code = 409
    code = "schedule_has_runs"


class InsufficientLearningWordsError(ScheduleError):
    code = "insufficient_learning_words"


class InvalidScheduleConfigurationError(ScheduleError):
    code = "invalid_schedule_configuration"
