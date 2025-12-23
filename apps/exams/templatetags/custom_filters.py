# apps/exams/templatetags/custom_filters.py
from django import template

register = template.Library()

@register.filter(name='get_item')
def get_item(dictionary, key):
    """Get an item from a dictionary using a key"""
    if dictionary and key in dictionary:
        return dictionary[key]
    return None

@register.filter
def get(dictionary, key, default=None):
    """Alternative: Get item with default value"""
    if dictionary and key in dictionary:
        return dictionary[key]
    return default