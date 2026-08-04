# Changelog

Formato basado en [Keep a Changelog](https://keepachangelog.com/).

## [Unreleased]

### Added
- `map` puede invocar capacidades: `equipos | map({g: garantia(sku=sku)})` la llama
  una vez por elemento, en paralelo, con los campos del elemento en scope. Es el
  patrón que los modelos escriben apenas hay una colección y era el bloqueante para
  que un programa con listas llegara a ejecutarse.
- Tope de invocaciones concurrentes (`max_fanout`, 16 por defecto): un `map` sobre
  mil elementos no puede disparar mil pedidos a la vez.
- El compilador valida las capacidades invocadas dentro de una etapa, así que un
  nombre mal escrito falla en compilación y no a mitad de la ejecución.

### Fixed
- Ligar el mismo nombre en el `if` y en el `else` ya no se toma como reasignación:
  corre una sola de las dos ramas.
- Claves de dict entre comillas (`{"oem": x}`) y los literales `None`/`True`/`False`
  de Python, que el modelo escribe porque escribe Python.
- Pipear una capacidad sin llamarla devuelve un error que enseña la forma correcta
  en vez de un error de sintaxis genérico.

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
