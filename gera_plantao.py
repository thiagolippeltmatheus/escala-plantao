import pandas as pd
import gspread
import json
import tempfile
import streamlit as st
from gspread_dataframe import get_as_dataframe, set_with_dataframe
from datetime import datetime, timedelta

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
NOME_PLANILHA_FIXOS = 'Plantonistas_Fixos_Completo_real'

# Conectar
gc = conectar_gspread()

# Funções utilitárias
def carregar_planilha(nome_planilha):
    sh = gc.open(nome_planilha)
    worksheet = sh.sheet1
    df = get_as_dataframe(worksheet).dropna(how="all")
    return df, worksheet

def salvar_planilha(df, worksheet):
    worksheet.clear()
    set_with_dataframe(worksheet, df)

def atualizar_escala_proximos_30_dias():
    try:
        df_escala, ws_escala = carregar_planilha(NOME_PLANILHA_ESCALA)
    except Exception:
        df_escala = pd.DataFrame(columns=["data", "dia da semana", "turno", "nome", "crm", "status"])
        sh = gc.open(NOME_PLANILHA_ESCALA)
        ws_escala = sh.sheet1

    df_fixos, _ = carregar_planilha(NOME_PLANILHA_FIXOS)
    hoje = datetime.today().date()
    dias_novos = []

    dias_semana = ["segunda", "terça", "quarta", "quinta", "sexta", "sábado", "domingo"]
    turnos = ["manhã", "tarde", "noite"]
    qtd_plantonistas = {
        "manhã":   {"SEGUNDA": 9, "TERÇA": 9, "QUARTA": 9, "QUINTA": 9, "SEXTA": 9, "SÁBADO": 8, "DOMINGO": 8},
        "tarde":   {"SEGUNDA": 9, "TERÇA": 9, "QUARTA": 9, "QUINTA": 9, "SEXTA": 9, "SÁBADO": 8, "DOMINGO": 8},
        "noite":   {"SEGUNDA": 8, "TERÇA": 7, "QUARTA": 7, "QUINTA": 7, "SEXTA": 7, "SÁBADO": 7, "DOMINGO": 7},
    }

    for i in range(1, 31):
        data = hoje + timedelta(days=i)
        dia_nome = dias_semana[data.weekday()]
        data_str = data.strftime("%d/%m/%Y")

        for turno in turnos:
            existe = ((df_escala["data"] == data_str) & 
                      (df_escala["turno"] == turno) &
                      (df_escala["dia da semana"] == dia_nome)).any()
            if existe:
                continue

            fixos_sel = df_fixos[
                (df_fixos["Dia da Semana"].str.upper() == dia_nome.upper())
                & (df_fixos["Turno"].str.lower() == turno)
            ]
            nomes = list(fixos_sel["Nome"])
            crms = list(fixos_sel["CRM"])

            total = qtd_plantonistas[turno][dia_nome.upper()]
            add_cinderela = False
            if turno == "noite":
                if dia_nome.upper() in ["TERÇA", "QUARTA", "QUINTA", "SEXTA", "SÁBADO"]:
                    add_cinderela = True

            faltam = total - len(nomes)
            if faltam > 0:
                nomes.extend(["VAGA"] * faltam)
                crms.extend([""] * faltam)

            if add_cinderela:
                nomes.append("CINDERELA")
                crms.append("")

            for nome, crm in zip(nomes, crms):
                status = "fixo" if nome not in ["VAGA", "CINDERELA"] else "livre"
                dias_novos.append({
                    "data": data_str,
                    "dia da semana": dia_nome.lower(),
                    "turno": turno,
                    "nome": nome,
                    "crm": crm,
                    "status": status
                })

    if dias_novos:
        df_novos = pd.DataFrame(dias_novos)
        df_escala = pd.concat([df_escala, df_novos], ignore_index=True)
        df_escala = df_escala.drop_duplicates(subset=["data", "turno", "nome", "crm"], keep="first")
        salvar_planilha(df_escala, ws_escala)
        print(f"Escala atualizada até {data_str}.")
    else:
        print("Nenhuma data nova para atualizar.")

if __name__ == "__main__":
    atualizar_escala_proximos_30_dias()
