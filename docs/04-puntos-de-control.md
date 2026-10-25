# 04 · Puntos de control

Este documento define **dónde se detiene el sistema, quién decide y con qué reglas**. Tiene tres partes:

1. **Puertas** (G0-G7): controles automáticos del ciclo de vida.
2. **Clasificación y autonomía**: qué puede hacer el sistema solo y qué no.
3. **Intervenciones** (H1-H6): cuándo y cómo el sistema pide decisión a una persona.

Y dos salvaguardas transversales:

4. **Reglas de plataforma** (RP): invariantes que nadie, ni personas ni agentes, puede saltarse sin cambiar la política.
5. **Funciones de aptitud** (F): comprobaciones automáticas que impiden que la plataforma se vuelva ad hoc o encorsetada.

## 1. Puertas del ciclo de vida

Cada puerta tiene **criterio de entrada, comprobaciones, evidencia producida y salida**. Ninguna ruta las salta (RP-01).

| Puerta | Comprueba | Evidencia | Si falla |
|---|---|---|---|
| **G0 · Admisión** | Entradas válidas contra su esquema; requisitos con identificador, actor y criterio de aceptación (ISO 29148: verificable [R18]); glosario sin términos contradictorios; referencias cruzadas resueltas | Informe de admisión | Versión rechazada con errores localizados (fichero, línea) |
| **G1 · Compilación** | Especificación compilada válida; cada requisito tiene un elemento de especificación; **ambigüedades** detectadas (términos no definidos, reglas sin entidad, criterios no medibles) | Especificación compilada + diferencias con la publicada + lista de ambigüedades | H1 si hay ambigüedades o cambios de especificación |
| **G2 · Planificación** | Cada vista tiene patrón, view model, clase de riesgo y ruta; las vistas manuales tienen componente asignado o pendiente | Plan de construcción | H2 si hay clase alta, manual o cambio de clase |
| **G3 · Generación** | Salida estructurada válida; capas 1-2 del guardián (estructura y enlaces) | Borrador + hallazgos | Reparación (si quedan reintentos) o H3 |
| **G4 · Verificación** | Capas 3-4 del guardián (diseño y políticas); pruebas de conformidad; pruebas de aceptación y E2E (ruta lote); juez consultivo | Informe por artefacto: hallazgos, pruebas, puntuación | Reparación con los hallazgos como entrada, o H3 |
| **G5 · Aprobación** | Política de autonomía de la clase; todos los requisitos afectados `cubiertos`; sin hallazgos bloqueantes | Informe de conformidad + matriz de trazabilidad | H4 si la política lo exige |
| **G6 · Publicación** | Versión completa (no hay vistas declaradas sin artefacto ni reserva); migraciones aprobadas aplicadas; reversión disponible | Registro de publicación | Se mantiene la versión anterior |
| **G7 · Operación** | Señales de ejecución dentro de umbrales; dependencias sin cambios | Métricas y alertas | Revalidación, reparación o H6 |

### 1.1 Severidad de hallazgos

| Severidad | Efecto |
|---|---|
| **Bloqueante** | Impide avanzar. Ej.: componente fuera del catálogo, enlace a ruta inexistente, prueba de aceptación fallida, acción destructiva fuera de confirmación. |
| **Mayor** | Impide la publicación automática; permite publicar con H4. Ej.: puntuación del juez por debajo de umbral, receta incumplida parcialmente. |
| **Menor** | Se registra y se muestra en el informe. Ej.: texto de ayuda genérico. |
| **Autocorregible** | El guardián lo corrige y lo anota (no consume reintentos). Ej.: falta `type` en un botón de cabecera. |

## 2. El juez consultivo

El validador basado en modelo **no aprueba**. Aporta una puntuación por criterio con motivo, para ordenar, detectar problemas que las reglas no cubren y priorizar la revisión humana. Se limita así por la evidencia sobre sesgos de los modelos como jueces [R17] y sobre autocorrección sin retroalimentación externa [R12][R13].

Rúbrica base (configurable por sistema de diseño):

| Criterio | Pregunta | Escala |
|---|---|---|
| Fidelidad funcional | ¿La pantalla permite exactamente lo que dice el requisito, ni más ni menos? | 0-3 |
| Receta | ¿Sigue el patrón y la receta declarados? | 0-3 |
| Claridad | ¿Jerarquía, agrupación y textos son comprensibles para el actor? | 0-3 |
| Tono | ¿Cumple la voz del sistema de diseño? | 0-3 |
| Coherencia | ¿Es coherente con pantallas hermanas ya publicadas? | 0-3 |

Mitigaciones de sesgo: el juez usa **un perfil de modelo distinto** del compositor cuando sea posible; evalúa sin conocer qué modelo generó; se calibra periódicamente con pantallas que las personas ya han valorado.

## 3. Clasificación y autonomía

### 3.1 Clase de riesgo (calculada, no elegida)

