#!/usr/bin/env python3
"""Baixa do Gmail os XLSX enviados pelo ERP e guarda em dados/xlsx (historico).

Variaveis de ambiente:
  GMAIL_USER, GMAIL_APP_PASSWORD  -> conta e senha de app do Gmail (obrigatorias)
  FILTRO_REMETENTE                -> so aceita e-mails deste remetente (recomendado)
  FILTRO_ASSUNTO                  -> trecho que o assunto deve conter (opcional)
  FILTRO_ANEXO                    -> trecho do nome do anexo (padrao: SEPARACAO)
  DIAS_BUSCA                      -> quantos dias para tras procurar (padrao: 10)

Cada e-mail e importado uma unica vez (controle em dados/processados.json).
Nenhum arquivo e sobrescrito: conteudo diferente para o mesmo dia ganha sufixo _2, _3...

Uso manual, sem Gmail:  python scripts/buscar_email.py --eml mensagem.eml
"""
import datetime as dt
import email
import email.policy
import email.utils
import hashlib
import imaplib
import json
import os
import pathlib
import re
import sys
import tempfile
import unicodedata

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from gerar_dados import DIR_XLSX, RAIZ, ler_xlsx  # noqa: E402

PROCESSADOS = RAIZ / "dados" / "processados.json"


def _normalizar(texto):
    sem_acento = unicodedata.normalize("NFKD", texto or "").encode("ascii", "ignore").decode()
    return sem_acento.upper()


def _hash(conteudo):
    return hashlib.sha256(conteudo).hexdigest()


def anexos_xlsx(msg, filtro_anexo):
    """Devolve [(nome, bytes)] dos anexos .xlsx cujo nome contem o filtro."""
    achados = []
    for parte in msg.walk():
        nome = parte.get_filename()
        if not nome or not nome.lower().endswith(".xlsx"):
            continue
        if filtro_anexo and _normalizar(filtro_anexo) not in _normalizar(nome):
            continue
        conteudo = parte.get_payload(decode=True)
        if conteudo:
            achados.append((nome, conteudo))
    return achados


def data_do_arquivo(conteudo, data_email):
    """Dia a que os dados se referem; se a planilha vier vazia, usa a vespera do e-mail."""
    with tempfile.NamedTemporaryFile(suffix=".xlsx") as tmp:
        tmp.write(conteudo)
        tmp.flush()
        itens = ler_xlsx(tmp.name)  # levanta excecao se nao for um XLSX valido
    if itens:
        return min(i["data"] for i in itens), len(itens)
    return (data_email - dt.timedelta(days=1)).isoformat(), 0


def salvar(conteudo, dia):
    """Grava sem sobrescrever. Devolve o nome do arquivo ou None se ja existia identico."""
    DIR_XLSX.mkdir(parents=True, exist_ok=True)
    existentes = sorted(DIR_XLSX.glob(f"{dia}_SEPARACAO*.xlsx"))
    if any(_hash(a.read_bytes()) == _hash(conteudo) for a in existentes):
        return None
    nome = f"{dia}_SEPARACAO.xlsx" if not existentes else f"{dia}_SEPARACAO_{len(existentes) + 1}.xlsx"
    (DIR_XLSX / nome).write_bytes(conteudo)
    return nome


def processar(msg, registro, filtro_anexo, filtro_assunto=""):
    """Importa os anexos de uma mensagem. Devolve a quantidade de arquivos novos."""
    ident = (msg.get("Message-ID") or "").strip() or _hash(msg.as_bytes())
    if ident in registro:
        return 0
    if filtro_assunto and _normalizar(filtro_assunto) not in _normalizar(str(msg.get("Subject", ""))):
        return 0
    try:
        data_email = email.utils.parsedate_to_datetime(msg.get("Date")).date()
    except (TypeError, ValueError):
        data_email = dt.date.today()
    novos, arquivos = 0, []
    for nome, conteudo in anexos_xlsx(msg, filtro_anexo):
        try:
            dia, qtd = data_do_arquivo(conteudo, data_email)
        except Exception as erro:
            print(f"AVISO: anexo '{nome}' ignorado (nao e um XLSX valido): {erro}", file=sys.stderr)
            continue
        gravado = salvar(conteudo, dia)
        if gravado:
            novos += 1
            arquivos.append(gravado)
            print(f"Novo arquivo: {gravado} ({qtd} itens)")
    if arquivos or anexos_xlsx(msg, filtro_anexo):
        registro[ident] = {"email_de": data_email.isoformat(), "arquivos": arquivos}
    return novos


def caixa_todos_os_emails(imap):
    """No Gmail o nome da pasta 'Todos os e-mails' muda com o idioma; localiza pela marca \\All."""
    _, pastas = imap.list()
    for linha in pastas or []:
        texto = linha.decode("utf-8", "replace")
        if "\\All" in texto:
            achou = re.search(r'"([^"]+)"\s*$', texto)
            if achou:
                return f'"{achou.group(1)}"'
    return "INBOX"


def main():
    registro = json.loads(PROCESSADOS.read_text(encoding="utf-8")) if PROCESSADOS.exists() else {}
    filtro_anexo = os.environ.get("FILTRO_ANEXO") or "SEPARACAO"
    filtro_assunto = os.environ.get("FILTRO_ASSUNTO") or ""
    novos = 0

    if len(sys.argv) == 3 and sys.argv[1] == "--eml":
        msg = email.message_from_bytes(pathlib.Path(sys.argv[2]).read_bytes(), policy=email.policy.default)
        novos = processar(msg, registro, filtro_anexo, filtro_assunto)
    else:
        usuario, senha = os.environ.get("GMAIL_USER"), os.environ.get("GMAIL_APP_PASSWORD")
        if not usuario or not senha:
            print("GMAIL_USER / GMAIL_APP_PASSWORD nao configurados: busca de e-mail ignorada.")
            return
        dias = int(os.environ.get("DIAS_BUSCA") or 10)
        consulta = f"has:attachment filename:xlsx newer_than:{dias}d"
        remetente = (os.environ.get("FILTRO_REMETENTE") or "").strip()
        if remetente:
            if not re.fullmatch(r"[\w.+\-@]+", remetente):
                sys.exit("FILTRO_REMETENTE invalido: informe apenas o endereco de e-mail.")
            consulta += f" from:{remetente}"
        else:
            print("AVISO: FILTRO_REMETENTE vazio - qualquer remetente pode alimentar o painel.", file=sys.stderr)

        imap = imaplib.IMAP4_SSL("imap.gmail.com", 993)
        imap.login(usuario, senha.replace(" ", ""))
        imap.select(caixa_todos_os_emails(imap), readonly=True)  # readonly: nao marca como lido
        _, resposta = imap.uid("SEARCH", "X-GM-RAW", f'"{consulta}"')
        uids = resposta[0].split() if resposta and resposta[0] else []
        print(f"{len(uids)} e-mail(s) com XLSX nos ultimos {dias} dias.")
        for uid in uids:
            _, dados = imap.uid("FETCH", uid, "(BODY.PEEK[])")
            bruto = next((p[1] for p in dados if isinstance(p, tuple)), None)
            if bruto:
                msg = email.message_from_bytes(bruto, policy=email.policy.default)
                novos += processar(msg, registro, filtro_anexo, filtro_assunto)
        imap.logout()

    PROCESSADOS.write_text(json.dumps(registro, ensure_ascii=False, indent=1, sort_keys=True), encoding="utf-8")
    print(f"{novos} arquivo(s) novo(s) importado(s).")


if __name__ == "__main__":
    main()
