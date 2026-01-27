import streamlit as st
import pandas as pd
import re
import pdfplumber
from io import BytesIO

# --- CONFIGURAÇÃO ---
st.set_page_config(page_title="R3R Enterprise", layout="wide", page_icon="🏢")
st.markdown(
    """
    <style>
        #MainMenu {visibility: hidden;} footer {visibility: hidden;} header {visibility: hidden;}
        div[data-testid="stMetric"] { background-color: #1E1E1E; border: 1px solid #333; padding: 15px; border-radius: 10px; color: white; }
        div.stDownloadButton > button { width: 100%; background-color: #00C853; color: white; font-weight: bold; padding: 15px; border-radius: 8px; }
    </style>
""",
    unsafe_allow_html=True,
)

# --- INTELLIGENT PARSER V2.0 (ROW EXPLODER) ---


def parse_money(value_str):
    if not value_str:
        return None
    clean = re.sub(r"[^\d,]", "", str(value_str))
    if not clean:
        return None
    try:
        val = (
            float(clean.replace(".", "").replace(",", "."))
            if "," in clean
            else float(clean.replace(".", ""))
        )
        return val if val > 2000 else None  # Filtra valores de margem pequenos
    except:
        return None


def clean_model(text):
    text = str(text).upper().replace("\n", " ")
    remove = [
        "VCPBR",
        "VCPER",
        "OFERTA",
        "DISPONIVEL",
        "FLEX",
        "GASOLINA",
        "ALCOOL",
        "AUTOMATICO",
        "MANUAL",
        "C/AR",
        "4P",
        "2P",
    ]
    clean = re.sub(r"R\$\s?[\d\.,]+", "", text)  # Tira preço
    words = clean.split()
    # Pega as primeiras 5 palavras que não sejam proibidas
    final = [w for w in words if w not in remove and len(w) > 2 and not w.isdigit()]
    return " ".join(final[:6])


