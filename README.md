# AprovaOS

AprovaOS é um MVP SaaS em FastAPI para organização inteligente de estudos. Ele não é curso, não substitui escola, cursinho ou professores, e não promete aprovação. A proposta é funcionar como uma camada de organização acima da rotina real do estudante: pendências, materiais, simulados, redações, revisões, calendário e plano de recuperação.

## Como Rodar

```bash
pip install -r requirements.txt
python run.py
```

Depois abra:

```text
http://127.0.0.1:8000
```

Opcionalmente, crie um arquivo `.env` a partir de `.env.example` para trocar chave de sessão, banco, pasta de upload e chave de IA.
Para desenvolvimento com recarregamento automático, use `APP_RELOAD=true`.

## Como Rodar o Mobile

```bash
cd aprovaos-mobile
npm install
npx expo start
```

Para emulador Android, use `EXPO_PUBLIC_API_BASE_URL=http://10.0.2.2:8000`. Para celular físico, use o IP do computador na mesma rede Wi-Fi, por exemplo `EXPO_PUBLIC_API_BASE_URL=http://192.168.0.10:8000`.

## Integração de IA

O AprovaOS usa um gateway central em `app/services/ai_gateway.py`. Materiais, Tutor IA, flashcards, planejamento, recuperação e relatórios não chamam OpenAI, Gemini ou DeepSeek diretamente.

As chaves são infraestrutura interna do SaaS. Estudantes não informam chave, o app mobile não recebe chave e a interface web não renderiza segredo.

Configure as chaves somente no backend, preferencialmente em `.env` ou variáveis do ambiente de deploy:

```env
AI_INTERNAL_KEYS_ONLY=true
AI_ENSEMBLE_ENABLED=true
AI_ENSEMBLE_SYNTHESIS_PROVIDER=openai
OPENAI_API_KEY=
GEMINI_API_KEY=
DEEPSEEK_API_KEY=
AI_DEFAULT_PROVIDER=openai
AI_DEFAULT_MODEL=gpt-4.1-mini
AI_BASE_URL=https://api.openai.com/v1
AI_TIMEOUT_SECONDS=30
AI_DATA_TRAINING_ENABLED=false
```

Se quiser configurar por arquivo Python local no backend, copie `app/private_ai_keys.example.py` para `app/private_ai_keys.py` e preencha as chaves. O arquivo real `app/private_ai_keys.py` está no `.gitignore` e não deve ser enviado para repositório.

Com `AI_ENSEMBLE_ENABLED=true`, o gateway tenta consultar OpenAI, Gemini e DeepSeek quando as três chaves existem. Depois, ele sintetiza uma resposta final única antes de devolver ao produto. Se apenas uma ou duas chaves existirem, usa as disponíveis. Se nenhuma existir, os recursos não-IA continuam funcionando e as ações de IA mostram estado seguro de “IA não configurada”.

A página admin `Configurações > Integrações de IA` mostra apenas status, teste de conexão e monitor de uso. Ela não pede nem salva chave no modo interno.

Segurança:

- Nunca commite `.env`.
- Não coloque chaves em HTML, JavaScript, templates ou app mobile.
- A API nunca retorna a chave completa.
- O app mobile mostra apenas status de IA para admin e não edita chaves no MVP.
- Logs de uso guardam metadados técnicos, sem prompts completos nem conteúdo privado.
- Se uma chave for exposta em conversa, histórico ou print, revogue e gere outra antes de usar.

Solução de problemas:

- `ModuleNotFoundError: cryptography`: rode `pip install -r requirements.txt`. O app também trata a ausência da dependência sem quebrar a inicialização.
- Chave inválida: o teste retorna mensagem limpa, sem stack trace e sem expor segredo.
- Nenhum provedor configurado: recursos não-IA continuam funcionando e ações de IA avisam que a configuração ainda falta.

## Estrutura

```text
app/
  main.py              # aplicação FastAPI
  config.py            # variáveis de ambiente
  database.py          # conexão SQLite e sessão SQLAlchemy
  models.py            # modelos de dados
  schemas.py           # validação Pydantic
  routers/             # páginas e APIs por módulo
  services/            # regras de produto, IA e fallbacks locais
  templates/           # HTML Jinja2
  static/css/          # tema, layout, componentes e responsividade
  static/js/           # módulos JS por página
uploads/               # arquivos enviados
aprovaos-mobile/       # app Expo em React Native consumindo a API
run.py                 # servidor local
```

## Recursos do MVP

