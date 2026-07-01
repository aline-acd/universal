# Portal Universal Royalty

App Streamlit para extrair resumo de relatórios PDF da Universal.

## Colunas extraídas

- Arquivo
- Cliente
- Período
- Obra
- Recebimentos
- Valor_Devido
- Páginas

## Rodar localmente

```bash
pip install -r requirements.txt
streamlit run app.py
```

## Render

Build command:

```bash
pip install -r requirements.txt
```

Start command:

```bash
streamlit run app.py --server.port $PORT --server.address 0.0.0.0
```
