import streamlit as st
import pandas as pd
import re
import pdfplumber

# --- CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(page_title="FipeHunter - v0.3", page_icon="🚜", layout="wide")


# --- FUNÇÕES DE LIMPEZA E EXTRAÇÃO ---
def clean_currency(value_str):
    """
    Limpa strings de moeda complexas.
    Aceita: 'R$ 100.000', '100 000', '100.000,00'
    """
    if not value_str:
        return 0.0
    # Mantém apenas dígitos, pontos e vírgulas
    clean_str = re.sub(r"[^\d,.]", "", str(value_str))

    # Lógica para detectar se ponto/espaço é milhar ou decimal
    # Se tiver vírgula, assume padrão BR (1.000,00)
    if "," in clean_str:
        clean_str = clean_str.replace(".", "")  # Remove milhar
        clean_str = clean_str.replace(",", ".")  # Troca virgula por ponto decimal
    else:
        # Se NÃO tiver vírgula (ex: 131638 ou 131.638)
        # Assume que ponto é milhar, pois carros custam > 500 reais
        clean_str = clean_str.replace(".", "")

    try:
        return float(clean_str)
    except:
        return 0.0


def extract_model_from_text(full_text):
    """Remove a placa e preços do texto bruto para tentar isolar o Modelo"""
    # Remove a placa
    text = re.sub(r"\b[A-Z]{3}[0-9][A-Z0-9][0-9]{2}\b", "", full_text)
    # Remove padrões de dinheiro
    text = re.sub(r"(?:R\$|RS|R|\$)\s?[\d\.\s,]+", "", text)
    # Limpa quebras de linha e espaços extras
    text = text.replace("\n", " ").strip()

    words = text.split()
    # Remove palavras comuns de cabeçalho/lixo do PDF
    stopwords = [
        "oferta",
        "disponivel",
        "sp",
        "barueri",
        "de",
        "para",
        "em",
        "loja",
        "acordo",
        "com",
    ]
    clean_words = [w for w in words if w.lower() not in stopwords and len(w) > 1]

    # Retorna as primeiras 6 palavras (geralmente é Marca Modelo Versão)
    return " ".join(clean_words[:6])


def process_pdf_smart_mode(text):
    """
    MODO ASPIRADOR (STATE MACHINE):
    Lê o texto corrido. Abre um contexto quando acha uma Placa.
    Coleta todos os preços e textos até encontrar a próxima Placa.
    """
    data = []

    # Regex de Placa (Mercosul e Antiga)
    plate_pattern = r"\b[A-Z]{3}[0-9][A-Z0-9][0-9]{2}\b"

    # Regex de Dinheiro FLEXÍVEL (Pega 'R$ 100', 'R$ 100.000', 'R$ 100 000')
    money_pattern = r"(?:R\$|RS|R|\$)\s?[\d\.\s,]+"

    # Quebra em linhas para iterar
    lines = text.split("\n")

    current_car = None

    for line in lines:
        # Tenta achar placa na linha
        plate_match = re.search(plate_pattern, line)

        if plate_match:
            # Se já tinha um carro aberto, salva ele antes de começar o novo
            if current_car:
                finalize_car(current_car, data)

            # Abre novo contexto de carro
            current_car = {
                "placa": plate_match.group(),
                "full_text": line,
                "prices_raw": [],
                "year_model": "-",
            }

        # Se tem um carro aberto, continua aspirando dados das linhas seguintes
        if current_car:
            # 1. Coleta Preços na linha
            prices = re.findall(money_pattern, line)
            for p in prices:
                # Filtra lixo (ex: "R$ " vazio ou muito curto)
                if len(re.sub(r"\D", "", p)) > 2:
                    current_car["prices_raw"].append(p)

            # 2. Tenta achar Ano (ex: 2023, 2024/2025)
            if current_car["year_model"] == "-":
                year_match = re.search(r"\b(20[1-2][0-9])\b", line)
                if year_match:
                    current_car["year_model"] = year_match.group(0)

            # 3. Acumula texto para extração do modelo
            current_car["full_text"] += " " + line

    # Não esquecer de salvar o último carro do arquivo
    if current_car:
        finalize_car(current_car, data)

    return pd.DataFrame(data)


