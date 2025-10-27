import functools
import inspect
from typing import Any, Callable, TypeVar

F = TypeVar('F', bound=Callable[..., Any])

def enforce_types(func: F) -> F:
    """
    A decorator that enforces type hints at runtime.

    It checks the types of the arguments passed to the decorated function
    and the type of the value it returns against the function's type
    annotations.

    If a type mismatch is found, it raises a TypeError.

    Example:
        @enforce_types
        def greet(name: str, age: int) -> str:
            return f"Hello, {name}! You are {age} years old."

        greet("Alice", 30)  # Works fine
        greet("Bob", "twenty")  # Raises TypeError
    """
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        sig = inspect.signature(func)
        bound_args = sig.bind(*args, **kwargs)
        bound_args.apply_defaults()

        # Check argument types
        for name, value in bound_args.arguments.items():
            if name in func.__annotations__:
                expected_type = func.__annotations__[name]
                if not isinstance(value, expected_type):
                    raise TypeError(
                        f"Argument '{name}' for {func.__name__}() "
                        f"must be {expected_type.__name__}, "
                        f"not {type(value).__name__}"
                    )

        # Execute the function
        result = func(*args, **kwargs)

        # Check return type
        if 'return' in func.__annotations__:
            expected_return_type = func.__annotations__['return']
            if not isinstance(result, expected_return_type):
                raise TypeError(
                    f"Return value of {func.__name__}() "
                    f"must be {expected_return_type.__name__}, "
                    f"not {type(result).__name__}"
                )

        return result
    return wrapper
