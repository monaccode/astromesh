from jinja2 import BaseLoader, Environment, Undefined


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

    def evaluate(self, expression, variables):
        """Evalúa una EXPRESIÓN Jinja (sin llaves) y devuelve el valor, no un string.

        El `when` de `spec.prefetch` se evalúa acá y no con `render`: `{{ rows }}`
        de una lista vacía renderiza "[]", que no es vacío. Una variable indefinida
        da `None`, y `a and a.b` corta antes de leer `b` de algo indefinido.
        """
        return self._env.compile_expression(expression, undefined_to_none=True)(**variables)

    def compile_expression(self, expression):
        """Compila una EXPRESIÓN Jinja sin evaluarla — para validar sintaxis al cargar.

        Levanta `jinja2.TemplateSyntaxError` si `expression` no parsea. No lee
        ninguna variable, así que una expresión que referencia algo que sólo
        existe en runtime (p.ej. `prefetch.x`) sigue siendo válida acá.
        """
        self._env.compile_expression(expression, undefined_to_none=True)

    def compile_template(self, template_str):
        """Compila un TEMPLATE Jinja sin renderizarlo — para validar sintaxis al cargar."""
        self._env.from_string(template_str)

    def register_template(self, name, template_str, scope=None):
        self._templates[(scope, name)] = template_str

    def render_template(self, name, variables, scope=None):
        template_str = self._templates.get((scope, name))
        if not template_str:
            return ""
        return self.render(template_str, variables)
