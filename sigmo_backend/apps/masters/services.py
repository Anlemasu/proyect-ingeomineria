import openpyxl
from datetime import datetime
from decimal import Decimal, InvalidOperation
from .models import PinsDumper


# Mapeo de columnas del Excel exportado desde el PDF de la SDA
# El admin debe asegurarse que el Excel tenga estas columnas en este orden
EXPECTED_COLUMNS = [
    'PIN', 'NOMBRE', 'DIRECCION', 'TELEFONO', 'E_MAIL',
    'PLACA', 'LUGAR_EXPEDICION', 'MODELO', 'CAPACIDAD',
    'CONDUCTOR', 'FECHA_REGISTRO', 'ESTADO'
]


def parse_pins_from_excel(file) -> dict:
    """
    RF-23: Lee el Excel exportado del PDF de la SDA
    y actualiza/crea registros en PinsDumper.
    """
    created = 0
    updated = 0
    rejected = []

    try:
        wb = openpyxl.load_workbook(file, data_only=True)
        ws = wb.active

        if ws is None:
            return {
                'success': False,
                'error': 'El archivo Excel no tiene hojas activas.'
            }
        
        # Buscar la fila de encabezados
        header_row = None
        for i, row in enumerate(ws.iter_rows(values_only=True), start=1):
            if row and any(
                str(cell).upper().strip() in ['PIN', 'PLACA', 'NOMBRE']
                for cell in row if cell
            ):
                header_row = i
                break

        if not header_row:
            return {
                'success': False,
                'error': 'No se encontró la fila de encabezados. '
                         'Verifique que el Excel tenga las columnas correctas.'
            }

        # Mapear índices de columnas por nombre
        headers = [
            str(cell).upper().strip() if cell else ''
            for cell in list(ws.iter_rows(
                min_row=header_row,
                max_row=header_row,
                values_only=True
            ))[0]
        ]

        def col_index(names: list[str]) -> int | None:
            """Busca el índice de una columna por posibles nombres."""
            for name in names:
                if name in headers:
                    return headers.index(name)
            return None

        idx_pin      = col_index(['PIN'])
        idx_nombre   = col_index(['NOMBRE'])
        idx_dir      = col_index(['DIRECCION', 'DIRECCIÓN'])
        idx_tel      = col_index(['TELEFONO', 'TELÉFONO'])
        idx_email    = col_index(['E_MAIL', 'EMAIL', 'CORREO'])
        idx_placa    = col_index(['PLACA'])
        idx_exp      = col_index(['LUGAR_EXPEDICION', 'LUGAR EXPEDICIÓN', 'LUGAR_EXPEDICIÓN'])
        idx_modelo   = col_index(['MODELO'])
        idx_cap      = col_index(['CAPACIDAD', 'CAPACID'])
        idx_driver   = col_index(['CONDUCTOR'])
        idx_fecha    = col_index(['FECHA_REGISTRO', 'FECHA REGISTRO'])
        idx_estado   = col_index(['ESTADO'])

        # Verificar columnas mínimas obligatorias
        if idx_pin is None or idx_placa is None:
            return {
                'success': False,
                'error': 'El Excel no tiene las columnas PIN y PLACA. '
                         'Verifique la estructura del archivo.'
            }

        def get_cell(row, idx):
            """Obtiene el valor de una celda de forma segura."""
            if idx is None or idx >= len(row):
                return ''
            val = row[idx]
            return str(val).strip() if val is not None else ''

        # Procesar filas de datos
        for fila_num, row in enumerate(
            ws.iter_rows(min_row=header_row + 1, values_only=True),
            start=header_row + 1
        ):
            # Ignorar filas completamente vacías
            if not any(cell for cell in row if cell):
                continue

            pin    = get_cell(row, idx_pin)
            plaque = get_cell(row, idx_placa).upper()[:6]

            # Validaciones obligatorias (RF-23)
            if not pin:
                rejected.append({'fila': fila_num, 'motivo': 'PIN vacío'})
                continue
            if not plaque:
                rejected.append({'fila': fila_num, 'motivo': 'Placa vacía'})
                continue

            propietary = get_cell(row, idx_nombre)[:50]
            address    = get_cell(row, idx_dir)[:20]
            email      = get_cell(row, idx_email)[:20]
            exp_site   = get_cell(row, idx_exp)[:20]
            model      = get_cell(row, idx_modelo)[:50]
            driver     = get_cell(row, idx_driver)[:50]
            state_raw  = get_cell(row, idx_estado).upper()
            date_raw   = get_cell(row, idx_fecha)
            tel_raw    = get_cell(row, idx_tel).replace(' ', '').replace('-', '')
            cap_raw    = get_cell(row, idx_cap).replace(',', '.')

            # Parsear fecha
            date_register = None
            for fmt in ['%d/%m/%Y', '%Y-%m-%d', '%d-%m-%Y', '%m/%d/%Y']:
                try:
                    date_register = datetime.strptime(date_raw, fmt).date()
                    break
                except ValueError:
                    continue

            if not date_register:
                # Si es un número (Excel guarda fechas como números)
                try:
                    from openpyxl.utils.datetime import from_excel
                    date_register = from_excel(int(date_raw)).date()
                except Exception:
                    rejected.append({
                        'fila': fila_num,
                        'placa': plaque,
                        'motivo': f'Fecha inválida: "{date_raw}"'
                    })
                    continue

            # Parsear teléfono
            try:
                phone = Decimal(tel_raw) if tel_raw else Decimal('0')
            except InvalidOperation:
                phone = Decimal('0')

            # Parsear capacidad
            try:
                capacity = Decimal(cap_raw) if cap_raw else Decimal('0')
            except InvalidOperation:
                capacity = Decimal('0')

            # Estado
            state = state_raw == 'ACTIVO'

            # Crear o actualizar (RF-23)
            try:
                existing = PinsDumper.objects.filter(
                    plaque=plaque,
                    ambiental_pin=pin
                ).first()

                if existing:
                    existing.propietary      = propietary
                    existing.address         = address
                    existing.phone           = phone       # type: ignore
                    existing.email           = email
                    existing.expedition_site = exp_site
                    existing.model           = model
                    existing.capacity        = capacity    # type: ignore
                    existing.driver          = driver
                    existing.date_register   = date_register
                    existing.state           = state
                    existing.save()
                    updated += 1
                else:
                    PinsDumper.objects.create(
                        ambiental_pin    = pin,
                        propietary       = propietary,
                        address          = address,
                        phone            = phone,
                        email            = email,
                        plaque           = plaque,
                        expedition_site  = exp_site,
                        model            = model,
                        capacity         = capacity,
                        driver           = driver,
                        date_register    = date_register,
                        state            = state,
                    )
                    created += 1

            except Exception as e:
                rejected.append({
                    'fila': fila_num,
                    'placa': plaque,
                    'motivo': f'Error al guardar: {str(e)}'
                })

    except Exception as e:
        return {
            'success': False,
            'error': f'No se pudo leer el archivo: {str(e)}',
        }

    return {
        'success': True,
        'created': created,
        'updated': updated,
        'rejected_count': len(rejected),
        'rejected': rejected,
    }