"""Errores que pueden mostrarse directamente al usuario."""


class ErrorDeNegocio(Exception):
    """Una operación no cumple las reglas del negocio."""

    def __init__(self, mensaje, campo=None):
        super().__init__(mensaje)
        self.mensaje = mensaje
        self.campo = campo
