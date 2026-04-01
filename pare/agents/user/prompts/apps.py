from __future__ import annotations

from functools import lru_cache
from typing import TYPE_CHECKING

from jinja2.exceptions import TemplateError
from jinja2.sandbox import ImmutableSandboxedEnvironment

if TYPE_CHECKING:
    from jinja2 import Template

    from pare.apps import App

DEFAULT_APP_DESCRIPTIONS_TEMPLATE = """
  Navigable Apps (use open_app from home screen or switch_app):
  {% for app in navigable_apps %}
  - {{ app.name }}: {{ app.description }}
  {% endfor %}

  System Tools (always available):
  {% for app in system_apps %}
  - {{ app.name }}: {{ app.description }}
  {% endfor %}
  """


@lru_cache
def compile_jinja_template(template: str) -> Template:
    """Compile a Jinja template into a callable function."""

    def raise_exception(message: str) -> None:
        raise TemplateError(message)

    jinja_env = ImmutableSandboxedEnvironment(trim_blocks=True, lstrip_blocks=True)
    jinja_env.globals["raise_exception"] = raise_exception
    return jinja_env.from_string(template)


def format_available_apps(apps: list[App], template: str = DEFAULT_APP_DESCRIPTIONS_TEMPLATE) -> str:
    """Format the available apps into a string using the given template.

    Args:
        apps: List of apps to format.
        template: Template to use for formatting.

    Returns:
        Formatted string of available apps.
    """
    # categorize apps
    navigable_apps = []
    system_apps = []

    for app in apps:
        if app.name in ["PAREAgentUserInterface", "HomeScreenSystemApp"]:
            system_apps.append(app)
        else:
            navigable_apps.append(app)

    compiled = compile_jinja_template(template)
    return compiled.render(navigable_apps=navigable_apps, system_apps=system_apps)
