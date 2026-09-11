class BusinessError(Exception):
    def __init__(self, code, message, status=409, details=None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status
        self.details = details


def require(condition, code, message, status=409):
    if not condition:
        raise BusinessError(code, message, status)
