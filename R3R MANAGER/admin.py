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
        .top-card { background: linear-gradient(135deg, #1a5f2a 0%, #0d3018 100%); border: 2px solid #2ecc71; border-radius: 12px; padding: 20px; margin: 10px 0; }
        .top-card h3 { color: #2ecc71; margin: 0 0 10px 0; }
        .top-card p { color: white; margin: 5px 0; font-size: 14px; }
        .lucro-destaque { color: #2ecc71; font-size: 24px; font-weight: bold; }
    </style>
""",
    unsafe_allow_html=True,
)

# --- INTELLIGENT PARSER V2.0 ---


def parse_money(value_str):
    """Converte valores monetários para float"""
    if not value_str:
        return None
    clean = re.sub(r"[^\d,]", "", str(value_str).replace(" ", ""))
    if not clean:
        return None
    try:
        val = (
            float(clean.replace(".", "").replace(",", "."))
            if "," in clean
            else float(clean.replace(".", ""))
        )
        return val if val > 2000 else None
    except Exception:
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
    clean = re.sub(r"R\$\s?[\d\.,]+", "", text)
    words = clean.split()
    final = [w for w in words if w not in remove and len(w) > 2 and not w.isdigit()]
    return " ".join(final[:6])


def extract_cars_from_row(row):
    """
    Extrai carros da linha usando layout de 16 colunas ALPHAVILLE:
    0: PLACA, 1: LOJA, 2: MODELO, 3: ANO FAB, 4: ANO MOD, 5: KM, 6: COR,
    7: FIPE, 8: MARGEM (R$), 9: PREÇO CLIENTE (=Custo), 10: ORÇAMENTO,
    11: ENDEREÇO, 12: BAIRRO, 13: CIDADE, 14: ESTADO, 15: LAUDO
    """
    extracted = []

    if len(row) < 10:
        return []

    if not row[2] or "MODELO" in str(row[2]).upper():
        return []

    # Dados da linha
    modelos = str(row[2]).split("\n") if row[2] else []
    anos_fab = str(row[3]).split("\n") if row[3] else []
    anos_mod = str(row[4]).split("\n") if row[4] else []
    kms = str(row[5]).split("\n") if row[5] else []
    cores = str(row[6]).split("\n") if row[6] else []
    fipes_txt = str(row[7]).split("\n") if len(row) > 7 and row[7] else []
    precos_txt = str(row[9]).split("\n") if len(row) > 9 and row[9] else []
    laudo_txt = str(row[15]).strip().upper() if len(row) > 15 and row[15] else ""

    placas = re.findall(r"[A-Z]{3}[0-9][A-Z0-9][0-9]{2}", str(row[0])) if row[0] else []
    num_cars = max(len(modelos), 1)

    for i in range(num_cars):
        car = {}

        # Placa
        car["Placa"] = placas[i] if i < len(placas) else f"SEM-{i + 1}"

        # Modelo
        raw_model = modelos[i] if i < len(modelos) else (modelos[-1] if modelos else "")
        car["Modelo"] = clean_model(raw_model)

        # Ano
        fab = anos_fab[i] if i < len(anos_fab) else (anos_fab[-1] if anos_fab else "")
        mod = anos_mod[i] if i < len(anos_mod) else (anos_mod[-1] if anos_mod else "")
        car["Ano"] = f"{fab}/{mod}".strip("/")

        # KM
        try:
            k_txt = kms[i] if i < len(kms) else "0"
            car["KM"] = int(re.sub(r"[^\d]", "", k_txt))
        except Exception:
            car["KM"] = 0

        # Cor
        cor_txt = cores[i] if i < len(cores) else (cores[-1] if cores else "OUTROS")
        car["Cor"] = cor_txt.split()[0] if cor_txt else "OUTROS"

        # Laudo
        car["Laudo"] = laudo_txt if laudo_txt else "N/A"

        # FIPE
        fipe_raw = (
            fipes_txt[i] if i < len(fipes_txt) else (fipes_txt[-1] if fipes_txt else "")
        )
        fipe_val = parse_money(fipe_raw)

        # Custo Original
        preco_raw = (
            precos_txt[i]
            if i < len(precos_txt)
            else (precos_txt[-1] if precos_txt else "")
        )
        preco_val = parse_money(preco_raw)

        if fipe_val and preco_val and preco_val > 5000:
            car["Fipe"] = fipe_val
            car["Custo_Original"] = preco_val
            extracted.append(car)

    return extracted


def process_pdf(file):
    final_data = []
    with pdfplumber.open(file) as pdf:
        for page in pdf.pages:
            tables = page.extract_tables()
            for table in tables:
                for row in table:
                    if (
                        not row
                        or len(row) < 3
                        or not row[2]
                        or "LOJA" in str(row[0] or "")
                    ):
                        continue
                    cars = extract_cars_from_row(row)
                    final_data.extend(cars)
    return final_data


# --- APP ---
st.title("🏢 R3R Auto-Manager")

# SIDEBAR - Filtros
with st.sidebar:
    st.header("⚙️ Configurações")
    margem = st.number_input("Margem Fixa (R$):", value=2000.0, step=100.0)

    st.divider()
    st.header("🔍 Filtros")
    f_modelo = st.text_input("Modelo (busca)")
    f_km_max = st.number_input("KM Máximo", min_value=0, value=0, step=10000)
    f_laudo = st.multiselect("Laudo", ["APROVADO", "REPROVADO", "PENDENTE", "N/A"])

up = st.file_uploader("📄 Envie o PDF Alphaville", type="pdf")

if up:
    with st.spinner("🔎 Processando oportunidades..."):
        data = process_pdf(up)
        df = pd.DataFrame(data)

        if not df.empty:
            df["Venda"] = df["Custo_Original"] + margem
            df["Lucro"] = df["Fipe"] - df["Custo_Original"]
            df["Margem"] = (df["Lucro"] / df["Fipe"]) * 100

            # Aplicar filtros
            df_filtrado = df.copy()
            if f_modelo:
                df_filtrado = df_filtrado[
                    df_filtrado["Modelo"].str.contains(
                        f_modelo.upper(), case=False, na=False
                    )
                ]
            if f_km_max > 0:
                df_filtrado = df_filtrado[df_filtrado["KM"] <= f_km_max]
            if f_laudo:
                df_filtrado = df_filtrado[df_filtrado["Laudo"].isin(f_laudo)]

            df_filtrado = df_filtrado[df_filtrado["Lucro"] > 0]

            # Métricas
            c1, c2, c3 = st.columns(3)
            c1.metric("🚗 Veículos", len(df_filtrado))
            c2.metric("💰 Lucro Total", f"R$ {df_filtrado['Lucro'].sum():,.0f}")
            c3.metric("📊 Margem Média", f"{df_filtrado['Margem'].mean():.1f}%")

            # ========== TOP 10 OPORTUNIDADES (Margem >= 20%) ==========
            st.subheader("🏆 TOP 10 OPORTUNIDADES (Margem ≥ 20%)")

            top10 = df_filtrado[df_filtrado["Margem"] >= 20].nlargest(10, "Margem")

            if not top10.empty:
                cols = st.columns(2)
                for idx, (_, car) in enumerate(top10.iterrows()):
                    with cols[idx % 2]:
                        st.markdown(
                            f"""
                        <div class="top-card">
                            <h3>#{idx + 1} {car["Modelo"]}</h3>
                            <p><b>Placa:</b> {car["Placa"]} | <b>KM:</b> {car["KM"]:,} | <b>Laudo:</b> {car["Laudo"]}</p>
                            <p><b>FIPE:</b> R$ {car["Fipe"]:,.2f}</p>
                            <p><b>Custo:</b> R$ {car["Custo_Original"]:,.2f}</p>
                            <p class="lucro-destaque">💰 LUCRO: R$ {car["Lucro"]:,.2f} ({car["Margem"]:.1f}%)</p>
                        </div>
                        """,
                            unsafe_allow_html=True,
                        )
            else:
                st.info("Nenhuma oportunidade com margem ≥ 20% encontrada.")

            st.divider()

            # ========== TABELA COMPLETA ==========
            st.subheader(f"📋 Lista Completa ({len(df_filtrado)} veículos)")

            df_display = df_filtrado[
                [
                    "Placa",
                    "Modelo",
                    "Ano",
                    "KM",
                    "Cor",
                    "Laudo",
                    "Custo_Original",
                    "Fipe",
                    "Lucro",
                    "Margem",
                ]
            ].copy()
            df_display = df_display.sort_values("Margem", ascending=False)

            st.dataframe(df_display, use_container_width=True, hide_index=True)

            # Download Excel
            st.divider()
            output = BytesIO()
            with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
                df_filtrado.to_excel(writer, index=False)
            st.download_button(
                "📥 Baixar Excel", output.getvalue(), "Lista_Oportunidades.xlsx"
            )
        else:
            st.error(
                "Nenhum carro identificado. O PDF pode estar como imagem ou layout diferente."
            )
