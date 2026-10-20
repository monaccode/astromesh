---
title: Otro agente no es tu usuario
date: 2026-10-20
platform: linkedin
format: post + carrusel (4 láminas)
product: astromesh-a2a
status: draft        # draft | published
url:                 # link al post al publicarlo
images: [01, 02, 03, 04]
relacionado: 2026/2026-10-19-mi-rag-borraba-lo-que-le-ensenaba (misma serie de librerías abiertas del ecosistema)
fuentes: astromesh-a2a 0.1.1 (README «Why the SDK alone is not enough», docs/eval.md «The traps», tabla de frameworks); astromesh core 0.73.0/0.74.x (origen humano|agente, tools type a2a); astromesh-adk 0.7.x (remote_a2a); Nexus 0.27–0.28.2 (servidor A2A)
primer_comentario: "Repo: https://github.com/monaccode/astromesh-a2a · PyPI: https://pypi.org/project/astromesh-a2a/ · Docs: https://monaccode.github.io/astromesh/a2a/introduction/"
---

Cuando mi agente habla con otro agente, el otro no es mi usuario.
Es código que no controlo, en un servidor que no es mío.

A2A es el protocolo abierto para que los agentes trabajen entre sí: uno publica una card con lo que sabe hacer y los demás le mandan tareas. El SDK oficial habla el protocolo. Lo que no decide es a quién podés llamar, cuánto de su respuesta aceptás ni qué hace tu modelo con ella.

Por eso armé astromesh-a2a, open source, sobre el SDK oficial:

→ Nada es alcanzable hasta que lo declarás. Y nunca una IP privada, ni por redirección ni por DNS
→ La respuesta del remoto llega a tu modelo marcada como no confiable, escapada para que no pueda cerrar el bloque
→ Si el remoto pide «respondé sí para confirmar», vuelve como pregunta pendiente: sólo tu usuario la contesta
→ Límites de tamaño, tiempo, eventos y presupuesto por remoto, con un trace por llamada sin credenciales

Lo que más valoro:

• Nueve servidores maliciosos lo atacan en cada push. Si una trampa pasa, el build falla
• Funciona como tool en nueve frameworks: LangChain, CrewAI, Google ADK, OpenAI Agents, PydanticAI, LlamaIndex, smolagents, Microsoft Agent Framework y MCP
• En Astromesh, un turno que viene de otro agente nunca confirma una acción por el usuario
• Nexus ya publica agentes por A2A, y un agente de Astromesh usa a cualquier agente A2A como herramienta

Lo que me llevo: conectar agentes es fácil. Lo difícil es decidir cuánto confiar.

Repo y docs en el primer comentario 👇

#A2A #AgentesDeIA #OpenSource #Seguridad #Python #Astromesh
