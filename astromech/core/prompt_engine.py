from jinja2 import Environment, BaseLoader, Undefined


class SilentUndefined(Undefined):
    def __str__(self): return ""
    def __iter__(self): return iter([])
    def __bool__(self): return False


class PromptEngine:
    def __init__(self):
        self._env = Environment(loader=BaseLoader(), undefined=SilentUndefined)
        self._templates: dict[str, str] = {}

    def render(self, template_str, variables):
        return self._env.from_string(template_str).render(**variables)

    def register_template(self, name, template_str):
        self._templates[name] = template_str

    def render_template(self, name, variables):
        template_str = self._templates.get(name)
        if not template_str: return ""
        return self.render(template_str, variables)
