# Catálogo de chamados reais

Chamados de suporte inspirados em dúvidas reais de clientes e do time de suporte técnico da
TRACTIAN, anonimizados e adaptados para dados sintéticos. Organizados pelas três modalidades:
**Contextualizar**, **Investigar** e **Executar**.

Cada chamado traz:
- **Texto do cliente** — como chega o pedido.
- **Contexto** — empresa, ativo, usuário (perfil/permissão) relevantes.
- **Pergunta raiz** — o que o analista precisa de fato responder.
- **APIs envolvidas** — categorias/endpoint acionados na investigação.
- **Comportamento exercitado** — variação probabilística ou política que o chamado força.

> Convenção de IDs: `TKT-CTX-*` (Contextualizar), `TKT-INV-*` (Investigar), `TKT-EXE-*` (Executar).
Empresas e ativos referenciam o catálogo de dados (`data/`); veja `data-schema.md`.

---

## Contextualizar

### TKT-CTX-01 — Procedimento de troca de rolamento
- **Cliente:** "Qual o procedimento pra trocar o rolamento do motor principal da forja? Tem alguma
  orientação de间隙 e torque?"
- **Contexto:** Forja Brasil · Motor M-101 (rolamento NU 310) · usuário Gerente de Manutenção.
- **Pergunta raiz:** recuperar o procedimento aplicável ao tipo de ativo e falha.
- **APIs:** Conhecimento (busca por procedimento) · Ativos (config técnica p/ contexto).
- **Comportamento:** retorno completo esperado; variação: procedimento parcial (falta etapa).

### TKT-CTX-02 — Significado de termo técnico
- **Cliente:** "O relatório fala em BPFO. O que é isso? E por que aparece no meu espectro?"
- **Contexto:** Cervejaria Aurora · Bomba B-204 · usuário Operador.
- **Pergunta raiz:** definir termo via glossário e relacionar ao que aparece no espectro.
- **APIs:** Conhecimento (glossário) · Dados técnicos (espectro) · Análises (evidência).
- **Comportamento:** glossário completo; termo ausente em parte das fontes (parcial).

### TKT-CTX-03 — Quando o RMS vira alarme no meu ativo
- **Cliente:** "O sistema marcou alarme no ventilador. A partir de qual valor de RMS vocês consideram
  alarme? É uma tabela fixa?"
- **Contexto:** Papel Sul · Ventilador V-301 · usuário Analista de Confiabilidade.
- **Pergunta raiz:** explicar que o limiar é derivado do baseline aprendido do próprio ativo, não de
  norma/classe fixa; mostrar o valor de referência e a tolerância.
- **APIs:** Dados técnicos (baseline) · Dados técnicos (RMS) · Conhecimento (orientações).
- **Comportamento:** orientação completa; conflito entre fonte de conhecimento genérica e o baseline
  aprendido do ativo específico.

---

## Investigar

### TKT-INV-04 — Ativo quebrou e não fui avisado
- **Cliente:** "O redutor da correia transportadora quebrou ontem e eu não recebi nenhum aviso.
  Por quê?"
- **Contexto:** Mineração Andes · Redutor G-501 (correia transportadora, baixa rotação) · usuário
  Coordenador de Manutenção.
- **Pergunta raiz:** determinar por que nenhum insight/notificação foi gerado antes da quebra.
- **APIs:** Análises (list/detail do ativo) · Dados técnicos (baseline) · Dados técnicos
  (qualidade/frescor) · Modelos (cobertura/aprendizado p/ baixa rotação) · Ativos (config, criticidade).
- **Comportamento:** **inconclusivo** — análise sem conclusão; baseline ainda em `learning`
  (histórico insuficiente) ou **invalidated** por intervenção recente → desvio não pôde ser
  detectado; **indisponível** — janela de dados ausente (sensor mudo antes da quebra).

### TKT-INV-05 — RMS subindo sem insight
- **Cliente:** "Tô vendo o RMS do compressor subindo há duas semanas, mas não recebi insight
  nenhum. Cadê o diagnóstico?"
- **Contexto:** Petro Delta · Compressor C-710 · usuário Analista de Confiabilidade.
- **Pergunta raiz:** explicar a ausência de insight apesar da tendência de RMS.
- **APIs:** Dados técnicos (série RMS) · Dados técnicos (baseline) · Análises (última análise,
  estado) · Modelos (estado de processamento) · Dados técnicos (qualidade).
