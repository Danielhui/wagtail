from __future__ import absolute_import, unicode_literals

from django import template
from django.template.defaulttags import token_kwargs
from django.utils.encoding import force_text
from django.utils.safestring import mark_safe

from wagtail import __version__
from wagtail.wagtailcore.models import Page
from wagtail.wagtailcore.rich_text import RichText, expand_db_html
from wagtail.wagtailcore.utils import accepts_kwarg

register = template.Library()


@register.simple_tag(takes_context=True)
def pageurl(context, page):
    """
    Outputs a page's URL as relative (/foo/bar/) if it's within the same site as the
    current page, or absolute (http://example.com/foo/bar/) if not.
    """
    try:
        current_site = context['request'].site
    except (KeyError, AttributeError):
        # request.site not available in the current context; fall back on page.url
        return page.url

    # RemovedInWagtail113Warning - this accepts_kwarg test can be removed when we drop support
    # for relative_url methods which omit the `request` kwarg
    if accepts_kwarg(page.relative_url, 'request'):
        # Pass page.relative_url the request object, which may contain a cached copy of
        # Site.get_site_root_paths()
        # This avoids page.relative_url having to make a database/cache fetch for this list
        # each time it's called.
        return page.relative_url(current_site, request=context.get('request'))
    else:
        return page.relative_url(current_site)


@register.simple_tag(takes_context=True)
def slugurl(context, slug):
    """Returns the URL for the page that has the given slug."""
    page = Page.objects.filter(slug=slug).first()

    if page:
        # call pageurl() instead of page.relative_url() here so we get the ``accepts_kwarg`` logic
        return pageurl(context, page)
    else:
        return None

    try:
        current_site = context['request'].site
    except (KeyError, AttributeError):
        # request.site not available in the current context; fall back on page.url
        return page.url

    return page.relative_url(current_site)


@register.simple_tag
def wagtail_version():
    return __version__


@register.filter
def richtext(value):
    if isinstance(value, RichText):
        # passing a RichText value through the |richtext filter should have no effect
        return value
    elif value is None:
        html = ''
    else:
        html = expand_db_html(value)

    return mark_safe('<div class="rich-text">' + html + '</div>')


class IncludeBlockNode(template.Node):
    def __init__(self, block_var, extra_context, use_parent_context):
        self.block_var = block_var
        self.extra_context = extra_context
        self.use_parent_context = use_parent_context

    def render(self, context):
        try:
            value = self.block_var.resolve(context)
        except template.VariableDoesNotExist:
            return ''

        if hasattr(value, 'render_as_block'):
            if self.use_parent_context:
                new_context = context.flatten()
            else:
                new_context = {}

            if self.extra_context:
                for var_name, var_value in self.extra_context.items():
                    new_context[var_name] = var_value.resolve(context)

            return value.render_as_block(context=new_context)
        else:
            return force_text(value)


@register.tag
def include_block(parser, token):
    """
    Render the passed item of StreamField content, passing the current template context
    if there's an identifiable way of doing so (i.e. if it has a `render_as_block` method).
    """
    tokens = token.split_contents()

    try:
        tag_name = tokens.pop(0)
        block_var_token = tokens.pop(0)
    except IndexError:
        raise template.TemplateSyntaxError("%r tag requires at least one argument" % tag_name)

    block_var = parser.compile_filter(block_var_token)

    if tokens and tokens[0] == 'with':
        tokens.pop(0)
        extra_context = token_kwargs(tokens, parser)
    else:
        extra_context = None

    use_parent_context = True
    if tokens and tokens[0] == 'only':
        tokens.pop(0)
        use_parent_context = False

    if tokens:
        raise template.TemplateSyntaxError("Unexpected argument to %r tag: %r" % (tag_name, tokens[0]))

    return IncludeBlockNode(block_var, extra_context, use_parent_context)
