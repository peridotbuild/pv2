"""
Decorators
"""
import functools
import pv2.util.log as pvlog

__all__ = [
        'clean_returned_dict',
        'alias_for'
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

def alias_for(method_name: str, warn: bool = True):
    """
    Sets an alias for a given function and will log a warning if asked.
    """
    def decorator(func):
        @functools.wraps(func)
        def wrapper(self, *args, **kwargs):
            if warn:
                pvlog.logger.warning(
                        "'%s()' is an alias for '%s()' - Please change your code to " +
                        "use the latter.", func.__name__, method_name
                )
            return getattr(self, method_name)(*args, **kwargs)
        return wrapper
    return decorator
