#!/usr/bin/env python3
"""Gera o dados.json do painel da operacao Berardini.

Le o funil 0 do Bitrix24 e as metricas da Cloud API da Meta e grava um
arquivo compacto na raiz do repositorio. Roda de hora em hora pelo
GitHub Actions; as credenciais vem de secrets do repositorio.
"""
import collections
import datetime
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

BX = os.environ["BITRIX_WEBHOOK"].rstrip("/") + "/"
META_TOKEN = os.environ["META_TOKEN"]
WABA = os.environ["WABA_ID"]
GRAPH = "https://graph.facebook.com/v23.0"
CATEGORIA = 0
TZ = datetime.timezone(datetime.timedelta(hours=-3))

CAMPO_MOTIVO = "UF_CRM_1792372814774"
CAMPO_ULTIMO = "UF_CRM_ULTIMO_DISPARO_WA"
CAMPO_FOLLOW = "UF_CRM_1792501470154"
ETAPA_FILA = "UC_29GPC9"  # Importacao base / Distribuicao

MOTIVOS = {
    "150": "Parou de responder", "152": "Nunca respondeu",
    "154": "Nao ve valor no servico", "156": "Nao entrega documentacao",
    "158": "Ja tem advogado", "160": "Impossibilidade de acao",
    "162": "Nao temos interesse", "164": "Nao tem direito",
    "166": "Sem interesse", "168": "Outros", "170": "Ja tem processo",
}


def chamar(metodo, params, tentativas=4):
    dados = json.dumps(params).encode()
    for n in range(tentativas):
        try:
            req = urllib.request.Request(
                BX + metodo + ".json", dados,
                {"Content-Type": "application/json", "User-Agent": "painel-berardini"})
            with urllib.request.urlopen(req, timeout=90) as r:
                return json.load(r)
        except Exception as e:  # rede instavel ou limite do Bitrix
            if n == tentativas - 1:
                raise
            print("retry %s: %s" % (metodo, e), file=sys.stderr)
            time.sleep(3 * (n + 1))


def qs(obj, prefixo=""):
    partes = []
    for k, v in obj.items():
        chave = "%s[%s]" % (prefixo, k) if prefixo else str(k)
        if isinstance(v, dict):
            partes.append(qs(v, chave))
        elif isinstance(v, list):
            partes.append(qs({str(i): x for i, x in enumerate(v)}, chave))
        else:
            partes.append(urllib.parse.quote(chave) + "=" + urllib.parse.quote(str(v)))
    return "&".join(p for p in partes if p)


def negocios():
    """Le todos os negocios do funil, 2.500 por chamada (batch de 50)."""
    sel = ["ID", "STAGE_ID", "DATE_CREATE", "DATE_MODIFY", "CLOSEDATE", "CLOSED",
           CAMPO_MOTIVO, CAMPO_ULTIMO, CAMPO_FOLLOW]
    fora, start, vistos = [], 0, set()
    while True:
        cmd = {}
        for i in range(50):
            cmd["c%d" % i] = "crm.deal.list?" + qs({
                "filter": {"CATEGORY_ID": CATEGORIA}, "select": sel,
                "order": {"ID": "ASC"}, "start": start + i * 50})
        r = chamar("batch", {"halt": 0, "cmd": cmd})["result"]["result"]
        lidos = 0
        for i in range(50):
            for d in (r.get("c%d" % i) or []):
                lidos += 1
                if d["ID"] in vistos:
                    continue
                vistos.add(d["ID"])
                fora.append(d)
        if lidos < 2500:
            break
        start += 2500
    return fora


def etapas():
    r = chamar("crm.status.list", {"filter": {"ENTITY_ID": "DEAL_STAGE"},
                                   "order": {"SORT": "ASC"}})
    return {s["STATUS_ID"]: s["NAME"] for s in r["result"]}


def graph(caminho, params):
    url = GRAPH + "/" + caminho + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"Authorization": "Bearer " + META_TOKEN})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.load(r)


def meta():
    fim = int(time.time()) + 86400
    ini = fim - 45 * 86400
    campos = ("analytics.start(%d).end(%d).granularity(DAY),"
              "phone_numbers{display_phone_number,quality_rating,"
              "whatsapp_business_manager_messaging_limit,status}") % (ini, fim)
    try:
        d = graph(WABA, {"fields": campos})
    except urllib.error.HTTPError as e:
        print("Meta indisponivel: %s" % e.read().decode()[:200], file=sys.stderr)
        return None
    dias = [{"d": datetime.datetime.fromtimestamp(p["start"], TZ).strftime("%Y-%m-%d"),
             "sent": p.get("sent", 0), "delivered": p.get("delivered", 0)}
            for p in d.get("analytics", {}).get("data_points", [])]
    n = (d.get("phone_numbers", {}).get("data") or [{}])[0]
    return {"dias": dias, "numero": n.get("display_phone_number", ""),
            "qualidade": n.get("quality_rating", ""),
            "tier": n.get("whatsapp_business_manager_messaging_limit", ""),
            "status": n.get("status", "")}


def main():
    deals = negocios()
    st = etapas()
    linhas, base = [], 0
    for d in deals:
        if d["STAGE_ID"] == ETAPA_FILA:
            base += 1
            continue
        linhas.append({
            "s": d["STAGE_ID"],
            "c": d["DATE_CREATE"][:10],
            "m": d["DATE_MODIFY"][:10],
            "f": (d.get("CLOSEDATE") or "")[:10] if d.get("CLOSED") == "Y" else "",
            "mo": MOTIVOS.get(str(d.get(CAMPO_MOTIVO) or ""), ""),
            "d": (d.get(CAMPO_ULTIMO) or "")[:10],
            "fu": int(float(d.get(CAMPO_FOLLOW) or 0)),
        })
    agora = datetime.datetime.now(TZ)
    anterior = {}
    if os.path.exists("dados.json"):
        try:
            anterior = json.load(open("dados.json"))
        except Exception:
            anterior = {}
    saida = {
        "gerado": agora.strftime("%Y-%m-%d"),
        "geradoEm": agora.strftime("%d/%m/%Y, %Hh%M"),
        "stages": st,
        "base": base,
        "total": len(deals),
        "rows": linhas,
        "meta": meta() or anterior.get("meta") or {"dias": []},
    }
    with open("dados.json", "w", encoding="utf-8") as f:
        json.dump(saida, f, ensure_ascii=False, separators=(",", ":"))
    print("negocios %d | fila %d | ativos %d | dias meta %d"
          % (len(deals), base, len(linhas), len(saida["meta"].get("dias", []))))
    print(collections.Counter(l["s"] for l in linhas))


if __name__ == "__main__":
    main()
