class SufError(Exception):
    """Base project error."""


class ValidationError(SufError):
    pass


class MissingCommandError(SufError):
    pass


class MissingPathError(SufError):
    pass


class ConfirmationError(SufError):
    pass


class UnsafeOperationError(SufError):
    pass
