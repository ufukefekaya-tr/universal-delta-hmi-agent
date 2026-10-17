# SPDX-License-Identifier: Apache-2.0
import hashlib


class AgentError(ValueError):
    def __init__(self, code, message, **details):
        self.code, self.message, self.details = code, message, details
        super().__init__(message)

    def as_dict(self):
        return {'code': self.code, 'message': self.message, 'details': self.details}


def digest(data):
    return hashlib.sha256(data).hexdigest()


def require(condition, code, message, **details):
    if not condition:
        raise AgentError(code, message, **details)