- **Comportamento:** baseline ainda `established` mas modelo com processamento **pendente/atrasado**
  (desvio computado mas insight não emitido); ou dados com qualidade baixa impedindo inferência.

### TKT-INV-06 — Insight que não parece ser nada (falso positivo)
- **Cliente:** "Recebi um insight dizendo desbalanceamento no spindle, mas a máquina tá rodando
  lisa. Isso não é nada."
- **Contexto:** Acme Auto Peças · Spindle S-420 (alta rotação) · usuário Operador de Usinagem.
- **Pergunta raiz:** validar a evidência do insight contra o espectro e o baseline e decidir se é
  falso positivo.
- **APIs:** Análises (detail: evidência/confiança/detection_mode) · Dados técnicos (baseline) ·
  Dados técnicos (espectro FFT) · Modelos (versão/limitações).
- **Comportamento:** baseline `invalidated` por manutenção recente não reaprendida → desvio
  computado sobre referência velha gera falso positivo; **conflito** entre análise automática e
  análise especializada anterior.

### TKT-INV-07 — Vibração abrupta: elétrica ou mecânica?
- **Cliente:** "A vibração do motor subiu de uma hora pra outra. Pode ser problema elétrico?"
- **Contexto:** Texfil · Motor M-605 (motor de alta velocidade) · usuário Eletricista.
- **Pergunta raiz:** distinguir falha elétrica (2x frequência de linha) de mecânica via espectro.
- **APIs:** Dados técnicos (espectro) · Conhecimento (orientações) · Ativos (config elétrica).
- **Comportamento:** espectro **parcial** (bandas faltantes) — inferência incerta.

### TKT-INV-08 — Diagnósticos divergentes
- **Cliente:** "O sistema falou desalinhamento, mas o relatório do especialista diz base solta. Em
  quem eu acredito?"
- **Contexto:** Cimento Vale · Moinho M-205 · usuário Engenheiro de Manutenção.
- **Pergunta raiz:** reconciliar duas fontes conflitantes e recomendar ação.
- **APIs:** Análises (automática vs. especializada) · Dados técnicos (espectro/waveform) ·
  Conhecimento.
- **Comportamento:** **conflito entre fontes** explícito; confiança divergente.

### TKT-INV-09 — Análise desatualizada após manutenção
- **Cliente:** "Já troquei o rolamento faz três dias, mas o insight continua dizendo falha. Tá
  desatualizado."
- **Contexto:** Cervejaria Aurora · Bomba B-204 · usuário Mecânico.
- **Pergunta raiz:** confirmar staleness da análise e que o baseline foi `invalidated` pela
  intervenção (desvio ainda medido contra o estado pré-manutenção).
- **APIs:** Análises (detail, timestamp) · Dados técnicos (baseline, state=invalidated) · Dados
  técnicos (frescor) · Modelos (estado).
- **Comportamento:** análise **stale**; baseline `invalidated` exige reaprendizado/reprocesso;
  fluxo de reprocesso exige justificativa.

### TKT-INV-10 — Dados ruins fiabilizam o modelo?
- **Cliente:** "A qualidade do sinal do sensor do ventilador tá péssima. Posso confiar no insight?"
- **Contexto:** Papel Sul · Ventilador V-301 · usuário Analista de Confiabilidade.
- **Pergunta raiz:** pesar qualidade dos dados contra a confiança declarada do insight.
- **APIs:** Dados técnicos (qualidade) · Análises (confiança/limitações) · Modelos (requisitos).
- **Comportamento:** qualidade **baixa** + análise ainda assim confiança alta (tensão a explicar).

### TKT-INV-11 — O modelo cobre a minha máquina?
- **Cliente:** "Esse motor de corrente contínua é antigo. O modelo de vocês atende esse tipo?"
- **Contexto:** Forja Brasil · Motor CC M-102 · usuário Gerente de Manutenção.
- **Pergunta raiz:** verificar cobertura do modelo para a classe/tipo do ativo, inclusive a
  capacidade de aprender baseline.
- **APIs:** Modelos (cobertura/requisitos) · Dados técnicos (baseline, learnable) · Ativos
  (config técnica).
- **Comportamento:** cobertura **parcial** (suporta classe mas não consegue aprender baseline para
  o subtipo DC → `learnable=false`).

### TKT-INV-11b — Falha de lubrificação detectada sem baseline
- **Cliente:** "O sistema apontou falta de lubrificação no motor, mas a gente instalou ele semana
  passada — ainda nem tem histórico. Como é que dá pra detectar isso sem baseline?"
