
import streamlit as st
import pandas as pd
import gspread
import json
import tempfile
from gspread_dataframe import get_as_dataframe, set_with_dataframe
from datetime import date

turnos_disponiveis = ["manhã", "tarde", "noite", "cinderela"]

# Funções primeiro
def conectar_gspread():
    credenciais_info = json.loads(st.secrets["CREDENCIAIS_JSON"])
    credenciais_info["private_key"] = credenciais_info["private_key"].replace("\n", "\n".replace("\\n", "\n"))
    temp_file = tempfile.NamedTemporaryFile(mode="w+", delete=False, suffix=".json")
    json.dump(credenciais_info, temp_file)
    temp_file.flush()
    temp_file.close()
    return gspread.service_account(filename=temp_file.name)

def carregar_planilha(nome_planilha):
    sh = gc.open(nome_planilha)
    worksheet = sh.sheet1
    df = get_as_dataframe(worksheet).dropna(how="all")
    return df, worksheet

def salvar_planilha(df, worksheet):
    worksheet.clear()
    set_with_dataframe(worksheet, df)

NOME_PLANILHA_ESCALA = 'Escala_Maio_2025'
NOME_PLANILHA_USUARIOS = 'usuarios'

gc = conectar_gspread()

try:
    df_usuarios, ws_usuarios = carregar_planilha(NOME_PLANILHA_USUARIOS)
except Exception as e:
    st.error(f"Erro ao carregar usuários: {e}")
    st.stop()

# Login
st.sidebar.header("Login")

if "autenticado" not in st.session_state:
    st.session_state.autenticado = False
if "nome_usuario" not in st.session_state:
    st.session_state.nome_usuario = ""
if "modo_nova_senha" not in st.session_state:
    st.session_state.modo_nova_senha = False

crm_input = st.sidebar.text_input("CRM", key="crm_input")
senha_input = st.sidebar.text_input("Senha", type="password", key="senha_input")

if st.sidebar.button("Entrar"):
    user_row = df_usuarios[df_usuarios["crm"] == str(crm_input).strip()]
    if not user_row.empty:
        senha_correta = user_row["senha"].values[0]
        nome_usuario = user_row["nome"].values[0]
        if str(senha_input).strip() == senha_correta:
            if senha_input.strip() == crm_input.strip():
                st.session_state.modo_nova_senha = True
            else:
                st.session_state.autenticado = True
                st.session_state.nome_usuario = nome_usuario
                st.sidebar.success(f"Bem-vindo, {nome_usuario}!")
        else:
            st.sidebar.error("Senha incorreta.")
    else:
        st.sidebar.error("Contate o chefe da escala para realizar o cadastro.")

# Troca de senha se necessário
if st.session_state.modo_nova_senha:
    nova_senha = st.sidebar.text_input("Escolha uma nova senha (apenas números)", type="password", key="nova_senha_input")
    if nova_senha:
        if nova_senha.isdigit():
            df_usuarios.loc[df_usuarios["crm"] == crm_input.strip(), "senha"] = nova_senha
            salvar_planilha(df_usuarios, ws_usuarios)
            st.sidebar.success("Senha atualizada com sucesso. Refaça o login.")
            st.session_state.modo_nova_senha = False
            st.session_state.autenticado = False
            st.stop()
        else:
            st.sidebar.error("A nova senha deve conter apenas números.")

# Estado final do login
autenticado = st.session_state.autenticado
nome_usuario = st.session_state.nome_usuario
