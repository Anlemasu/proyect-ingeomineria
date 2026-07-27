def uppercase_fields(instance, *field_names):
    for name in field_names:
        value = getattr(instance, name, None)
        if isinstance(value, str):
            setattr(instance, name, value.upper())