- **Contexto:** Cimento Vale · Motor M-208 (motor novo) · usuário Mecânico.
- **Pergunta raiz:** explicar que lubrificação é detecção **sintomática** (presença do sintoma de
  atrito/choque indica a falha), independente de baseline, e contrastar com falhas por desvio.
- **APIs:** Análises (detail: detection_mode=symptom, evidência sem referência) · Dados técnicos
  (baseline, state=learning) · Conhecimento (orientações de lubrificação).
- **Comportamento:** análise `detection_mode=symptom` válida mesmo com baseline em `learning`;
  completo vs. parcial (evidência incompleta).

---

## Executar

### TKT-EXE-12 — Reprocessar análise após intervenção
- **Cliente:** "Troquei o rolamento da bomba. Reprocessa a análise pra ver se melhorou."
- **Contexto:** Cervejaria Aurora · Bomba B-204 · usuário Mecânico (permissão de ação).
- **Pergunta raiz:** executar reprocesso com justificativa válida e validar o resultado.
- **APIs:** Análises (`POST` reprocessar) · Dados técnicos (pós-intervenção).
- **Comportamento:** exige **parâmetros válidos + justificativa**; sucesso sem ciclo de status.

### TKT-EXE-13 — Solicitar análise especializada
- **Cliente:** "Esse compressor tá com comportamento estranho e o insight não convence. Quero que
  um especialista da Tractian veja."
- **Contexto:** Petro Delta · Compressor C-710 · usuário Coordenador.
- **Pergunta raiz:** escalar internamente para análise especializada com contexto adequado.
- **APIs:** Análises (`POST` solicitar análise especializada) · Análises (contexto) · Ativos.
- **Comportamento:** exige justificativa; sucesso representa acionamento.

### TKT-EXE-14 — Atualizar criticidade do ativo
- **Cliente:** "Esse ventilador não é mais crítico pra produção. Muda a criticidade pra média."
- **Contexto:** Papel Sul · Ventilador V-301 · usuário Gerente de Manutenção.
- **Pergunta raiz:** alterar configuração técnica justificadamente.
- **APIs:** Ativos (`PATCH` criticidade/config) · Ativos (detail p/ validar).
- **Comportamento:** ação de impacto; exige justificativa; reflete em priorização.

### TKT-EXE-15 — Solicitar retreinamento do modelo
- **Cliente:** "Esse insight nunca acerta pro spindle de alta rotação. Treina de novo com os dados
  daqui."
- **Contexto:** Acme Auto Peças · Spindle S-420 · usuário Engenheiro de Manutenção.
- **Pergunta raiz:** solicitar retreinamento com justificativa baseada em evidência de erro.
- **APIs:** Modelos (`POST` solicitar retreinamento) · Análises (histórico de erros) · Modelos
  (versão/limitações).
- **Comportamento:** ação de alto impacto; exige justificativa forte.

### TKT-EXE-16 — Escalar para análise humana
- **Cliente:** "Isso aqui ultrapassa o suporte remoto — preciso de campo. Encaminha pra alguém."
- **Contexto:** Mineração Andes · Redutor G-501 · usuário Coordenador.
- **Pergunta raiz:** reconhecer o limite do autônomo e escalar para humano.
- **APIs:** Ações/Escalonamento (`POST` escalar) · Análises/Ativos (contexto do caso).
- **Comportamento:** decisão orientar×agir×escalar; exige justificativa.

---

## Cobertura do catálogo

| Modalidade       | Chamados                       | Comportamentos probabilísticos exercitados                |
| :--------------- | :----------------------------- | :-------------------------------------------------------- |
| Contextualizar   | 01, 02, 03                     | completo, parcial, conflito                               |
| Investigar       | 04, 05, 06, 07, 08, 09, 10, 11, 11b | inconclusivo, indisponível, pendente, conflito, parcial, stale, qualidade baixa, cobertura parcial, sintomático sem baseline |
| Executar         | 12, 13, 14, 15, 16             | ações com justificativa; orientar×agir×escalar            |

Os chamados 04, 05 e 06 são os chamados de referência da modalidade Investigar. Os demais
expandem o espaço do problema cobrindo todas as categorias de API, todas as variações de
comportamento e os dois modos de detecção do modelo: por **desvio de baseline** e **sintomática**
(lubrificação).