La calcula el motor de políticas a partir de la especificación compilada. Reglas por defecto (versionadas en `policies/risk.yaml`, propiedad del desarrollador):

| Factor | Baja | Media | Alta |
|---|---|---|---|
| Escritura de datos | No | Alta o edición | Baja, cambio masivo, operación irreversible |
| Permisos implicados | Lectura pública de la app | Rol estándar | Gestión de permisos o datos sensibles |
| Reglas de negocio afectadas | Ninguna | Validaciones | Reglas críticas (identificadas como tales en la especificación) |
| Entidades | 1 | 1-2 | ≥ 3 o relaciones complejas |
| Regiones | 1 | 2-3 | ≥ 4 |
| Capacidad del catálogo | Suficiente | Suficiente | Suficiente (si no, **manual**) |

La clase es **la máxima** de todos los factores. Si el catálogo no cubre la necesidad, la clase es **manual**.

### 3.2 Niveles de autonomía

Inspirados en los niveles de automatización por función de Parasuraman, Sheridan y Wickens [R23]:

| Nivel | Nombre | El sistema… | La persona… | Se aplica a |
|---|---|---|---|---|
| **A0** | Asistencia | Propone; no actúa | Decide y ejecuta | Especificación compilada, pruebas propuestas, migraciones |
| **A1** | Aprobación previa | Construye y verifica; publica tras aprobación | Aprueba o rechaza (H4) | Clase alta |
| **A2** | Supervisión posterior | Construye, verifica y publica | Revisa después; puede revertir; muestreo obligatorio | Clase media |
| **A3** | Autónomo acotado | Construye, verifica, publica y repara dentro de límites | Recibe informe; auditoría por muestreo | Clase baja |

| Función | Baja | Media | Alta | Manual |
|---|---|---|---|---|
| Generar | A3 | A2 | A1 | A0 |
| Reparar tras fallo de prueba | A3 | A2 | A1 | A0 |
| Publicar | A3 | A2 | A1 | A1 |
| Revalidar por dependencia | A3 | A3 | A3 | A3 |
| Cambiar la especificación | A0 | A0 | A0 | A0 |
| Cambiar pruebas | **Nunca** | **Nunca** | **Nunca** | **Nunca** |
| Migrar datos | A0 | A0 | A0 | A0 |

## 4. Catálogo de intervenciones

El sistema **crea** la intervención, **elige** el rol, **adjunta** la evidencia mínima y **fija** el plazo. La persona decide. Cada intervención es pequeña y concreta: nunca "aprueba todo".

| Id | Disparador | Rol | Evidencia que adjunta el sistema | Decisiones posibles | Plazo orientativo |
|---|---|---|---|---|---|
| **H1 · Aclarar o aprobar especificación** | Ambigüedad detectada en G1, o cualquier cambio en la especificación compilada | Funcional (ambigüedad) / Desarrollador (técnico) | Texto original, interpretación propuesta, alternativas, diferencias | Aprobar · Elegir alternativa · Modificar entradas | 2 días |
| **H2 · Confirmar plan** | Vista de clase alta o manual; cambio de clase; vista nueva sin patrón conocido | Desarrollador | Vista, factores de riesgo, patrón propuesto, estimación | Confirmar · Cambiar ruta · Pedir componente manual | 2 días |
| **H3 · Resolver bloqueo** | Reintentos agotados en G3/G4 | Desarrollador (+ diseño si es de diseño) | Hallazgos, intentos, diferencias entre intentos | Regenerar con indicación · Ruta manual · Ajustar entradas | 1 día |
| **H4 · Aprobar publicación** | Clase alta; hallazgos mayores; migración de datos; regeneración por cambio de modelo | Desarrollador | Informe de conformidad, previsualización, diferencias visuales y de documento, trazabilidad | Aprobar · Rechazar con motivo | 1 día |
| **H5 · Aceptación funcional** | Requisito `verificado` que la política marca para aceptación explícita | Funcional | Requisito, pantallas, pruebas superadas, capturas | Aceptar · Rechazar con motivo (crea cambio funcional) | 3 días |
| **H6 · Incidencia en operación** | Señales de ejecución sobre umbral sin reparación automática posible | Desarrollador | Señales, artefacto, versión, reproducción | Reparar · Revertir · Abrir cambio | Según severidad |

### 4.1 Diseño de las intervenciones (contra las ironías de la automatización)

Para que la supervisión sea real y no un trámite [R24][R25]:

- **Pequeñas y con alcance claro**: una intervención por decisión, no lotes.
- **Con evidencia y diferencias**: qué cambia, por qué, qué pruebas lo respaldan.
- **Con alternativas**: la persona elige entre opciones explicadas, no solo sí o no.
- **Con motivo obligatorio** al rechazar o modificar; el motivo alimenta la siguiente generación.
- **Muestreo de auditoría**: un porcentaje de artefactos publicados automáticamente (A2/A3) se asigna a revisión posterior (por defecto: 20 % en media, 5 % en baja).
- **Métrica de aprobación rutinaria**: si una persona aprueba > 95 % sin cambios en < 30 s, el sistema avisa al responsable de políticas.

