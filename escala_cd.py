import streamlit as st
import pandas as pd
import gspread
import json
import tempfile
from gspread_dataframe import get_as_dataframe, set_with_dataframe
from datetime import date

# Função para conectar ao Google Sheets usando credenciais dos secrets
def conectar_gspread():
    credenciais_info = json.loads(st.secrets["CREDENCIAIS_JSON"])

    # Corrigir a chave privada para ter quebras de linha reais
    credenciais_info["private_key"] = credenciais_info["private_key"].replace("\\n", "\n")

    # Criar arquivo temporário
    temp_file = tempfile.NamedTemporaryFile(mode="w+", delete=False, suffix=".json")
    json.dump(credenciais_info, temp_file)
    temp_file.flush()
    temp_file.close()

    # Agora conecta ao gspread
    gc = gspread.service_account(filename=temp_file.name)
    return gc

# Nome das planilhas
NOME_PLANILHA_ESCALA = 'Escala_Maio_2025'
NOME_PLANILHA_USUARIOS = 'usuarios'

# Conectar
gc = conectar_gspread()

# Funções para carregar e salvar dados
def carregar_planilha(nome_planilha):
    sh = gc.open(nome_planilha)
    worksheet = sh.sheet1
    df = get_as_dataframe(worksheet).dropna(how="all")
    return df, worksheet

def salvar_planilha(df, worksheet):
    worksheet.clear()
    set_with_dataframe(worksheet, df)

# Carregar dados de usuários
try:
    df_usuarios, ws_usuarios = carregar_planilha(NOME_PLANILHA_USUARIOS)
except Exception as e:
    st.error(f"Erro ao carregar usuários: {e}")
    st.stop()

# Login
st.sidebar.header("Login")
crm_input = st.sidebar.text_input("CRM")
senha_input = st.sidebar.text_input("Senha", type="password")

autenticado = False
nome_usuario = ""

crm_input_str = crm_input.strip()
user_exists = crm_input_str in df_usuarios["crm"].astype(str).str.strip().values

if user_exists:
    user_row = df_usuarios[df_usuarios["crm"].astype(str).str.strip() == crm_input_str]
    senha_correta = user_row["senha"].astype(str).values[0].strip()
    nome_usuario = user_row["nome"].values[0]
    if senha_input.strip() == senha_correta:
        st.sidebar.success(f"Bem-vindo, {nome_usuario}!")
        autenticado = True
    else:
        st.sidebar.error("Senha incorreta")
else:
    st.sidebar.warning("Novo usuário. Cadastre sua senha.")
    novo_nome = st.sidebar.text_input("Seu nome completo")
    nova_senha = st.sidebar.text_input("Criar senha", type="password")
    confirmar = st.sidebar.button("Criar conta")

    if confirmar and novo_nome and nova_senha:
        novo_usuario = pd.DataFrame([[crm_input, novo_nome, nova_senha]], columns=["crm", "nome", "senha"])
        df_usuarios = pd.concat([df_usuarios, novo_usuario], ignore_index=True)
        salvar_planilha(df_usuarios, ws_usuarios)
        st.sidebar.success("Cadastro criado! Refaça o login.")

# App principal
st.title("Escala de Plantão")

if autenticado:
    try:
        df, ws_escala = carregar_planilha(NOME_PLANILHA_ESCALA)
    except Exception as e:
        st.error(f"Erro ao carregar escala: {e}")
        st.stop()

    df["data"] = pd.to_datetime(df["data"], dayfirst=True).dt.date
    df["turno"] = df["turno"].str.lower()

    data_plantoa = st.date_input("Selecione a data do plantão")
    turno = st.selectbox("Selecione o turno", ["manhã", "tarde", "noite", "cinderela"])

    st.markdown(f"**Data selecionada:** {data_plantoa.strftime('%d/%m/%Y')} - **Turno:** {turno.capitalize()}")

    df_turno = df[(df["data"] == data_plantoa) & (df["turno"] == turno)]
    df_usuario_turno = df_turno[df_turno["nome"].fillna("").astype(str).str.lower().str.strip() == nome_usuario.lower().strip()]

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
                elif status == "livre" or nome.strip().lower() == "vaga livre":
                    st.error("**Vaga disponível**")
                else:
                    st.success(f"**{nome}** está escalado como `{status}`")

            with col2:
                ja_escalado = not df_usuario_turno.empty

                if (status == "livre" or nome.strip().lower() == "vaga livre") and not ja_escalado:
                    if st.button("Pegar vaga", key=f"pegar_{idx}"):
                        df.at[idx, "nome"] = nome_usuario
                        df.at[idx, "status"] = "extra"
                        salvar_planilha(df, ws_escala)
                        st.success("Você pegou a vaga com sucesso! Atualize a página para ver a mudança.")

                elif status == "repasse" and not ja_escalado:
                    if st.button("Assumir", key=f"assumir_{idx}"):
                        df.at[idx, "nome"] = nome_usuario
                        df.at[idx, "status"] = "extra"
                        salvar_planilha(df, ws_escala)
                        st.success("Você assumiu o plantão com sucesso! Atualize a página para ver a mudança.")

                elif nome_usuario.strip().lower() in nome.strip().lower() and status != "repasse":
                    if st.button("Repassar", key=f"repassar_{idx}"):
                        df.at[idx, "status"] = "repasse"
                        salvar_planilha(df, ws_escala)
                        st.warning("Você colocou seu plantão para repasse. Atualize a página para ver a mudança.")

                elif nome_usuario.strip().lower() in nome.strip().lower() and status == "repasse":
                    if st.button("Cancelar repasse", key=f"cancelar_{idx}"):
                        df.at[idx, "status"] = "fixo"
                        salvar_planilha(df, ws_escala)
                        st.success("Você reassumiu o plantão. Atualize a página para ver a mudança.")
else:
    st.info("Faça login na barra lateral para acessar a escala de plantão.")
