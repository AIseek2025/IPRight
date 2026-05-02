"""Middleware utilities for the demo backend application."""

import time
import functools
from typing import Callable


def timing_decorator(func: Callable) -> Callable:
    """Decorator that logs function execution time."""

    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        start = time.time()
        result = func(*args, **kwargs)
        elapsed = time.time() - start
        print(f"[TIMING] {func.__name__} took {elapsed:.4f}s")
        return result

    return wrapper


def retry_decorator(max_retries: int = 3, delay: float = 1.0):
    """Decorator that retries a function on failure."""

    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            last_exception = None
            for attempt in range(max_retries):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    last_exception = e
                    if attempt < max_retries - 1:
                        print(f"[RETRY] {func.__name__} attempt {attempt + 1} failed: {e}")
                        time.sleep(delay)
            raise last_exception or RuntimeError(f"{func.__name__} failed after {max_retries} retries")

        return wrapper

    return decorator


def cache_result(ttl_seconds: int = 60):
    """Simple in-memory cache decorator with TTL."""

    def decorator(func: Callable) -> Callable:
        cache = {}

        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            key = (args, tuple(sorted(kwargs.items())))
            now = time.time()

            if key in cache:
                result, timestamp = cache[key]
                if now - timestamp < ttl_seconds:
                    return result

            result = func(*args, **kwargs)
            cache[key] = (result, now)
            return result

        return wrapper

    return decorator


def validate_params(**validators: Callable):
    """Decorator that validates function parameters."""

    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            param_names = func.__code__.co_varnames[:func.__code__.co_argcount]
            all_params = dict(zip(param_names, args))
            all_params.update(kwargs)

            for param_name, validator in validators.items():
                if param_name in all_params:
                    value = all_params[param_name]
                    if not validator(value):
                        raise ValueError(f"Validation failed for parameter '{param_name}': value={value}")

            return func(*args, **kwargs)

        return wrapper

    return decorator


def paginate(items: list, page: int = 1, page_size: int = 20) -> dict:
    """Paginate a list of items."""
    total = len(items)
    total_pages = (total + page_size - 1) // page_size
    start = (page - 1) * page_size
    end = start + page_size

    return {
        "items": items[start:end],
        "pagination": {
            "page": page,
            "page_size": page_size,
            "total": total,
            "total_pages": total_pages,
            "has_next": page < total_pages,
            "has_previous": page > 1,
        },
    }


def filter_by_fields(items: list, **filters) -> list:
    """Filter a list of dicts by field values."""
    result = items
    for field, value in filters.items():
        if value is not None and value != "":
            result = [item for item in result if str(item.get(field, "")).lower() == str(value).lower()]
    return result


def search_in_fields(items: list, query: str, fields: list[str]) -> list:
    """Search for a query string across multiple fields."""
    if not query:
        return items
    query_lower = query.lower()
    result = []
    for item in items:
        for field in fields:
            field_value = str(item.get(field, "")).lower()
            if query_lower in field_value:
                result.append(item)
                break
    return result


def sort_by_field(items: list, field: str, order: str = "asc") -> list:
    """Sort a list of dicts by a field."""
    reverse = order.lower() == "desc"
    try:
        return sorted(items, key=lambda x: x.get(field, ""), reverse=reverse)
    except TypeError:
        return sorted(items, key=lambda x: str(x.get(field, "")), reverse=reverse)
