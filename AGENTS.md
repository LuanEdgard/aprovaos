# AGENTS.md — AprovaOS

## Produto

AprovaOS é um SaaS educacional de organização, automação e acompanhamento da rotina de estudos para vestibulandos brasileiros.

AprovaOS NÃO é cursinho.
AprovaOS NÃO vende aulas como produto principal.
AprovaOS NÃO promete aprovação.
AprovaOS NÃO substitui escola, professor ou cursinho.

A pergunta central do produto é:
"Com tudo que eu tenho para fazer, o que eu estudo hoje, por quê e como recupero se atrasar?"

## Stack atual

Backend:
- Python
- FastAPI
- SQLAlchemy
- Pydantic
- SQLite no MVP

Frontend:
- Jinja2 templates
- HTML separado
- CSS separado
- JavaScript separado

Estrutura esperada:
- app/templates/
- app/static/css/
- app/static/js/
- app/routers/
- app/services/
- app/models.py
- app/schemas.py
- app/database.py

## Regra principal

Preservar funcionamento antes de melhorar estética.

## Proibido

- Não alterar rotas sem autorização.
- Não alterar endpoints sem autorização.
- Não alterar models, schemas ou banco durante redesign visual.
- Não renomear ids usados por JS.
- Não renomear name de inputs.
- Não remover data attributes.
- Não trocar actions de forms.
- Não mover lógica de negócio para templates.
- Não colocar CSS inline dentro do HTML.
- Não colocar JS gigante dentro do HTML.
- Não usar innerHTML com conteúdo do usuário.
- Não criar dados falsos como se fossem reais.
- Não substituir o projeto por React/Next sem autorização explícita.

## Permitido

- Melhorar CSS.
- Criar design tokens.
- Melhorar layout dos templates.
- Reorganizar hierarquia visual.
- Melhorar responsividade.
- Melhorar acessibilidade.
- Criar componentes CSS reutilizáveis.
- Criar pequenos JS auxiliares se não quebrarem a lógica existente.
- Criar testes Playwright.
- Criar documentação de UX.

## Telas prioritárias do MVP

1. Login/cadastro
2. Onboarding
3. Hoje
4. Rotina
5. Pendências
6. Materiais
7. Flashcards
8. Simulados
9. Redação
10. Tutor IA simples
11. Relatório simples

## UX desejada

A interface deve parecer um sistema operacional de estudos:
- clara
- organizada
- rápida
- confiável
- jovem sem ser infantil
- educacional sem parecer cursinho
- moderna sem parecer dashboard genérico de IA

Evitar:
- excesso de glassmorphism
- gradientes aleatórios
- cards cinza genéricos
- visual de template shadcn sem personalidade
- ícones em excesso
- animações desnecessárias
- dashboards poluídos

## Estados visuais obrigatórios

Criar padrões para:
- tarefa pendente
- tarefa concluída
- tarefa atrasada
- tarefa reagendada
- revisão
- simulado
- redação
- prova
- prioridade alta
- sobrecarga
- recuperação de atraso

## Como trabalhar

Sempre:
1. Ler arquivos relevantes antes de alterar.
2. Explicar plano.
3. Alterar em pequenos passos.
4. Listar arquivos modificados.
5. Rodar testes quando possível.
6. Preservar funcionamento.