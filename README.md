# Painel Licença Especial · Advocacia Escalável × Berardini

Painel da operação de prospecção por WhatsApp da tese de licença especial da PM e do
Bombeiro Militar de Santa Catarina.

- **Endereço:** https://matheushenriquemendes.github.io/berardini-painel-licenca-especial/
- **Fontes:** Bitrix24 (funil Comercial | Berardini) e Cloud API da Meta.
- **Atualização:** automática, de hora em hora, pelo GitHub Actions.

## Como funciona

`scripts/atualiza.py` lê o funil no Bitrix24 e as métricas de envio na Meta e grava
`dados.json`. O `index.html` lê esse arquivo no navegador e monta os indicadores.
Os textos das análises ficam em `textos.json` e são reescritos sob demanda, não a cada hora.

As credenciais ficam em **Settings → Secrets and variables → Actions**:
`BITRIX_WEBHOOK`, `META_TOKEN` e `WABA_ID`. Nenhuma delas aparece no código.

Para forçar uma atualização fora da hora: aba **Actions** → *Atualiza o painel* → *Run workflow*.

## O que vai para o arquivo público

Apenas números agregados por etapa e por data: nenhum nome, telefone, CPF ou dado
de contato dos leads.
