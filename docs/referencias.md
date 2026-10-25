# Referencias

Las referencias se citan en los documentos como **[R#]**. Se agrupan por tema; el número es estable.

## Ingeniería del software y arquitectura

- **[R1]** Brooks, F. P. (1987). *No Silver Bullet — Essence and Accidents of Software Engineering*. IEEE Computer, 20(4), 10-19.
  → Complejidad esencial frente a accidental; motivación para que las personas se centren en lo funcional.
- **[R2]** Lehman, M. M. (1980). *Programs, life cycles, and laws of software evolution*. Proceedings of the IEEE, 68(9), 1060-1076.
  → Cambio continuo y complejidad creciente; justifica un mantenimiento basado en regeneración y verificación.
- **[R28]** Burns, B., Grant, B., Oppenheimer, D., Brewer, E., Wilkes, J. (2016). *Borg, Omega, and Kubernetes*. ACM Queue, 14(1). También en Communications of the ACM, 59(5).
  → Estado deseado, controladores y reconciliación; separación plano de control / plano de datos.
- **[R29]** Humble, J., Farley, D. (2010). *Continuous Delivery*. Addison-Wesley.
  → Tubería de despliegue con puertas de calidad automáticas.
- **[R30]** Forsgren, N., Humble, J., Kim, G. (2018). *Accelerate: The Science of Lean Software and DevOps*. IT Revolution.
  → Métricas de entrega y relación entre automatización y rendimiento.
- **[R31]** Ford, N., Parsons, R., Kua, P. (2017). *Building Evolutionary Architectures*. O'Reilly. (2.ª ed. 2023, con P. Sadalage).
  → Funciones de aptitud para proteger propiedades arquitectónicas.
- **[R32]** Parnas, D. L. (1972). *On the criteria to be used in decomposing systems into modules*. Communications of the ACM, 15(12), 1053-1058.
  → Ocultación de información; contratos entre planos.
- **[R33]** Meyer, B. (1992). *Applying "Design by Contract"*. IEEE Computer, 25(10), 40-51.
  → Contratos verificables: catálogo y documentos de pantalla.
- **[R34]** Cockburn, A. (2005). *Hexagonal Architecture* (Ports and Adapters). alistair.cockburn.us.
  → Adaptadores de modelos y de datos.
- **[R39]** Preston-Werner, T. *Semantic Versioning 2.0.0*. https://semver.org
  → Versionado de contratos y catálogo.
- **[R40]** Nygard, M. (2011). *Documenting Architecture Decisions*. Cognitect blog.
  → Formato de los ADR.
- **[R41]** Brown, S. *The C4 model for visualising software architecture*. https://c4model.com
  → Vistas de contexto y contenedores.

## Desarrollo dirigido por modelos y por especificaciones

- **[R3]** Object Management Group (2014). *MDA Guide revision 2.0* (ormsc/14-06-01).
  → Modelos independientes de plataforma y transformación a implementaciones.
- **[R4]** Schmidt, D. C. (2006). *Model-Driven Engineering*. IEEE Computer, 39(2), 25-31.
  → Lenguajes de modelado específicos de dominio y generadores.
- **[R5]** Hutchinson, J., Whittle, J., Rouncefield, M., Kristoffersen, S. (2011). *Empirical assessment of MDE in industry*. ICSE 2011, 471-480.
  → Beneficios reales ligados a lenguajes específicos pequeños y factores organizativos.
- **[R6]** Whittle, J., Hutchinson, J., Rouncefield, M. (2014). *The State of Practice in Model-Driven Engineering*. IEEE Software, 31(3), 79-85.
  → El éxito llega usando MDE en partes concretas, conviviendo con código manual.
- **[R37]** GitHub (2025). *Spec Kit: spec-driven development toolkit*. https://github.com/github/spec-kit
  → Especificación y plan escritos por personas como guía de agentes de desarrollo.

## Requisitos, pruebas y trazabilidad

- **[R18]** ISO/IEC/IEEE 29148:2018. *Systems and software engineering — Life cycle processes — Requirements engineering*.
  → Requisitos no ambiguos, verificables y trazables.
- **[R19]** Gotel, O., Finkelstein, A. (1994). *An analysis of the requirements traceability problem*. Proceedings of ICRE '94, 94-101.
  → Trazabilidad requisito-implementación-prueba.
- **[R20]** Adzic, G. (2011). *Specification by Example*. Manning.
  → Especificaciones ejecutables como documentación viva.
- **[R21]** North, D. (2006). *Introducing BDD*. Better Software.
  → Formato Dado/Cuando/Entonces.
- **[R22]** Evans, E. (2003). *Domain-Driven Design*. Addison-Wesley.
  → Lenguaje ubicuo y contextos delimitados.

## Interfaces generadas por agentes

- **[R8]** A2UI — *Agent-to-User Interface* (Google, con contribuciones de CopilotKit). Especificación v0.9.1 (actual) y v1.0 (candidata). https://a2ui.org · https://github.com/a2ui-project/a2ui
  → UI declarativa sobre catálogo de confianza, lista plana con `id`, enlaces JSON Pointer, acciones y errores de validación.
- **[R9]** Vercel Labs. *json-render: The Generative UI framework*. https://github.com/vercel-labs/json-render
  → Catálogo con esquemas como fuente del prompt; registro de implementaciones; streaming.
- **[R10]** Brooks, R. (2021). *A Deep Dive into Airbnb's Server-Driven UI System*. Airbnb Engineering & Data Science.
  → Server-driven UI en producción: pantallas, secciones y acciones.
- **[R38]** AG-UI — *Agent-User Interaction Protocol*. https://docs.ag-ui.com
  → Protocolo de eventos entre aplicaciones y agentes; interrupciones con intervención humana.

## Modelos de lenguaje: generación, corrección y evaluación

- **[R7]** Willard, B. T., Louf, R. (2023). *Efficient Guided Generation for Large Language Models*. arXiv:2307.09702. Ver también la documentación de salida estructurada de Ollama (https://docs.ollama.com/capabilities/structured-outputs) y de Azure OpenAI.
  → Decodificación restringida a esquemas.
- **[R11]** Anthropic (2024). *Building effective agents*. https://www.anthropic.com/research/building-effective-agents
  → Preferir flujos simples y componibles; patrón *evaluator-optimizer*.
- **[R12]** Huang, J., Chen, X., Mishra, S., et al. (2024). *Large Language Models Cannot Self-Correct Reasoning Yet*. ICLR 2024. arXiv:2310.01798.
  → Sin retroalimentación externa, la autocorrección no es fiable.
- **[R13]** Olausson, T. X., Inala, J. P., Wang, C., Gao, J., Solar-Lezama, A. (2024). *Is Self-Repair a Silver Bullet for Code Generation?* ICLR 2024. arXiv:2306.09896.
  → La reparación depende de la calidad de la retroalimentación.
- **[R14]** Madaan, A., et al. (2023). *Self-Refine: Iterative Refinement with Self-Feedback*. NeurIPS 2023. arXiv:2303.17651.
  → Refinamiento iterativo con retroalimentación.
- **[R15]** Shinn, N., et al. (2023). *Reflexion: Language Agents with Verbal Reinforcement Learning*. NeurIPS 2023. arXiv:2303.11366.
  → Agentes que mejoran con señales de evaluación.
- **[R16]** Jimenez, C. E., et al. (2024). *SWE-bench: Can Language Models Resolve Real-World GitHub Issues?* ICLR 2024. arXiv:2310.06770.
  → Pruebas como oráculo para evaluar reparaciones de agentes.
- **[R17]** Zheng, L., et al. (2023). *Judging LLM-as-a-Judge with MT-Bench and Chatbot Arena*. NeurIPS 2023 (Datasets and Benchmarks). arXiv:2306.05685.
  → Utilidad y sesgos (posición, extensión, autopreferencia) de los modelos como jueces.

## Ingeniería de sistemas con aprendizaje automático

- **[R35]** Sculley, D., et al. (2015). *Hidden Technical Debt in Machine Learning Systems*. NeurIPS 2015.
  → Código de pegamento, dependencias de datos no declaradas, bucles ocultos.
- **[R36]** Amershi, S., et al. (2019). *Software Engineering for Machine Learning: A Case Study*. ICSE-SEIP 2019.
  → Prácticas de ingeniería específicas para sistemas con modelos.

## Supervisión humana y automatización

- **[R23]** Parasuraman, R., Sheridan, T. B., Wickens, C. D. (2000). *A model for types and levels of human interaction with automation*. IEEE Transactions on Systems, Man, and Cybernetics — Part A, 30(3), 286-297.
  → Niveles de automatización por tipo de función y riesgo.
- **[R24]** Bainbridge, L. (1983). *Ironies of automation*. Automatica, 19(6), 775-779.
  → Riesgos de la supervisión de sistemas automatizados.
- **[R25]** Amershi, S., et al. (2019). *Guidelines for Human-AI Interaction*. CHI 2019.
  → Diseño de la interacción en las intervenciones.
- **[R26]** NIST (2023). *Artificial Intelligence Risk Management Framework (AI RMF 1.0)*. NIST AI 100-1.
  → Gobernar, mapear, medir y gestionar riesgos de IA.
- **[R27]** Reglamento (UE) 2024/1689 del Parlamento Europeo y del Consejo (Reglamento de Inteligencia Artificial), artículo 14 (supervisión humana).
  → Supervisión humana efectiva y trazabilidad.

## Estándares técnicos

- RFC 6901 — *JavaScript Object Notation (JSON) Pointer*.
- RFC 6902 — *JavaScript Object Notation (JSON) Patch*.
- JSON Schema 2020-12 — https://json-schema.org
- Design Tokens Community Group (W3C) — formato de tokens de diseño (DTCG).

> **Nota:** las referencias académicas se han citado por autor, título, publicación y año; antes de un uso formal externo conviene verificar paginación y DOI en la fuente.
