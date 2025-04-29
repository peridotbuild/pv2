"""
Decorators
"""
__all__ = [
        'clean_returned_dict'
]
def clean_returned_dict(defaults: dict = None, fallback: str = "0"):
    """
    Cleans up a returned dict to have default values.
    """
    def decorator(func):
        def wrapper(*args, **kwargs):
            result = func(*args, **kwargs)
            if isinstance(result, dict):
                defaults_ = defaults or {}
                return {k: (v if v not in [None, ""] else defaults_.get(k, fallback))
                        for k, v in result.items()}
            return result
        return wrapper
    return decorator
