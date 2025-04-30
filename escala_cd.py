import streamlit as st
import pandas as pd
import gspread
import json
import tempfile
from gspread_dataframe import get_as_dataframe
from datetime import datetime

# Conectar ao Google Sheets
def conectar_gspread():
    credenciais_info = json.loads(st.secrets["CREDENCIAIS_JSON"])
    credenciais_info["private_key"] = credenciais_info["private_key"].replace("\\n", "\n")
    temp_file = tempfile.NamedTemporaryFile(mode="w+", delete=False, suffix=".json")
    json.dump(credenciais_info, temp_file)
    temp_file.flush()
    temp_file.close()
    return gspread.service_account(filename=temp_file.name)

def carregar_planilha(nome):
    sh = gc.open(nome)
    ws = sh.sheet1
    df = get_as_dataframe(ws).dropna(how="all")
    return df, ws

# Variáveis principais
NOME_PLANILHA_ESCALA = "Escala_Maio_2025"
NOME_PLANILHA_USUARIOS = "usuarios"
gc = conectar_gspread()

# Login
st.sidebar.header("Login")
crm_input = st.sidebar.text_input("CRM")
senha_input = st.sidebar.text_input("Senha", type="password")

df_usuarios, _ = carregar_planilha(NOME_PLANILHA_USUARIOS)
df_usuarios["crm"] = df_usuarios["crm"].apply(lambda x: str(int(float(x)))).str.strip()
df_usuarios["senha"] = df_usuarios["senha"].apply(lambda x: str(int(float(x)))).str.strip()
crm_input_str = crm_input.strip()
senha_input_str = senha_input.strip()

autenticado = False
nome_usuario = ""

user_row = df_usuarios[df_usuarios["crm"] == crm_input_str]
if not user_row.empty:
    senha_correta = user_row["senha"].values[0]
    nome_usuario = user_row["nome"].values[0]
    if senha_input_str == senha_correta:
        st.sidebar.success(f"Bem-vindo, {nome_usuario}!")
        autenticado = True
    else:
        st.sidebar.error("Senha incorreta.")
else:
    st.sidebar.error("Contate o chefe da escala para realizar o cadastro.")

# App principal
st.title("Escala de Plantão")

if autenticado:
    df, _ = carregar_planilha(NOME_PLANILHA_ESCALA)
    df = df[df["data"].notna()]
    df["data"] = pd.to_datetime(df["data"], dayfirst=True, errors="coerce").dt.date
    df = df[df["data"].notna()]
    df["turno"] = df["turno"].str.lower()

    data_plantoa = st.date_input("Selecione a data do plantão")
    turno = st.selectbox("Selecione o turno", ["manhã", "tarde", "noite", "cinderela"])

    df_turno = df[(df["data"] == data_plantoa) & (df["turno"] == turno)]
    df_usuario_turno = df_turno[df_turno["nome"].fillna("").str.lower().str.strip() == nome_usuario.lower().strip()]

    if df_turno.empty:
        st.warning("Nenhum plantonista encontrado para essa data e turno.")
    else:
        for idx, row in df_turno.iterrows():
            nome = row["nome"] if pd.notna(row["nome"]) and row["nome"] != "" else "Vaga livre"
            status = row["status"].strip().lower() if pd.notna(row["status"]) else "livre"

            col1, col2 = st.columns([3, 1])
            with col1:
                if status == "repasse":
                    st.warning(f"**{nome}** está repassando o plantão.")
                elif status == "livre" or nome.lower() == "vaga livre":
                    st.error("**Vaga disponível**")
                else:
                    st.success(f"**{nome}** está escalado como `{status}`")

            with col2:
                ja_escalado = not df_usuario_turno.empty

                if (status == "livre" or nome.lower() == "vaga livre") and not ja_escalado:
                    if st.button("Pegar vaga", key=f"pegar_{idx}"):
                        df.at[idx, "nome"] = nome_usuario
                        df.at[idx, "status"] = "extra"
                        salvar_planilha(df, _)
                        st.success("Você pegou a vaga com sucesso! Atualize a página para ver a mudança.")

                elif status == "repasse" and not ja_escalado:
                    if st.button("Assumir", key=f"assumir_{idx}"):
                        df.at[idx, "nome"] = nome_usuario
                        df.at[idx, "status"] = "extra"
                        salvar_planilha(df, _)
                        st.success("Você assumiu o plantão com sucesso! Atualize a página para ver a mudança.")

                elif nome_usuario.lower() in nome.lower() and status != "repasse":
                    if st.button("Repassar", key=f"repassar_{idx}"):
                        df.at[idx, "status"] = "repasse"
                        salvar_planilha(df, _)
                        st.warning("Você colocou seu plantão para repasse. Atualize a página para ver a mudança.")

                elif nome_usuario.lower() in nome.lower() and status == "repasse":
                    if st.button("Cancelar repasse", key=f"cancelar_{idx}"):
                        df.at[idx, "status"] = "fixo"
                        salvar_planilha(df, _)
                        st.success("Você reassumiu o plantão. Atualize a página para ver a mudança.")
else:
    st.info("Faça login na barra lateral para acessar a escala.")