def extract_cars_from_row(row):
    """
    Função Mágica: Recebe uma linha crua da tabela (que pode ter 3 carros grudados)
    e devolve uma lista de dicionários separados.
    """
    extracted = []

    # 1. Identificar Placas (Âncora) - Coluna 0
    raw_placas = str(row[0])
    placas = re.findall(r"[A-Z]{3}[0-9][A-Z0-9][0-9]{2}", raw_placas)

    if not placas:
        return []

    # 2. Preparar outras colunas para divisão
    # Se temos 2 placas, esperamos que as outras colunas tenham dados para 2 carros
    # Dividimos por quebra de linha '\n' que é o padrão do PDFplumber para células mescladas

    models = str(row[1]).split("\n") if len(row) > 1 else []
    anos_fab = str(row[2]).split("\n") if len(row) > 2 else []
    anos_mod = str(row[3]).split("\n") if len(row) > 3 else []
    kms = str(row[4]).split("\n") if len(row) > 4 else []

    # Coluna 5 (Preços/Cores) é a mais bagunçada.
    # Tática: Dividir pelo número de placas.
    raw_prices = str(row[5])
    # Tenta dividir por duplo enter (padrão visual) ou apenas enter
    price_chunks = re.split(r"\n+", raw_prices)
    # Remove chunks vazios ou que só tem "RS"
    price_chunks = [p for p in price_chunks if len(p.strip()) > 2]

    # Sincronização
    num_cars = len(placas)

    for i in range(num_cars):
        car = {}
        car["Placa"] = placas[i]

        # Tenta pegar o Modelo correspondente (ou repete o último)
        try:
            raw_model = models[i] if i < len(models) else models[-1]
        except:
            raw_model = "Modelo Desconhecido"
        car["Modelo"] = clean_model(raw_model)

        # Tenta pegar Ano
        try:
            fab = anos_fab[i] if i < len(anos_fab) else ""
        except:
            fab = ""
        try:
            mod = anos_mod[i] if i < len(anos_mod) else ""
        except:
            mod = ""
        car["Ano"] = f"{fab}/{mod}"

        # Tenta pegar KM
        try:
            k_txt = kms[i] if i < len(kms) else "0"
            car["KM"] = int(re.sub(r"[^\d]", "", k_txt))
        except:
            car["KM"] = 0

        # Tenta pegar Preços no Chunk correspondente
        # Se temos 2 carros e 4 chunks de preço, assumimos 2 chunks por carro?
        # Simplificação: Pega todo o texto da coluna 5 e busca preços.
        # SEPARAMOS o texto da coluna 5 em N partes iguais para tentar isolar o preço de cada carro

        full_price_text = raw_prices.replace("\n", " ")
        # Busca TODOS os preços da célula
        all_money = re.findall(r"R\$\s?[\d\.,]+", full_price_text)
        all_vals = sorted(
            [parse_money(m) for m in all_money if parse_money(m)], reverse=True
        )

        # Lógica de Distribuição:
        # Se tem 2 carros, os 2 maiores valores são Fipes? Ou Fipe1, Repasse1, Fipe2, Repasse2?
        # A planilha mistura tudo.
        # Melhor estratégia: Tentar isolar o texto do chunk.

        current_chunk = ""
        if i < len(price_chunks):
            current_chunk = price_chunks[i]
        else:
            current_chunk = raw_prices  # Fallback

        # Extrai cor do chunk
        car["Cor"] = "OUTROS"
        for c in ["BRANCO", "PRETO", "PRATA", "CINZA", "VERMELHO"]:
            if c in current_chunk.upper():
                car["Cor"] = c
                break

        # Extrai valores DO CHUNK ESPECÍFICO (Mais seguro)
        chunk_vals = sorted(
            [
                parse_money(m)
                for m in re.findall(r"R\$\s?[\d\.,]+", current_chunk)
                if parse_money(m)
            ],
            reverse=True,
        )

        if len(chunk_vals) >= 2:
            car["Fipe"] = chunk_vals[0]
            car["Custo_Original"] = chunk_vals[
                1
            ]  # Segundo maior valor do bloco é o custo
        elif len(all_vals) >= 2 * num_cars:
            # Fallback: Se não achou no chunk, tenta pegar da lista global de preços da célula
            # Ex: Carro 0 pega indices 0 e 1. Carro 1 pega indices 2 e 3.
            idx_start = i * 2
            if idx_start + 1 < len(all_vals):
                car["Fipe"] = all_vals[idx_start]
                car["Custo_Original"] = all_vals[idx_start + 1]
            else:
                continue  # Pula se não tiver preço
        else:
            continue  # Sem preço, sem carro

        if car.get("Custo_Original", 0) > 5000:
            extracted.append(car)

    return extracted


def process_pdf(file):
    final_data = []
    with pdfplumber.open(file) as pdf:
        for page in pdf.pages:
            # Extrai tabela (ajuda a separar as linhas visuais)
            tables = page.extract_tables()
            for table in tables:
                for row in table:
                    # Pula cabeçalho ou linha vazia
                    if not row or not row[0] or "LOJA" in str(row[0]):
                        continue

                    # Processa a linha (pode gerar 1 ou + carros)
                    cars = extract_cars_from_row(row)
                    final_data.extend(cars)
    return final_data


# --- APP ---
with st.sidebar:
    st.title("🏢 R3R Admin")
    margem = st.number_input("Margem Fixa (R$):", value=2000.0, step=100.0)

st.title("Importador Alphaville Oficial 🚀")
st.caption("Leitura de Células Mescladas Ativada")

up = st.file_uploader("PDF Alphaville (Novo)", type="pdf")

if up:
    with st.spinner("Processando..."):
        data = process_pdf(up)
        df = pd.DataFrame(data)

        if not df.empty:
            df["Venda"] = df["Custo_Original"] + margem
            df["Lucro"] = df["Venda"] - df["Custo_Original"]

            c1, c2 = st.columns(2)
            c1.metric("Veículos", len(df))
            c2.metric("Lucro Total", f"R$ {df['Lucro'].sum():,.0f}")

            st.dataframe(df, use_container_width=True)

            output = BytesIO()
            with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
                df.to_excel(writer, index=False)
            st.download_button("Baixar Excel", output.getvalue(), "Lista.xlsx")
        else:
            st.error(
                "Nenhum carro identificado. O PDF pode estar como imagem ou layout muito diferente."
            )
