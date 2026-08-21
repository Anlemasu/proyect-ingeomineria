"""Extracción de tablas de PDF, opcionalmente en paralelo.

Sin dependencias de Django a propósito: ProcessPoolExecutor en Windows usa
'spawn', que reimporta este módulo en cada proceso hijo — si importara algo
de apps.masters.models forzaría a cada hijo a inicializar Django
(django.setup(), settings, DB) solo para hacer trabajo CPU-bound que no
toca la base de datos. Manteniendo este módulo aislado (solo pdfplumber +
stdlib), los procesos hijos arrancan rápido y sin tocar el ORM.

page.extract_table() es CPU-bound (análisis de posiciones de texto en
Python puro) y no libera el GIL, así que hilos no ayudan — un PDF de ~300
páginas tarda varios minutos en un solo proceso. Como cada página se
extrae de forma independiente, se reparte entre procesos.
"""
import io
import os
from concurrent.futures import ProcessPoolExecutor

# Por debajo de este número de páginas no compensa el overhead de arrancar
# procesos (cada uno reabre el PDF completo). También mantiene los tests
# (que mockean pdfplumber.open con PDFs falsos de 1-2 páginas) corriendo en
# el mismo proceso, donde el mock aplica.
MIN_PAGES_FOR_PARALLEL = 20

MAX_WORKERS = 8


def _extract_chunk(data: bytes, page_indices: list[int]) -> list[tuple[int, list | None]]:
    import pdfplumber
    with pdfplumber.open(io.BytesIO(data)) as pdf:
        return [(i, pdf.pages[i].extract_table()) for i in page_indices]


def extract_tables(file) -> list[list | None]:
    """Devuelve extract_table() de cada página de `file` (objeto
    file-like abierto en binario), en el mismo orden que las páginas del
    PDF. Para PDFs con muchas páginas, reparte la extracción entre varios
    procesos.
    """
    import pdfplumber

    data = file.read()

    with pdfplumber.open(io.BytesIO(data)) as pdf:
        n_pages = len(pdf.pages)
        workers = min(os.cpu_count() or 1, MAX_WORKERS, n_pages) if n_pages else 0

        if n_pages == 0 or n_pages < MIN_PAGES_FOR_PARALLEL or workers <= 1:
            return [page.extract_table() for page in pdf.pages]

    chunks: list[list[int]] = [[] for _ in range(workers)]
    for i in range(n_pages):
        chunks[i % workers].append(i)

    ordered: list[tuple[int, list | None]] = []
    with ProcessPoolExecutor(max_workers=workers) as executor:
        for chunk_result in executor.map(_extract_chunk, [data] * workers, chunks):
            ordered.extend(chunk_result)

    ordered.sort(key=lambda item: item[0])
    return [table for _, table in ordered]