def finalize_car(car, data_list):
    """Processa os dados brutos acumulados de um carro"""
    # Limpa e converte preços
    clean_prices = []
    for p in car["prices_raw"]:
        val = clean_currency(p)
        # Filtra valores irrisórios (taxas, multas pequenas)
        if val > 3000:
            clean_prices.append(val)

    # Ordena preços (Maior = Fipe, Segundo Maior = Repasse)
    clean_prices = sorted(clean_prices, reverse=True)

    if len(clean_prices) >= 2:
        item = {
            "Placa": car["placa"],
            "Ano": car["year_model"],
            "Modelo": extract_model_from_text(car["full_text"]),
            "Fipe": clean_prices[0],
            "Repasse": clean_prices[1],
            "Lucro_Real": 0.0,
            "IPVA_Estimado": 0.0,
            "Status": "OK",
        }

        # Tenta detectar IPVA (Se tiver um 3º valor entre 2k e 15k na lista)
        potential_ipva = [x for x in clean_prices[2:] if 2000 < x < 18000]
        if potential_ipva:
            item["IPVA_Estimado"] = potential_ipva[0]
            item["Status"] = "Com IPVA desc."

        # Cálculo de Lucro Líquido
        item["Lucro_Real"] = item["Fipe"] - item["Repasse"] - item["IPVA_Estimado"]

        if item["Fipe"] > 0:
            item["Margem_%"] = round((item["Lucro_Real"] / item["Fipe"]) * 100, 1)

            # Filtro de Sanidade:
            # Margem > 3% (ninguém trabalha de graça)
            # Margem < 60% (evita erros de leitura absurdos)
            if 3 < item["Margem_%"] < 60:
                data_list.append(item)


# --- FRONTEND STREAMLIT ---
st.title("🚜 FipeHunter v0.3")
st.caption("Modo Aspirador: Lê listas quebradas, Localiza, Alphaville e Desmobja")

uploaded_file = st.file_uploader("Solte o PDF aqui", type="pdf")

if uploaded_file:
    with st.spinner("O Robô está aspirando os dados..."):
        try:
            all_text = ""
            with pdfplumber.open(uploaded_file) as pdf:
                for page in pdf.pages:
                    t = page.extract_text()
                    if t:
                        all_text += t + "\n"

            # Processa com a nova lógica
            df = process_pdf_smart_mode(all_text)

            if not df.empty:
                df = df.sort_values(by="Lucro_Real", ascending=False)

                # --- SNIPER MODE (Top 3) ---
                st.divider()
                st.subheader("🔥 Top 3 Oportunidades")

                cols = st.columns(3)
                top_cars = df.head(3).to_dict("records")

                for i, car in enumerate(top_cars):
                    cols[i].metric(
                        label=f"{car['Modelo'][:25]}...",
                        value=f"R$ {car['Lucro_Real']:,.0f}",
                        delta=f"{car['Margem_%']}%",
                    )
                    cols[i].caption(f"Placa: {car['Placa']} | Ano: {car['Ano']}")

                # --- TABELA COMPLETA ---
                st.divider()
                st.subheader("📋 Lista Completa")
                st.dataframe(
                    df[
                        [
                            "Modelo",
                            "Ano",
                            "Placa",
                            "Fipe",
                            "Repasse",
                            "IPVA_Estimado",
                            "Lucro_Real",
                            "Margem_%",
                            "Status",
                        ]
                    ],
                    use_container_width=True,
                    hide_index=True,
                )
            else:
                st.warning(
                    "Não consegui identificar carros. Verifique se o PDF contém texto selecionável (não pode ser imagem escaneada)."
                )

        except Exception as e:
            st.error(f"Erro ao processar: {e}")