## 5. Reglas de plataforma (invariantes)

| Id | Regla |
|---|---|
| **RP-01** | Ningún artefacto llega a usuarios finales sin superar G3 y G4. No hay rutas de excepción. |
| **RP-02** | Los agentes no escriben datos de la aplicación. Toda escritura es un comando declarado, validado y auditado. |
| **RP-03** | El sistema no modifica entradas humanas (documento funcional, diseño, especificaciones técnicas, pruebas). Solo propone cambios como intervención. |
| **RP-04** | No se repara sin hallazgo. Toda reparación cita el hallazgo que la motiva. |
| **RP-05** | Un requisito sin prueba aprobada bloquea la publicación de sus artefactos. |
| **RP-06** | Los artefactos publicados son inmutables y están bloqueados; regenerar exige un cambio de dependencia o una decisión registrada. |
| **RP-07** | Ningún dato real de la aplicación viaja a perfiles de modelo marcados como externos. |
| **RP-08** | Toda migración de datos es reversible, se simula antes y se aprueba (A0). |
| **RP-09** | Toda decisión humana y automática queda registrada con evidencia, versión y autor. |
| **RP-10** | La plataforma no contiene conocimiento de ningún dominio (ver F1). |

## 6. Funciones de aptitud: evitar lo ad hoc y lo encorsetado

Las funciones de aptitud son pruebas automáticas **de la arquitectura**, no de la aplicación [R31]. Se ejecutan en el CI de la plataforma en cada cambio. Hay dos riesgos opuestos:

- **Ad hoc**: la plataforma acumula casos especiales para la primera aplicación y deja de ser genérica.
- **Encorsetado**: la plataforma es tan rígida que cualquier necesidad nueva obliga a salirse de ella.

### 6.1 Contra lo ad hoc

| Id | Función | Cómo se mide |
|---|---|---|
| **F1 · Sin dominio en la plataforma** | El código y los prompts de la plataforma no contienen términos de ningún dominio | Análisis estático: ningún identificador de las especificaciones de las aplicaciones aparece en `platform/` |
| **F2 · Dominio testigo** | La plataforma construye y verifica una segunda aplicación distinta (p. ej. reservas de salas) con las mismas puertas | Pipeline del dominio testigo en verde en cada cambio de plataforma |
| **F3 · Prompts derivados** | Todo prompt se construye a partir de contratos y especificaciones | Prueba: cambiar una etiqueta en la especificación cambia el prompt; no hay cadenas de dominio en plantillas |
| **F4 · Sin rutas paralelas** | Todo artefacto publicado tiene registro de G3-G4 | Consulta sobre el registro: 0 artefactos sin evidencia |
| **F5 · Extensión por tipos** | Las capacidades nuevas se añaden como tipo de artefacto, patrón o componente | Revisión de cambios: modificaciones al reconciliador requieren ADR |
| **F6 · Reglas como datos** | Las reglas del guardián y de riesgo viven en ficheros de diseño y políticas | Análisis estático: 0 condiciones sobre nombres de componente concretos fuera del registro |

### 6.2 Contra lo encorsetado

| Id | Función | Cómo se mide |
|---|---|---|
| **F7 · Ruta manual de primera clase** | Un componente manual se registra y se usa sin tocar la plataforma | Prueba: registrar un componente de ejemplo y generar una vista que lo use |
| **F8 · Catálogo ampliable** | Añadir un componente al catálogo actualiza prompt, validación, documentación y tipos del cliente | Prueba de extremo a extremo con un componente nuevo |
| **F9 · Patrones ampliables** | Añadir un patrón no requiere cambios de código | Prueba con un patrón nuevo en el dominio testigo |
| **F10 · Independencia de modelo** | La batería de evaluación pasa con al menos dos perfiles de modelo | Informe de evaluación por perfil |
| **F11 · Independencia de almacén** | El dominio testigo funciona con dos adaptadores de datos | Pruebas de integración |
| **F12 · Compatibilidad de contrato** | Cambios del contrato siguen versionado semántico; los documentos antiguos se migran o siguen siendo válidos | Validación de documentos publicados contra el nuevo esquema [R39] |

### 6.3 Presupuestos

| Presupuesto | Valor inicial | Acción si se supera |
|---|---|---|
| Nodos por región | 40 | Hallazgo mayor; dividir en regiones |
| Regiones por pantalla | 8 | Hallazgo mayor; revisar patrón |
| Reintentos por artefacto | 1-2 según clase | H3 |
| Coste por versión construida | Definido por aplicación | Aviso al responsable |
| Tiempo de generación a demanda | 30 s | Plantilla de respaldo + encolar en lote |
