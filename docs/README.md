# Eidos · Documentación de arquitectura

> **Versión:** 1.0 (borrador para debate) · **Fecha:** octubre 2026
> **Ámbito:** plataforma para construir y mantener aplicaciones de gestión ligeras cuyas interfaces genera y mantiene un sistema de agentes, a partir de entradas definidas y validadas por personas.

## En una frase

**Las personas definen, diseñan y validan. El sistema construye, verifica, repara y propone. Las reglas de quién interviene, cuándo y con qué criterio las fija la plataforma, no la improvisación.**

## Cómo leer esta documentación

| # | Documento | Para quién | Pregunta que responde |
|---|---|---|---|
| 01 | [Enfoque](01-enfoque.md) | Todo el equipo | ¿Qué proponemos, por qué y qué evidencia lo respalda? ¿Qué no es? |
| 02 | [Arquitectura](02-arquitectura.md) | IA, desarrollo | ¿Cómo está construido el sistema y cómo escala? |
| 03 | [Ciclo de vida y estados](03-ciclo-de-vida.md) | Todo el equipo | ¿Por qué estados pasa cada cosa y qué los mueve? |
| 04 | [Puntos de control](04-puntos-de-control.md) | Todo el equipo | ¿Dónde se detiene el sistema, quién decide y cómo evitamos que se vuelva ad hoc? |
| 05 | [Contratos y formatos](05-contratos.md) | Funcionales, diseño, desarrollo, IA | ¿Qué se escribe, en qué formato y qué produce el sistema? |
| 06 | [Mantenimiento](06-mantenimiento.md) | Desarrollo, IA | ¿Qué pasa cuando cambian requisitos, datos, librerías, diseño o modelos? |
| 07 | [Decisiones (ADR)](07-decisiones.md) | IA, desarrollo | ¿Qué hemos decidido, qué descartamos y por qué? |
| 08 | [Hoja de ruta y piloto](08-hoja-de-ruta.md) | Dirección, todo el equipo | ¿En qué orden se construye y cómo sabremos que funciona? |
| 09 | [Plan de trabajo](09-plan-de-trabajo.md) | Todo el equipo | ¿Qué tareas, quién, con qué criterio de aceptación y en qué estado? |
| — | [Referencias](referencias.md) | Quien quiera profundizar | Bibliografía citada en los documentos |

Las citas aparecen como **[R#]** y remiten a [referencias.md](referencias.md).

## Glosario mínimo

| Término | Definición |
|---|---|
| **Plataforma** | El sistema Eidos: agentes, pipeline, guardián, renderizador. No conoce ningún dominio. |
| **Aplicación** | Lo que se construye con la plataforma a partir de un *paquete de entradas*. Ej.: gestión de usuarios. |
| **Paquete de entradas** | Documento funcional + diseño + especificaciones técnicas + pruebas. Escrito por personas. Versionado en git. |
| **Especificación compilada** | Representación estructurada y validada del paquete de entradas. Es el contrato que usan los agentes. |
| **Artefacto** | Todo lo que produce el sistema: pantallas, migraciones, informes, propuestas de prueba. Tiene estado y procedencia. |
| **Puerta (gate)** | Punto de control automático que un artefacto debe superar para avanzar. |
| **Intervención** | Solicitud formal del sistema a una persona para que decida. Tiene tipo, contexto, plazo y registro. |
| **Clase de riesgo** | Baja, media, alta o manual. La calcula una regla y fija la ruta de construcción y el nivel de autonomía. |
| **Reconciliación** | Bucle que compara el estado deseado (entradas) con el real (artefactos publicados) y actúa sobre la diferencia. |
| **Función de aptitud** | Comprobación automática de una propiedad de la arquitectura (p. ej. "la plataforma no contiene nombres del dominio"). |
