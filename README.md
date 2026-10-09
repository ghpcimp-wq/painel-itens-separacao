# Painel de Separação

Painel em HTML (GitHub Pages) alimentado pelo XLSX diário que o ERP envia por e-mail.

## Como funciona

1. O ERP envia o `SEPARACAO_DIA_ANTERIOR.xlsx` para a conta Gmail.
2. O fluxo **Atualizar painel** (GitHub Actions) roda 3 vezes ao dia (07:17, 10:17 e 18:17, horário de Brasília), lê o Gmail e grava cada anexo novo em `dados/xlsx/` com a data dos dados no nome (`2026-10-08_SEPARACAO.xlsx`). Nada é sobrescrito nem apagado: esse é o histórico.
3. O mesmo fluxo converte todo o histórico em JSON (`dados/json/` e `dados/resumo.json`) e publica o painel.

## Configuração (uma única vez)

1. **Repositório:** crie o repositório e envie todo o conteúdo desta pasta para a branch `main` (incluindo a pasta oculta `.github`).
2. **Gmail:** ative a verificação em duas etapas na conta e gere uma *senha de app* (Conta Google → Segurança → Senhas de app).
3. **Segredos** (Settings → Secrets and variables → Actions → *Secrets*):
   - `GMAIL_USER`: endereço da conta Gmail.
   - `GMAIL_APP_PASSWORD`: a senha de app de 16 caracteres.
4. **Variáveis** (mesma tela, aba *Variables*):
   - `FILTRO_REMETENTE`: e-mail usado pelo ERP no envio. **Recomendado**: sem ele, qualquer pessoa que mande um XLSX para a conta alimenta o painel.
   - `FILTRO_ASSUNTO` (opcional): trecho do assunto.
   - `FILTRO_ANEXO` (opcional, padrão `SEPARACAO`): trecho do nome do anexo.
   - `DIAS_BUSCA` (opcional, padrão `10`): janela de busca em dias. Aumente uma vez para importar e-mails antigos.
5. **Pages:** Settings → Pages → *Source*: **GitHub Actions**.
6. **Primeira execução:** aba Actions → *Atualizar painel* → *Run workflow*.

## Uso do dia a dia

- **Carga manual:** envie um XLSX para `dados/xlsx/` com o nome `AAAA-MM-DD_SEPARACAO.xlsx`; o painel é atualizado sozinho.
- **Abrir um dia específico:** `.../index.html?dia=2026-10-08`.
- **Falhas:** se o Gmail recusar o acesso, o fluxo falha e o GitHub avisa por e-mail. O painel também mostra um alerta quando o último arquivo tem 4 dias ou mais.

## Atenção: privacidade

Um site do GitHub Pages é acessível por qualquer pessoa que tenha o endereço, mesmo com repositório privado (restrição de acesso ao site só existe no plano Enterprise Cloud). Em repositório público, os XLSX do histórico também ficam visíveis. Confirme as regras do plano de vocês antes de publicar dados comerciais.

## Estrutura

    index.html                      painel
    dados/xlsx/                     histórico de arquivos recebidos
    dados/json/, dados/resumo.json  dados gerados para o painel
    dados/processados.json          e-mails já importados
    scripts/buscar_email.py         Gmail -> dados/xlsx
    scripts/gerar_dados.py          dados/xlsx -> JSON
    .github/workflows/atualizar.yml agendamento e publicação
