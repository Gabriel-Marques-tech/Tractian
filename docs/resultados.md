## Comparação entre braços

| Métrica | Braço A | Braço B |
| --- | --- | --- |
| Execuções | 85 | 85 |
| Trajetória | 0.09 ± 0.13 | 0.07 ± 0.12 |
| Recall de ferramentas | 0.10 ± 0.15 | 0.08 ± 0.15 |
| Precisão de ferramentas | 0.34 ± 0.47 | 0.24 ± 0.43 |
| Respondeu | 85/85 | 85/85 |
| Instabilidade média | 0.004 | 0.018 |
| Chamadas ao modelo por execução | 1.9 | 5.8 |
| Segundos por execução | 33 | 59 |
| Ações exigidas não executadas | 35 | 30 |
| Ações executadas sem o caso pedir | 0 | 4 |
| Alterações de config indevidas | 0 | 3 |
| Ações sem justificativa | 0 | 0 |
| Recusas do gate | 0 | 7 |
| Chamadas resgatadas de texto | 0% | 31% |
| Ancoragem (objeto 4) | 3.29 ± 2.26 (n=66) | 3.38 ± 2.28 (n=40) |
| Respostas que citam dado | 66/85 | 40/85 |
| Qualidade da resposta (objeto 5) | 2.38 ± 1.21 | 2.42 ± 1.25 |
| — reconhece a degradação | 4.12 ± 1.92 | 4.24 ± 1.81 |
| — cobre a pergunta raiz | 0.94 ± 1.17 | 0.80 ± 0.88 |
| Valores citados | 216 | 62 |
| Alucinação por valor citado | 22% | 26% |

## Por categoria de caso

As três categorias exigem comportamentos diferentes, então a média
global pode esconder que um braço só é melhor numa delas.

| Categoria | Braço A | Braço B |
| --- | --- | --- |
| contextualizar | 0.14 ± 0.11 (n=15) | 0.08 ± 0.12 (n=15) |
| executar | 0.07 ± 0.14 (n=25) | 0.08 ± 0.14 (n=25) |
| investigar | 0.09 ± 0.13 (n=45) | 0.06 ± 0.12 (n=45) |

## Degradação enfrentada

Sob a mesma seed os braços deveriam ver distribuição parecida. Uma
diferença grande indica que trajetórias diferentes tocaram recursos
diferentes, não que a API tratou os braços de forma distinta.

| `mode` da API | Braço A | Braço B |
| --- | --- | --- |
| `complete` | 36 | 30 |
| `conflict` | 29 | 10 |
| `partial` | 5 | 10 |

## Estabilidade entre repetições

**Braço A** — instabilidade média 0.004

- `TKT-CTX-01`: desvio 0.062

**Braço B** — instabilidade média 0.018

- `TKT-INV-05`: desvio 0.112
- `TKT-EXE-15`: desvio 0.112
- `TKT-INV-04`: desvio 0.089

