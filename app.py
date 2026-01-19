import streamlit as st
import pandas as pd
import re
import pdfplumber

st.set_page_config(page_title="FipeHunter v0.6 (Matrix)", page_icon="🚜", layout="wide")


def clean_currency(value_str):
    if not value_str:
        return 0.0
    # Limpa string mantendo apenas numeros e separadores
    clean = re.sub(r"[^\d,.]", "", str(value_str))

    # Se estiver vazia
    if not clean:
        return 0.0

    # Lógica de Pontuação (BR vs US)
    if "," in clean:
        clean = clean.replace(".", "").replace(",", ".")
    else:
        # Se só tem ponto, assume milhar se for > 3 digitos ou se tiver 3 digitos e valor alto
        clean = clean.replace(".", "")

    try:
        return float(clean)
    except:
        return 0.0


def extract_model_from_row(row_cells):
    """
    Varre as células da linha procurando o texto mais longo que NÃO seja placa nem dinheiro.
    """
    full_text = " ".join([str(c) for c in row_cells if c])

    # Remove padrões conhecidos
    full_text = re.sub(r"\b[A-Z]{3}[0-9][A-Z0-9][0-9]{2}\b", "", full_text)  # Placa
    full_text = re.sub(r"(?:R\$|RS|R|\$)\s?[\d\.\s,]+", "", full_text)  # Dinheiro

    # Limpa palavras proibidas
    stopwords = [
        "oferta",
        "sp",
        "barueri",
        "sorocaba",
        "campinas",
        "flex",
        "diesel",
        "automatico",
        "manual",
    ]

    words = full_text.split()
    clean_words = [
        w
        for w in words
        if w.lower() not in stopwords and len(w) > 2 and not w.isdigit()
    ]

    return " ".join(clean_words[:6])


def process_pdf_hybrid(file):
    data = []

    with pdfplumber.open(file) as pdf:
        for page in pdf.pages:
            # TENTATIVA 1: Extração de Tabela (Perfeito para R3R e Alphaville)
            tables = page.extract_tables()

            for table in tables:
                for row in table:
                    # Filtra linhas vazias
                    if not row:
                        continue

                    # Converte linha para string para buscar placa
                    row_str = " ".join([str(cell) for cell in row if cell])

                    # Procura Placa na linha (Âncora)
                    plate_match = re.search(
                        r"\b[A-Z]{3}[0-9][A-Z0-9][0-9]{2}\b", row_str
                    )

                    if plate_match:
                        # Achamos um carro! Agora caçamos o dinheiro NAS CÉLULAS
                        money_values = []

                        # Regex para achar dinheiro dentro das células
                        money_pattern = r"(?:R\$|RS|R|\$)\s?[\d\.\s,]+"

                        for cell in row:
                            cell_str = str(cell)
                            # Acha valores formatados (R$ ...)
                            prices = re.findall(money_pattern, cell_str, re.IGNORECASE)
                            for p in prices:
                                val = clean_currency(p)
                                if val > 3000:
                                    money_values.append(val)

                            # Acha valores soltos (ex: 53.602,00) que o regex de R$ pode perder
                            # Se a célula for puramente numérica e alta
                            try:
                                clean_val = clean_currency(cell_str)
                                if clean_val > 3000 and clean_val not in money_values:
                                    money_values.append(clean_val)
                            except:
                                pass

                        # Tenta achar Ano
                        year = "-"
                        year_match = re.search(r"\b(20[1-2][0-9])\b", row_str)
                        if year_match:
                            year = year_match.group(0)

                        # PROCESSA OS VALORES (Lógica do Trator)
                        prices = sorted(list(set(money_values)), reverse=True)

                        if len(prices) >= 2:
                            fipe = prices[0]
                            repasse = prices[1]

                            # Correção para R3R: Se tiver "Ganho IPVA" (lucro), ele será o 3º valor ou menor
                            # A Fipe e o Repasse sempre serão os maiores valores absolutos da linha.

                            # Trava: Repasse não pode ser minúsculo (<30% da Fipe)
                            if repasse < (fipe * 0.3) and len(prices) > 2:
                                repasse = prices[2]

                            lucro_real = fipe - repasse

                            if fipe > 0:
                                margem_pct = (lucro_real / fipe) * 100

                                if 2 < margem_pct < 70:
                                    data.append(
                                        {
                                            "Placa": plate_match.group(),
                                            "Modelo": extract_model_from_row(row),
                                            "Ano": year,
                                            "Fipe": fipe,
                                            "Repasse": repasse,
                                            "Lucro_Real": lucro_real,
                                            "Margem_%": round(margem_pct, 1),
                                        }
                                    )

    return pd.DataFrame(data)


# --- FRONTEND ---
st.title("🚜 FipeHunter v0.6 (Matrix)")
st.caption("Modo Híbrido: Extração de Tabelas Estruturadas (R3R/Alphaville)")

uploaded_file = st.file_uploader("Solte seu PDF", type="pdf")

if uploaded_file:
    with st.spinner("Decodificando a Matrix do PDF..."):
        try:
            df = process_pdf_hybrid(uploaded_file)

            if not df.empty:
                df = df.sort_values(by="Lucro_Real", ascending=False)

                st.divider()
                st.subheader("🔥 Top Oportunidades")
                cols = st.columns(3)
                for i in range(min(3, len(df))):
                    row = df.iloc[i]
                    cols[i].metric(
                        f"{row['Modelo'][:20]}..",
                        f"R$ {row['Lucro_Real']:,.0f}",
                        f"{row['Margem_%']}%",
                    )
                    cols[i].caption(f"{row['Placa']} | Fipe: {row['Fipe']:,.0f}")

                st.divider()
                st.dataframe(
                    df[
                        [
                            "Modelo",
                            "Ano",
                            "Placa",
                            "Fipe",
                            "Repasse",
                            "Lucro_Real",
                            "Margem_%",
                        ]
                    ],
                    use_container_width=True,
                    hide_index=True,
                )
            else:
                st.error(
                    "Não consegui extrair tabela. O PDF pode ser uma imagem (scan) ou não ter linhas de grade."
                )

        except Exception as e:
            st.error(f"Erro Crítico: {e}")
