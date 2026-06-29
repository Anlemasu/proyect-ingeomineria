import pdfplumber

ruta = r'C:\Users\angel\Downloads\TRANSPORTADORES INSCRITOS ESCOMBROS_2026_compressed.pdf'

with pdfplumber.open(ruta) as pdf:
    page = pdf.pages[0]
    tables = page.extract_tables()
    # Ver las primeras 5 filas de la primera tabla
    for row in tables[0][:5]:
        print(row)
        print('---')