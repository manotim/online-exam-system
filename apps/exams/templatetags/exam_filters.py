# apps/exams/templatetags/exam_filters.py
from django import template

register = template.Library()

@register.filter
def dict_key(d, key):
    """Get a value from a dictionary by key"""
    if isinstance(d, dict):
        return d.get(key, '')
    return ''

@register.filter
def get_item(dictionary, key):
    """Another name for dict_key filter"""
    return dict_key(dictionary, key)