- Página pública honesta de beta, sem métricas falsas.
- Cadastro, entrada e sessão com senha em hash.
- Configuração inicial com perfil do estudante, gargalo, risco de sobrecarga e plano inicial de 7 dias.
- Onboarding salva blocos reais de rotina no banco.
- Matérias organizam frentes, materiais, flashcards e pendências por assunto.
- Painel Hoje com foco de execução, pendências, revisões, carga planejada vs realizada e ações rápidas.
- Rotina semanal com blocos de escola, cursinho, transporte, trabalho, descanso e estudo.
- Pendências com descrição, categoria, fonte, matéria, subtópico, prioridade e prazo.
- Envio de arquivos ou cadastro de materiais por texto, com resumo, pendências e flashcards por IA quando configurada, com fallback local.
- Flashcards com geração por material, exportação CSV e repetição espaçada simples: Errei, Difícil, Médio e Fácil.
- Simulados com evolução, áreas fortes/fracas e motivos de erro.
- Redação como estimativa, registro de correções e análise de evolução.
- Calendário interno integra rotina, pendências, simulados, redações e revisões; Google Calendar fica como integração opcional configurável.
- Tutor IA com conversas persistentes, modos Organizador, Analista, Tutor com fontes, Criador de flashcards, Recuperação e Priorizador.
- App mobile Expo consome as mesmas APIs do backend.
- Relatório semanal com tarefas, carga, revisões, simulados, redações, sobrecarga e foco recomendado.
- Configurações com linguagem de privacidade, LGPD e segurança para adolescentes.
- Integrações de IA admin com chaves criptografadas, teste de conexão, roteamento por módulo e logs sem conteúdo sensível.

## Observações de Segurança

- Senhas são armazenadas com hash usando `bcrypt`.
- Arquivos enviados são limitados por extensão e tamanho.
- Conteúdo enviado pelo usuário não é renderizado com `innerHTML` no JavaScript.
- O MVP não executa arquivos enviados.
- A tela de Integrações de IA usa guarda admin temporária; em produção, reforce papéis/owner, auditoria e CSRF completo para ações sensíveis.
- Antes de produção, faltam proteção CSRF completa, HTTPS obrigatório, política de retenção, exportação real de dados e exclusão de conta.

## Próximas Funcionalidades

- Melhorias de qualidade para prompts, avaliação de fontes e testes automatizados da camada de IA.
- Exportação de relatórios em PDF.
- Integração opcional com Google Calendar.
- Notificações por e-mail ou aplicativo.
- Painel para escolas e cursinhos acompanharem turmas com consentimento adequado.
- Testes automatizados e migração para banco gerenciado.

## Migração Futura para React ou Next.js

O backend já está separado em APIs e serviços. Uma migração futura pode manter FastAPI como API e substituir os templates Jinja por um frontend React ou Next.js. O caminho recomendado:

1. Manter os modelos, serviços e rotas `/api`.
2. Criar um app frontend separado consumindo as mesmas APIs.
3. Migrar tela por tela, começando por dashboard, pendências e materiais.
4. Adicionar autenticação mais robusta com tokens ou sessão compartilhada.
5. Preservar os serviços de domínio no backend para não duplicar regra de produto no frontend.

## Atualizações MVP (maio/2026)

- Aba Hoje com 3 modos reais: lista, kanban e linha do tempo.
- Reorganização de atrasos com preview e confirmação antes de salvar.
- Aba Rotina com perfil de rotina editável e assistente por regras (sem LLM obrigatória).
- Tabela editável de blocos de rotina com duplicação por dia.
- Aba Pendências com cards-resumo, busca, ordenação e ações completas (concluir, editar, reagendar e excluir).
- Matérias com detalhe expandido: frentes + assuntos, progresso e recomendação dinâmica.
- Flashcards com métricas por baralho, filtros e histórico de revisão no banco.
- Calendário interno com alternância semanal/mensal.
- Tutor IA preparado para fallback rule-based e suporte opcional a Ollama local.

### Seed de desenvolvimento

Para criar dados de exemplo (somente desenvolvimento):

```bash
python -m app.seed
```

Os dados gerados são fictícios e servem apenas para teste local.

### Ollama local (opcional)

Se quiser usar IA local no Tutor sem depender de API externa:

```env
OLLAMA_ENABLED=true
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=llama3
```

Com `OLLAMA_ENABLED=false` (padrão), o sistema usa respostas por regras e dados já salvos no AprovaOS.
