import re

from django import template
from django.utils.html import escape
from django.utils.safestring import mark_safe

register = template.Library()


@register.filter
def highlight(text, query):
    """Escape `text` and wrap case-insensitive matches of `query` in <mark>."""
    escaped = escape(text)
    query = (query or "").strip()
    if not query:
        return mark_safe(escaped)
    pattern = re.compile(re.escape(escape(query)), re.IGNORECASE)
    return mark_safe(pattern.sub(lambda m: f"<mark>{m.group(0)}</mark>", escaped))
