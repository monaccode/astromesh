# Changelog

Formato basado en [Keep a Changelog](https://keepachangelog.com/).

## [0.1.0] - 2026-08-03

### Added
- Gramática núcleo: asignación, llamada con argumentos por nombre, pipe con las
  etapas `where`/`top`/`map`, `if/else` y `return`.
- Lexer con bloques por indentación y parser de descenso recursivo.
- Compilador a `PlanGraph`: grafo de dependencias entre sentencias y validación
  contra el catálogo de capacidades antes de ejecutar nada.
- Executor async por olas topológicas: las sentencias independientes corren
  concurrentes.
- `PartialState.to_prompt()`: estado parcial serializado para que el modelo repare
  sin repetir efectos ya aplicados.
- Protocolo `CapabilityProvider` de dos métodos como única frontera con el host.
- `build_system_block()` y `extract_program()` para el lado del prompt.
