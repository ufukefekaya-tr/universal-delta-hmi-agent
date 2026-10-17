class HmiError(ValueError):
    """An explicit failed gate; never implies a native fallback."""

    def __init__(self, code, message, **context):
        super().__init__(message)
        self.code = code
        self.context = context

    def as_dict(self):
        return {'code': self.code, 'message': str(self), 'context': self.context}
