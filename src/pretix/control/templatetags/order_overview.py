from django import template
from django.utils.html import conditional_escape
from django.utils.safestring import mark_safe
from django.utils import formats


register = template.Library()


@register.filter(name='togglesum', needs_autoescape=True)
def cut(value, autoescape=True):
    if autoescape:
        esc = conditional_escape
    else:
        esc = lambda x: x
    return mark_safe('<span class="count">{0}</span><span class="sum">{1}</span>'.format(
        esc(value[0]), esc(formats.localize(value[1]))
    ))
