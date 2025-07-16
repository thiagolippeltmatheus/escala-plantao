import pandas as pd
import gspread
import json
import tempfile
from gspread_dataframe import get_as_dataframe, set_with_dataframe
from datetime import datetime, timedelta
import os

def conectar_gspread():
    if "CREDENCIAIS_JSON" not in os.environ:
        raise ValueError("CREDENCIAIS_JSON não encontrado no ambiente.")

    credenciais_info = json.loads(os.environ["CREDENCIAIS_JSON"])
    credenciais_info["private_key"] = credenciais_info["private_key"].replace("\\n", "\n")

    temp_file = tempfile.NamedTemporaryFile(mode="w+", delete=False, suffix=".json")
    json.dump(credenciais_info, temp_file)
    temp_file.flush()
    temp_file.close()

    gc = gspread.service_account(filename=temp_file.name)
    return gc

NOME_PLANILHA_ESCALA = 'Escala_Maio_2025'
NOME_PLANILHA_FIXOS = 'Plantonistas_Fixos_Completo_real'

gc = conectar_gspread()

def carregar_planilha(nome_planilha):
    sh = gc.open(nome_planilha)
    worksheet = sh.sheet1
    df = get_as_dataframe(worksheet, evaluate_formulas=True).dropna(how="all")

    if nome_planilha == NOME_PLANILHA_ESCALA:
        colunas_esperadas = ["data", "dia da semana", "turno", "nome", "crm", "status", "funcao"]
    else:
        colunas_esperadas = ["Dia da Semana", "Turno", "Nome", "CRM", "Nome_quinzenal", "CRM_quinzenalCRM", "Funcao"]

    for col in colunas_esperadas:
        if col not in df.columns:
            df[col] = ""

    return df, worksheet

def salvar_planilha(df, worksheet):
    worksheet.clear()
    set_with_dataframe(worksheet, df)

def atualizar_escala_proximos_30_dias():
    try:
        df_escala, ws_escala = carregar_planilha(NOME_PLANILHA_ESCALA)
    except Exception:
        df_escala = pd.DataFrame(columns=["data", "dia da semana", "turno", "nome", "crm", "status", "funcao"])
        sh = gc.open(NOME_PLANILHA_ESCALA)
        ws_escala = sh.sheet1

    df_fixos, _ = carregar_planilha(NOME_PLANILHA_FIXOS)

    df_fixos["Dia da Semana Limpo"] = df_fixos["Dia da Semana"].str.extract(r"(\w+)", expand=False).str.lower()
    df_fixos["Turno Limpo"] = df_fixos["Turno"].astype(str).str.replace('\xa0', '', regex=False).str.strip().str.lower()

    hoje = datetime.today().date()
    dias_novos = []
    dias_semana = ["segunda", "terça", "quarta", "quinta", "sexta", "sábado", "domingo"]
    turnos = ["manhã", "tarde", "noite", "cinderela"]

    for i in range(1, 61):
        data = hoje + timedelta(days=i)
        dia_nome = dias_semana[data.weekday()]
        data_str = data.strftime("%d/%m/%Y")
        semana_num = data.isocalendar()[1]

        for turno in turnos:
            existe = ((df_escala["data"] == data_str) &
                      (df_escala["turno"] == turno) &
                      (df_escala["dia da semana"] == dia_nome)).any()
            if existe:
                continue

            fixos_sel = df_fixos[
                (df_fixos["Dia da Semana Limpo"] == dia_nome.lower()) &
                (df_fixos["Turno Limpo"] == turno)
            ]

            for _, row in fixos_sel.iterrows():
                nome_base = row["Nome"]
                crm_base = row["CRM"]
                nome_q = row.get("Nome_quinzenal")
                crm_q = row.get("CRM_quinzenalCRM")

                if pd.notna(nome_q) and semana_num % 2 == 0:
                    nome = nome_q
                    crm = crm_q
                else:
                    nome = nome_base
                    crm = crm_base

                status = "fixo" if nome not in ["VAGA", "CINDERELA"] else "livre"

                linha_match = fixos_sel[
                    (fixos_sel["Nome"].astype(str).str.strip() == str(nome).strip()) &
                    (fixos_sel["CRM"].astype(str).str.strip() == str(crm).strip())
                ]
                funcao_extra = ""
                if not linha_match.empty:
                    funcao_raw = str(linha_match.iloc[0].get("Funcao", "")).strip()
                    funcao_extra = funcao_raw if funcao_raw.lower() != "nan" else ""

                dias_novos.append({
                    "data": data_str,
                    "dia da semana": dia_nome.lower(),
                    "turno": turno,
                    "nome": nome,
                    "crm": crm,
                    "status": status,
                    "funcao": funcao_extra
                })

    if dias_novos:
        df_novos = pd.DataFrame(dias_novos)
        turnos_novos = set(df_novos[["data", "turno"]].apply(tuple, axis=1))
        df_escala = df_escala[~df_escala[["data", "turno"]].apply(tuple, axis=1).isin(turnos_novos)]
        df_escala = pd.concat([df_escala, df_novos], ignore_index=True)
        salvar_planilha(df_escala, ws_escala)
        print(f"Escala atualizada até {data_str}.")
    else:
        print("Nenhuma data nova para atualizar.")

if __name__ == "__main__":
    atualizar_escala_proximos_30_dias()