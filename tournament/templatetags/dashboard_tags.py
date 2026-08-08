from django import template

register = template.Library()

@register.filter(name='get_item')
def get_item(dictionary, key):
    if dictionary:
        val = dictionary.get(key)
        if val is None and key is not None:
            val = dictionary.get(str(key))
            if val is None:
                try:
                    val = dictionary.get(int(key))
                except (ValueError, TypeError):
                    pass
        return val
    return None

@register.filter(name='split')
def split(value, key="||"):
    """Splits a string by key delimiter."""
    if value:
        return value.split(key)
    return []

@register.simple_tag
def get_dashboard_users():
    return "" # Dummy tag to prevent crashing

@register.simple_tag
def get_dashboard_tournaments():
    return "" # Add this new dummy tag!