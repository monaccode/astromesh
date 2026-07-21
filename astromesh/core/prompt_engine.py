from jinja2 import Environment, BaseLoader, Undefined


class SilentUndefined(Undefined):
    def __str__(self):
        return ""

    def __iter__(self):
        return iter([])

    def __bool__(self):
        return False


class PromptEngine:
    def __init__(self):
        self._env = Environment(loader=BaseLoader(), undefined=SilentUndefined)
        # Clave por (scope, name). El scope es el nombre del agente dueño del template,
        # o None para los globales. Sin él, dos agentes con un template homónimo se
        # pisaban en silencio — inaceptable en un runtime que sirve a varios tenants.
        self._templates: dict[tuple[str | None, str], str] = {}

    def render(self, template_str, variables):
        return self._env.from_string(template_str).render(**variables)

    def register_template(self, name, template_str, scope=None):
        self._templates[(scope, name)] = template_str

    def render_template(self, name, variables, scope=None):
        template_str = self._templates.get((scope, name))
        if not template_str:
            return ""
        return self.render(template_str, variables)
