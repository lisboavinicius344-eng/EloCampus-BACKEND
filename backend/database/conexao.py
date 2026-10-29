import os

import psycopg
from dotenv import load_dotenv
from psycopg.types.string import TextLoader


load_dotenv()


class Conexao:
    @staticmethod
    def conectar():
        conexao = psycopg.connect(
            host=os.getenv("DB_HOST"),
            port=os.getenv("DB_PORT", "5432"),
            dbname=os.getenv("DB_NAME"),
            user=os.getenv("DB_USER"),
            password=os.getenv("DB_PASSWORD"),
            connect_timeout=5
        )

        # Ids de usuário são UUID: devolve como texto, para irem prontos
        # ao JSON das respostas, ao token e ao n8n.
        conexao.adapters.register_loader("uuid", TextLoader)

        return conexao
