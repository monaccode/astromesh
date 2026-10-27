---
title: Un dueño no mira tokens
date: 2026-10-26
platform: linkedin
format: post + carrusel (4 láminas)
product: astromesh-herald
status: draft        # draft | published
url:                 # link al post al publicarlo
images: [01, 02, 03, 04]
relacionado: 2026/2026-10-25-tu-plataforma-necesita-un-experto (serie del ecosistema)
fuentes: astromesh-herald 0.13.0 (CHANGELOG 2026-10-25; internal/server/handlers_admin_reads.go ConversacionesNuevas, maxConversacionesDias = 62; internal/adapters/store/postgres/admin_reads.go, created_at AT TIME ZONE tz; domain.NuevasPorHora {dia, hora, canal, nuevas}); docs-site herald/api-reference
retorica: los números de la lámina 2 son ilustrativos (rotulados); "casi le respondo 400 a todos" está en el CHANGELOG de 0.13.0 («the new route would have answered 400 to every request»), se detectó antes del release; "durante meses mis dashboards…" es recurso narrativo (el /admin/stats previo era de operación: mensajes, outbox, conversaciones activas)
---

Un dueño de negocio no mira tokens. Tampoco latencia, ni costo por llamada.

Mira tres cosas: cuánta gente le escribió, por dónde y a qué hora.

Durante meses mis dashboards respondían lo que a mí me importaba operar. No lo que él necesitaba para decidir. Así que en Herald, el gateway que conecta WhatsApp, Instagram, Messenger, Telegram y web chat con los agentes, agregué una sola pregunta bien hecha:

→ ¿Cuántas conversaciones nuevas hubo, por día, por hora y por canal?
→ Contadas cuando empiezan, no cuando hay actividad. Una conversación que dura tres días cuenta una vez, no tres.
→ En la hora del negocio, no en la del servidor. Un mensaje de las 23 h en Buenos Aires no puede caer a las 2 h del día siguiente.
→ Hasta 62 días por consulta. Suficiente para comparar dos meses, sin dejar que un pedido barra la base entera.

Lo que más aprendí no estaba en la consulta:

• La imagen del servidor no traía zonas horarias. La ruta nueva iba a rechazar con un 400 toda zona real. Lo encontré antes del release: ahora las zonas viajan dentro del binario.
• "Local" es una zona válida para Go y no para Postgres. Un detalle así es un 500 en producción. Ahora es un 400 con el motivo.
• Herald devuelve filas simples. El canal más usado o cuánto llega fuera de horario lo calcula quien muestra el dashboard. Cada capa hace una cosa.

Un agente que atiende bien no alcanza. El dueño tiene que poder ver que atiende.

Docs en el primer comentario 👇

#AIAgents #WhatsApp #CustomerExperience #Observability #SaaS

---

**Primer comentario:**

Herald, referencia de la API: https://monaccode.github.io/astromesh/herald/api-reference/
Herald: https://monaccode.github.io/astromesh/herald/introduction/
Mapa del ecosistema: https://monaccode.github.io/astromesh/#ecosystem
