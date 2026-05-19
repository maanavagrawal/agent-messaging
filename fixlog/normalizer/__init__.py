from fixlog.normalizer.models import ErrorKind, PythonErrorSignature


def normalize_python_error(raw: str) -> PythonErrorSignature:
    from fixlog.normalizer.python import normalize_python_error as normalize

    return normalize(raw)

__all__ = ["ErrorKind", "PythonErrorSignature", "normalize_python_error"]
