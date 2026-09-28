from jinja2 import BaseLoader, Undefined
from jinja2.exceptions import SecurityError
from jinja2.sandbox import ImmutableSandboxedEnvironment


class SilentUndefined(Undefined):
    # El sandbox devuelve un Undefined (no levanta) al leer un atributo prohibido
    # como `''.__class__`; silenciarlo haría que el ataque renderice vacío y pase
    # inadvertido. Ése sí levanta, así la corrida falla igual que con el resto.
    def _bloquear(self):
        if self._undefined_exception is SecurityError:
            self._fail_with_undefined_error()

    def __str__(self):
        self._bloquear()
        return ""

    def __iter__(self):
        self._bloquear()
        return iter([])

    def __bool__(self):
        self._bloquear()
        return False


class PromptEngine:
    def __init__(self):
        # Sandbox: el system prompt lo escribe el tenant (personas de OFFICIUM,
        # plantillas de Centuria). Con un `Environment` pelado,
        # `{{ ''.__class__.__mro__[1].__subclasses__() }}` ejecutaba código en el
        # pod compartido. Inmutable porque ningún template del repo muta nada
        # (`.append`, `.update`...) y así un prompt tampoco puede tocar el
        # contexto de la corrida. Un acceso bloqueado levanta
        # `jinja2.exceptions.SecurityError` y NO se atrapa acá: la corrida falla
        # entera en vez de caer a un prompt parcial (fijado por
        # tests/test_prompt_engine_sandbox.py::test_la_corrida_falla_con_un_prompt_ssti).
        self._env = ImmutableSandboxedEnvironment(loader=BaseLoader(), undefined=SilentUndefined)
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
