# Guaratiba Praia do Bahia

## Rodar localmente
```bash
pip install -r requirements.txt
python app.py
```

Abra:
- Site público: `http://127.0.0.1:5000/`
- Painel: `http://127.0.0.1:5000/adm`

## Variáveis de ambiente recomendadas
```bash
export SECRET_KEY='uma-chave-bem-forte'
export ADMIN_EMAIL='h.d.hoficial3658@gmail.com'
export ADMIN_PASSWORD='sua-senha'
export SMTP_HOST='smtp.gmail.com'
export SMTP_PORT='587'
export SMTP_USER='seuemail@gmail.com'
export SMTP_PASS='senha-de-app-do-gmail'
export SMTP_USE_TLS='1'
```

## Observação importante
Para envio de código por e-mail no Gmail, normalmente é preciso usar **senha de app** com 2 etapas ativadas, não a senha normal da conta.
