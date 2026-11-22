"""Extrae de los datos abiertos de la Plataforma de Contratación del Sector Público (PLACSP)
los contratos de un órgano de contratación y los guarda en data/contratos/<año>.json.

Uso: python scripts/contratos.py <año> [texto_del_organo]

Fuentes (ficheros ZIP con feeds ATOM/CODICE, uno por mes o por año):
  - Licitaciones de perfiles alojados en la Plataforma (sindicación 643)
  - Contratos menores (sindicación 1143)
Una misma licitación aparece varias veces (cada actualización); se queda la última.
"""
import io
import json
import sys
import zipfile
from pathlib import Path

import requests
from lxml import etree

ROOT = Path(__file__).resolve().parent.parent
BASE = "https://contrataciondelsectorpublico.gob.es/sindicacion"
FEEDS = {
    "licitacion": ("sindicacion_643", "licitacionesPerfilesContratanteCompleto3"),
    "menor": ("sindicacion_1143", "contratosMenoresPerfilesContratantes"),
}
S = requests.Session()
S.headers["User-Agent"] = "Mozilla/5.0 (presupuestos-venta-de-banos)"


def ln(el):
    return etree.QName(el).localname


def primero(el, *ruta):
    """Primer descendiente siguiendo una ruta de nombres locales."""
    actual = [el]
    for nombre in ruta:
        siguiente = []
        for a in actual:
            siguiente += [d for d in a.iter() if d is not a and ln(d) == nombre]
        if not siguiente:
            return None
        actual = siguiente
    return actual[0]


def texto(el, *ruta):
    n = primero(el, *ruta)
    return n.text.strip() if n is not None and n.text else None


def importe(el, *ruta):
    t = texto(el, *ruta)
    try:
        return float(t) if t else None
    except ValueError:
        return None


def contrato(entry, tipo_feed):
    cfs = primero(entry, "ContractFolderStatus")
    res = primero(cfs, "TenderResult") if cfs is not None else None
    link = next((l.get("href") for l in entry.iter() if ln(l) == "link" and l.get("href")), None)
    return {
        "id": texto(entry, "id"),
        "actualizado": texto(entry, "updated"),
        "feed": tipo_feed,
        "expediente": texto(cfs, "ContractFolderID"),
        "titulo": texto(cfs, "ProcurementProject", "Name") or texto(entry, "title"),
        "estado": texto(cfs, "ContractFolderStatusCode"),
        "tipo": texto(cfs, "ProcurementProject", "TypeCode"),
        "cpv": [c.text for c in cfs.iter() if ln(c) == "ItemClassificationCode" and c.text] if cfs is not None else [],
        "presupuesto_sin_iva": importe(cfs, "ProcurementProject", "BudgetAmount", "TaxExclusiveAmount"),
        "procedimiento": texto(cfs, "TenderingProcess", "ProcedureCode"),
        "adjudicatario": texto(res, "WinningParty", "PartyName", "Name") if res is not None else None,
        "nif_adjudicatario": texto(res, "WinningParty", "PartyIdentification", "ID") if res is not None else None,
        "importe_adjudicado_sin_iva": importe(res, "AwardedTenderedProject", "LegalMonetaryTotal", "TaxExclusiveAmount") if res is not None else None,
        "importe_adjudicado_con_iva": importe(res, "AwardedTenderedProject", "LegalMonetaryTotal", "PayableAmount") if res is not None else None,
        "fecha_adjudicacion": texto(res, "AwardDate") if res is not None else None,
        "ofertas_recibidas": importe(res, "ReceivedTenderQuantity") if res is not None else None,
        "urgencia": texto(cfs, "TenderingProcess", "UrgencyCode"),
        "fin_plazo_ofertas": texto(cfs, "TenderingProcess", "TenderSubmissionDeadlinePeriod", "EndDate"),
        "fondos_ue": texto(cfs, "TenderingTerms", "FundingProgramCode") or texto(cfs, "FundingProgramCode"),
        "organo": texto(cfs, "LocatedContractingParty", "Party", "PartyName", "Name"),
        "enlace": link,
    }


def zips(anio: int, carpeta: str, prefijo: str):
    """Intenta el ZIP anual; si no existe, los mensuales."""
    for sufijo in [str(anio)] + [f"{anio}{m:02d}" for m in range(1, 13)]:
        url = f"{BASE}/{carpeta}/{prefijo}_{sufijo}.zip"
        r = S.get(url, timeout=1800)
        print(f"  {r.status_code} {url} ({len(r.content) // 1_000_000} MB)")
        if r.ok and r.content[:2] == b"PK":
            yield zipfile.ZipFile(io.BytesIO(r.content))
            if sufijo == str(anio):
                return


def main(anio: str, organo: str = "Venta de Ba") -> int:
    anio = int(anio)
    encontrados: dict[str, dict] = {}
    for tipo_feed, (carpeta, prefijo) in FEEDS.items():
        for z in zips(anio, carpeta, prefijo):
            for nombre in z.namelist():
                if not nombre.endswith(".atom"):
                    continue
                with z.open(nombre) as f:
                    for _, entry in etree.iterparse(f, events=("end",), tag="{http://www.w3.org/2005/Atom}entry", huge_tree=True):
                        partes = " ".join(t for el in entry.iter() if ln(el) == "LocatedContractingParty" for t in el.itertext())
                        if organo.lower() in partes.lower():
                            c = contrato(entry, tipo_feed)
                            clave = c["id"] or c["expediente"]
                            if clave not in encontrados or (c["actualizado"] or "") > (encontrados[clave]["actualizado"] or ""):
                                encontrados[clave] = c
                        entry.clear()
                        while entry.getprevious() is not None:
                            del entry.getparent()[0]
    destino = ROOT / "data" / "contratos"
    destino.mkdir(parents=True, exist_ok=True)
    lista = sorted(encontrados.values(), key=lambda c: c["fecha_adjudicacion"] or c["actualizado"] or "")
    (destino / f"{anio}.json").write_text(json.dumps(lista, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"[+] {anio}: {len(lista)} contratos de '{organo}'")
    for c in lista[:15]:
        print("   ", c["feed"], c["fecha_adjudicacion"], c["importe_adjudicado_sin_iva"], c["adjudicatario"], "|", (c["titulo"] or "")[:80])
    return 0


if __name__ == "__main__":
    sys.exit(main(*sys.argv[1:]))
