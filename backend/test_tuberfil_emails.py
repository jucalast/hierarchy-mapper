"""
Teste APOS a correcao: verifica se o novo fluxo retorna emails corretos.
"""
import asyncio
import sys
import os
import io

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.path.insert(0, os.path.dirname(__file__))

from core.external.email_service import discover_and_validate_email, get_mx_record
import unicodedata

DOMAIN = "tuberfil.com.br"

CONTACTS = [
    ("Renata", "Oliveira"),       # Renata Cristina Garanhani de Oliveira
    ("Andrea", "Silva"),          # Andrea Aparecida Soares da Silva
    ("Elieber", "Santos"),        # Elieber Maciel Santos
    ("Natany", "Lima"),           # Natany Lima
    ("Emerson", "Ribeiro"),       # Emerson Ribeiro
    ("Odirlei", "Esteves"),       # Odirlei Esteves
    ("Hugo", "Tida"),             # Hugo Tida
    ("Patricia", "Santos"),       # Patricia Santos
    ("Daniela", "Pereira"),       # Daniela Cardim Cardoso Pereira
    ("Eduardo", "Previatto"),     # Eduardo Previatto
    ("Edilson", "Exel"),          # Edilson Exel
    ("Jeova", "Diego"),           # Jeova Diego
    ("Monica", "Ledesma"),        # Monica Ledesma
    ("Juciane", "Cunha"),         # Juciane Cunha
]


async def main():
    print("=" * 70)
    print("  TESTE POS-CORRECAO: discover_and_validate_email")
    print("=" * 70)

    mx = await get_mx_record(DOMAIN)
    print(f"MX Host: {mx}")
    print()

    confirmed = 0
    not_confirmed = 0

    for first_raw, last_raw in CONTACTS:
        f = "".join(c for c in unicodedata.normalize("NFD", first_raw.lower()) if unicodedata.category(c) != 'Mn')
        l = "".join(c for c in unicodedata.normalize("NFD", last_raw.lower()) if unicodedata.category(c) != 'Mn')

        result = await discover_and_validate_email(
            first=f, last=l, domain=DOMAIN,
            do_smtp=True
        )

        email = result.get("email", "N/A")
        smtp = result.get("smtp_result", "N/A")
        confidence = result.get("confidence", "N/A")

        if smtp == "valid":
            status = "CONFIRMADO"
            confirmed += 1
        elif smtp == "catchall":
            status = "CATCH-ALL (nao confiavel)"
            not_confirmed += 1
        else:
            status = f"NAO CONFIRMADO ({smtp})"
            not_confirmed += 1

        print(f"  {first_raw} {last_raw}")
        print(f"    Email: {email}")
        print(f"    SMTP: {smtp} | Confidence: {confidence}")
        print(f"    Status: {status}")
        print()

    print("=" * 70)
    print(f"  RESULTADO: {confirmed} confirmados | {not_confirmed} nao confirmados")
    print(f"  (Antes da correcao: 14 confirmados / 11 errados)")
    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(main())
