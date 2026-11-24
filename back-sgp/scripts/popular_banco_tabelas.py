import glob
import os
import sys

import pandas as pd

# Adiciona a raiz do projeto no path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.database import Base, SessionLocal, engine
from app.models.tabelas_salariais import (
    TabelaRetribuicaoTitulacao,
    TabelaVencimentoBasico,
)


def main():
    print("Criando tabelas no banco de dados...")
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()

    # Checar se ja populou
    if db.query(TabelaVencimentoBasico).first() is not None:
        print("Tabelas já parecem estar populadas. Abortando seed.")
        return

    # Buscar a planilha correta (PLAN 5)
    files = glob.glob('models/PLAN 5*.xls*')
    if not files:
        print("Arquivo da PLAN 5 não encontrado na pasta models/")
        return
    
    file_path = files[0]
    print(f"Lendo dados de {file_path}...")
    df = pd.read_excel(file_path, sheet_name='CALCULOS')

    # --- 1. Extrair Tabela Vencimento Básico ---
    # As linhas identificadas para VB eram da 13 até 26, nas colunas 39 a 41
    subset_vb = df.iloc[12:28, 39:42]
    
    current_class = None
    for index, row in subset_vb.iterrows():
        classe_val = row.iloc[0]
        nivel_val = row.iloc[1]
        valor_val = row.iloc[2]

        if pd.notna(classe_val) and str(classe_val).strip() != "" and str(classe_val).strip() != "CLASSE":
            current_class = str(classe_val).strip()
        
        if current_class and pd.notna(nivel_val) and pd.notna(valor_val) and isinstance(nivel_val, (int, float)):
            try:
                vb = TabelaVencimentoBasico(
                    classe=current_class,
                    nivel=int(nivel_val),
                    valor=float(valor_val)
                )
                db.add(vb)
            except ValueError:
                pass

    # --- 2. Extrair Tabela Retribuição por Titulação ---
    # As linhas para RT eram da 31 a 45, colunas 39 a 43
    subset_rt = df.iloc[30:46, 39:44]
    
    current_class = None
    for index, row in subset_rt.iterrows():
        classe_val = row.iloc[0]
        nivel_val = row.iloc[1]
        val_esp = row.iloc[2]
        val_mestrado = row.iloc[3]
        val_doutorado = row.iloc[4]

        if pd.notna(classe_val) and str(classe_val).strip() != "" and str(classe_val).strip() != "CLASSE":
            current_class = str(classe_val).strip()
        
        if current_class and pd.notna(nivel_val) and isinstance(nivel_val, (int, float)):
            try:
                if pd.notna(val_esp):
                    db.add(TabelaRetribuicaoTitulacao(classe=current_class, nivel=int(nivel_val), titulacao="Especializacao", valor=float(val_esp)))
                if pd.notna(val_mestrado):
                    db.add(TabelaRetribuicaoTitulacao(classe=current_class, nivel=int(nivel_val), titulacao="Mestrado", valor=float(val_mestrado)))
                if pd.notna(val_doutorado):
                    db.add(TabelaRetribuicaoTitulacao(classe=current_class, nivel=int(nivel_val), titulacao="Doutorado", valor=float(val_doutorado)))
            except ValueError:
                pass

    db.commit()
    print("Banco de dados populado com sucesso com Vencimentos Básicos e Retribuições por Titulação!")
    db.close()

if __name__ == "__main__":
    main()
